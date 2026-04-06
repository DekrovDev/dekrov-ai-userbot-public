from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
import mimetypes
import httpx
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    BadRequestError,
    RateLimitError,
)

from config.settings import AppConfig
from config.identity import (
    classify_identity_question,
    force_identity_answer,
    is_identity_question,
)
from .judge import JudgeDecision, build_judge_messages, parse_judge_response
from infra.language_tools import detect_language, tr
from .model_stats import ModelStatsStore
from .model_pool import judge_candidates, preferred_generator_order, preferred_task_order
from config.prompts import build_system_messages
from safety.safety import classify_request_safety
from state.state import RateLimitState, StateStore
from .validator import (
    CandidateAssessment,
    assess_candidate_response,
    choose_best_available_index,
    sanitize_ai_output,
)


LOGGER = logging.getLogger("assistant.groq")


@dataclass(slots=True)
class ChatResult:
    text: str
    model: str
    judge_model: str | None = None
    finish_reason: str | None = None
    validation_reason: str = "accepted_locally"


@dataclass(slots=True)
class RawCompletionResult:
    text: str
    model: str
    finish_reason: str | None
    latency_ms: float


@dataclass(slots=True)
class CandidateRecord:
    candidate_id: str
    model: str
    finish_reason: str | None
    raw_text: str
    assessment: CandidateAssessment


class GroqClient:
    def __init__(
        self, config: AppConfig, state: StateStore, model_stats: ModelStatsStore
    ) -> None:
        self._config = config
        self._state = state
        self._model_stats = model_stats
        self._client = AsyncOpenAI(
            api_key=config.groq_api_key,
            base_url=config.groq_base_url,
            timeout=config.openai_timeout_seconds,
            max_retries=0,  # We handle retries/fallback ourselves
        )

    async def close(self) -> None:
        await self._client.close()

    async def transcribe_audio(
        self, audio_bytes: bytes, filename: str = "voice.ogg"
    ) -> str | None:
        """Transcribe audio via Groq Whisper API. Returns text or None on failure."""

        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self._config.groq_api_key}"},
                    files={"file": (filename, audio_bytes, mime_type)},
                    data={"model": "whisper-large-v3-turbo", "response_format": "text"},
                )
                resp.raise_for_status()
                text = resp.text.strip()
                LOGGER.info("transcribe_audio_ok length=%d", len(text))
                return text if text else None
        except Exception:
            LOGGER.exception("transcribe_audio_failed")
            return None

    async def generate_vision_reply(
        self,
        prompt: str,
        image_base64: str,
        image_mime: str = "image/jpeg",
        *,
        user_query: str | None = None,
        response_mode: str = "ai_prefixed",
    ) -> ChatResult:
        """Send prompt + image to a vision-capable model."""
        vision_model = "meta-llama/llama-4-scout-17b-16e-instruct"
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_mime};base64,{image_base64}",
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        try:
            result = await self._request_chat_completion(
                model=vision_model,
                messages=messages,
                max_output_tokens=1000,
            )
            return ChatResult(
                text=sanitize_ai_output(
                    result.text,
                    user_query=user_query or prompt,
                    response_mode=response_mode,
                ),
                model=vision_model,
                judge_model=None,
                finish_reason=result.finish_reason,
                validation_reason="vision",
            )
        except Exception as exc:
            LOGGER.warning("vision_request_failed error=%s", exc.__class__.__name__)
            raise

    async def refresh_models(self) -> list[str]:
        response = await self._client.models.list()
        fetched = [item.id for item in response.data if getattr(item, "id", None)]
        filtered = [model for model in self._config.default_models if model in fetched]
        missing = [
            model for model in self._config.default_models if model not in filtered
        ]
        models = filtered + missing
        await self._state.sync_model_pool(models)
        snapshot = await self._state.get_snapshot()
        LOGGER.info(
            "refreshed_models count=%s active_model=%s judge_model=%s",
            len(models),
            snapshot.active_model,
            snapshot.judge_model,
        )
        return models

    async def generate_reply(
        self,
        prompt: str,
        *,
        user_query: str | None = None,
        style_instruction: str | None = None,
        reply_mode: str = "command",
        max_output_tokens: int | None = None,
        response_mode: str = "ai_prefixed",
        response_style_mode: str = "NORMAL",
        apply_live_guard: bool = True,
        task_type_override: str | None = None,
    ) -> ChatResult:
        reference_query = user_query or prompt
        expected_language = detect_language(reference_query)
        task_type = task_type_override or self._detect_task_type(
            reference_query, reply_mode
        )
        question_type = classify_identity_question(reference_query)
        if question_type is not None:
            return ChatResult(
                text=sanitize_ai_output(
                    force_identity_answer(
                        expected_language,
                        response_mode=response_mode,
                        question_type=question_type,
                    ),
                    user_query=reference_query,
                    expected_language=expected_language,
                    response_mode=response_mode,
                ),
                model="identity_guard",
                judge_model=None,
                finish_reason=None,
                validation_reason="canonical_identity",
            )
        safety = classify_request_safety(reference_query)
        LOGGER.info(
            "request_safety safe=%s category=%s source=user_query",
            safety.is_safe,
            safety.category,
        )
        if not safety.is_safe:
            LOGGER.warning("request_rejected_by_safety category=%s", safety.category)
            return ChatResult(
                text=sanitize_ai_output(
                    safety.refusal_text,
                    user_query=reference_query,
                    expected_language=expected_language,
                    response_mode=response_mode,
                ),
                model="safety_guard",
                judge_model=None,
                finish_reason=None,
                validation_reason=f"safety_refusal:{safety.category}",
            )

        snapshot = await self._state.get_snapshot()
        ordered_models = preferred_generator_order(
            available_models=snapshot.available_models,
            enabled_models=snapshot.enabled_models,
            active_model=snapshot.active_model,
            model_limits=snapshot.model_limits,
        )
        if not ordered_models:
            ordered_models = self._ordered_models(
                snapshot.active_model, snapshot.available_models
            )
        if not snapshot.fallback_enabled:
            ordered_models = ordered_models[:1]
        ordered_models = preferred_task_order(task_type, ordered_models)
        ordered_models = await self._model_stats.rank_models(ordered_models, task_type)

        last_api_error: Exception | None = None
        candidate_records: list[CandidateRecord] = []
        # Track if we hit rate limit â€” always try next model on 429 even if fallback disabled
        _rate_limited_models: set[str] = set()

        for index, model in enumerate(ordered_models):
            can_try_next = (
                snapshot.fallback_enabled and index < len(ordered_models) - 1
            ) or model in _rate_limited_models
            try:
                candidate = await self._generate_candidate(
                    model=model,
                    prompt=prompt,
                    user_query=reference_query,
                    style_instruction=style_instruction,
                    reply_mode=reply_mode,
                    max_output_tokens=max_output_tokens,
                    response_mode=response_mode,
                    response_style_mode=response_style_mode,
                    apply_live_guard=apply_live_guard,
                )
            except RateLimitError as exc:
                last_api_error = exc
                _rate_limited_models.add(model)
                await self._persist_headers_from_exception(exc, model)
                # On 429 always try next model â€” don't wait, switch immediately
                all_models = self._ordered_models(
                    snapshot.active_model, snapshot.available_models
                )
                remaining = [
                    m
                    for m in all_models
                    if m not in {model} and m not in _rate_limited_models
                ]
                if remaining:
                    ordered_models = [
                        model
                        for model in ordered_models
                        if model not in _rate_limited_models
                    ] + [m for m in remaining if m not in ordered_models]
                LOGGER.warning(
                    "model_rate_limited model=%s switching_to_next=True", model
                )
                continue
            except (
                APIConnectionError,
                APITimeoutError,
                APIError,
                BadRequestError,
            ) as exc:
                last_api_error = exc
                await self._persist_headers_from_exception(exc, model)
                LOGGER.warning(
                    "model_request_failed model=%s retry=%s error_type=%s",
                    model,
                    can_try_next,
                    exc.__class__.__name__,
                )
                continue

            assessment = assess_candidate_response(
                candidate.text,
                candidate.finish_reason,
                prompt=prompt,
                expected_language=expected_language,
                allow_refusal=False,
                response_mode=response_mode,
            )
            await self._model_stats.record_result(
                model=model,
                task_type=task_type,
                success=assessment.clearly_acceptable,
                incomplete=assessment.is_truncated,
                refusal=assessment.is_refusal,
                response_length=len(assessment.answer_text),
                latency_ms=candidate.latency_ms,
            )
            record = CandidateRecord(
                candidate_id=f"c{len(candidate_records) + 1}",
                model=model,
                finish_reason=candidate.finish_reason,
                raw_text=candidate.text,
                assessment=assessment,
            )
            if assessment.usable:
                candidate_records.append(record)

            if assessment.clearly_acceptable:
                await self._state.set_active_model(model)
                if index == 0:
                    LOGGER.info(
                        "candidate_accepted_directly model=%s score=%s",
                        model,
                        assessment.score,
                    )
                else:
                    LOGGER.info(
                        "candidate_accepted_after_fallback model=%s score=%s",
                        model,
                        assessment.score,
                    )
                return ChatResult(
                    text=sanitize_ai_output(
                        assessment.cleaned_text,
                        user_query=reference_query,
                        expected_language=expected_language,
                        response_mode=response_mode,
                    ),
                    model=model,
                    judge_model=None,
                    finish_reason=candidate.finish_reason,
                    validation_reason=assessment.reason,
                )

            LOGGER.warning(
                "candidate_rejected_due_to_bad_output model=%s score=%s reason=%s retry=%s",
                model,
                assessment.score,
                assessment.reason,
                can_try_next,
            )

        judged = await self._judge_or_choose_best_available(
            prompt, candidate_records, snapshot, response_mode
        )
        if judged is not None:
            chosen_record, judge_model_name, decision = judged
            await self._state.set_active_model(chosen_record.model)
            if decision == "accept":
                LOGGER.info(
                    "candidate_accepted_by_judge model=%s judge_model=%s candidate_id=%s",
                    chosen_record.model,
                    judge_model_name,
                    chosen_record.candidate_id,
                )
                validation_reason = "accepted_by_judge"
            elif decision == "best_available":
                LOGGER.warning(
                    "candidate_accepted_as_best_available model=%s judge_model=%s candidate_id=%s score=%s",
                    chosen_record.model,
                    judge_model_name,
                    chosen_record.candidate_id,
                    chosen_record.assessment.score,
                )
                validation_reason = "best_available_by_judge"
            else:
                LOGGER.warning(
                    "candidate_accepted_as_best_available_local model=%s candidate_id=%s score=%s",
                    chosen_record.model,
                    chosen_record.candidate_id,
                    chosen_record.assessment.score,
                )
                validation_reason = "best_available_local"

            return ChatResult(
                text=sanitize_ai_output(
                    chosen_record.assessment.cleaned_text,
                    user_query=reference_query,
                    expected_language=expected_language,
                    response_mode=response_mode,
                ),
                model=chosen_record.model,
                judge_model=judge_model_name,
                finish_reason=chosen_record.finish_reason,
                validation_reason=validation_reason,
            )

        if last_api_error is not None:
            LOGGER.error(
                "safe_request_failed_completely error_type=%s",
                last_api_error.__class__.__name__,
            )
        else:
            LOGGER.error("safe_request_failed_completely no_usable_candidates=true")

        return ChatResult(
            text=sanitize_ai_output(
                tr("failure_generic", expected_language),
                user_query=reference_query,
                expected_language=expected_language,
                response_mode=response_mode,
            ),
            model=snapshot.active_model,
            judge_model=None,
            finish_reason=None,
            validation_reason="failed_completely",
        )

    async def _generate_candidate(
        self,
        *,
        model: str,
        prompt: str,
        user_query: str | None,
        style_instruction: str | None,
        reply_mode: str,
        max_output_tokens: int | None,
        response_mode: str,
        response_style_mode: str,
        apply_live_guard: bool,
    ) -> RawCompletionResult:
        base_limit = self._effective_max_output_tokens(
            max_output_tokens, response_style_mode
        )
        initial = await self._request_chat_completion(
            model=model,
            messages=self._build_messages(
                model,
                prompt,
                user_query,
                style_instruction,
                reply_mode,
                response_mode,
                response_style_mode,
                apply_live_guard,
            ),
            max_output_tokens=base_limit,
        )
        if (initial.finish_reason or "").casefold() not in {"length", "max_tokens"}:
            return initial

        retry_limit = max(base_limit + 220, int(base_limit * 1.6))
        LOGGER.info(
            "retry_same_model_for_truncation model=%s max_tokens=%s", model, retry_limit
        )
        retried = await self._request_chat_completion(
            model=model,
            messages=self._build_messages(
                model,
                prompt,
                user_query,
                style_instruction,
                reply_mode,
                response_mode,
                response_style_mode,
                apply_live_guard,
            ),
            max_output_tokens=retry_limit,
        )
        return retried

    async def _judge_or_choose_best_available(
        self,
        prompt: str,
        candidate_records: list[CandidateRecord],
        snapshot,
        response_mode: str,
    ) -> tuple[CandidateRecord, str | None, str] | None:
        if not candidate_records:
            return None

        local_best = self._select_best_available_candidate(candidate_records)
        judge_model_name = None

        judge_candidates_list = judge_candidates(
            snapshot.available_models, snapshot.enabled_models, snapshot.judge_model
        )
        if judge_candidates_list:
            judge_payload = [
                {
                    "id": record.candidate_id,
                    "score": record.assessment.score,
                    "reason": record.assessment.reason,
                    "answer": record.assessment.answer_text[:1200],
                }
                for record in sorted(
                    candidate_records,
                    key=lambda item: item.assessment.score,
                    reverse=True,
                )[:5]
            ]
            for judge_model_name in judge_candidates_list:
                try:
                    result = await self._request_chat_completion(
                        model=judge_model_name,
                        messages=build_judge_messages(
                            prompt, judge_payload, response_mode=response_mode
                        ),
                        max_output_tokens=80,
                        temperature=0.0,
                    )
                except (
                    RateLimitError,
                    APIConnectionError,
                    APITimeoutError,
                    APIError,
                    BadRequestError,
                ) as exc:
                    await self._persist_headers_from_exception(exc, judge_model_name)
                    LOGGER.warning(
                        "judge_request_failed model=%s error=%s",
                        judge_model_name,
                        exc.__class__.__name__,
                    )
                    continue

                decision = parse_judge_response(result.text)
                chosen = self._candidate_from_decision(candidate_records, decision)
                if chosen is not None and decision.decision in {
                    "accept",
                    "best_available",
                }:
                    return chosen, judge_model_name, decision.decision
                LOGGER.warning(
                    "judge_selection_unusable model=%s decision=%s reason=%s",
                    judge_model_name,
                    decision.decision,
                    decision.reason,
                )
                break

        if local_best is not None:
            return local_best, judge_model_name, "local_best_available"
        return None

    async def _request_chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_output_tokens: int,
        temperature: float = 0.35,
    ) -> RawCompletionResult:
        started_at = time.perf_counter()
        raw_response = await self._client.chat.completions.with_raw_response.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_output_tokens,
        )
        latency_ms = (time.perf_counter() - started_at) * 1000.0
        completion = raw_response.parse()
        choice = completion.choices[0]
        content = (choice.message.content or "").strip()
        finish_reason = getattr(choice, "finish_reason", None)
        headers = dict(raw_response.headers.items())
        await self._state.update_model_limits(
            self._build_rate_limit_state(headers, model)
        )
        LOGGER.info("model_request_ok model=%s finish_reason=%s", model, finish_reason)
        return RawCompletionResult(
            text=content,
            model=model,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
        )

    def _build_messages(
        self,
        model: str,
        prompt: str,
        user_query: str | None,
        style_instruction: str | None,
        reply_mode: str,
        response_mode: str,
        response_style_mode: str,
        apply_live_guard: bool,
    ) -> list[dict[str, str]]:
        return build_system_messages(
            model_name=model,
            prompt=prompt,
            user_query=user_query,
            style_instruction=style_instruction,
            reply_mode=reply_mode,
            reject_live_data_requests=self._config.reject_live_data_requests
            and apply_live_guard,
            response_mode=response_mode,
            response_style_mode=response_style_mode,
        )

    async def _persist_headers_from_exception(self, exc: Exception, model: str) -> None:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        if headers is None:
            return

        if hasattr(headers, "items"):
            header_map = dict(headers.items())
        else:
            header_map = dict(headers)
        await self._state.update_model_limits(
            self._build_rate_limit_state(header_map, model)
        )

    def _ordered_models(
        self, active_model: str, available_models: Iterable[str]
    ) -> list[str]:
        models = [model for model in available_models if model]
        if active_model not in models:
            models.insert(0, active_model)
        ordered = [active_model]
        ordered.extend(model for model in models if model != active_model)
        seen: set[str] = set()
        unique: list[str] = []
        for model in ordered:
            if model in seen:
                continue
            seen.add(model)
            unique.append(model)
        return unique

    def _candidate_from_decision(
        self,
        candidate_records: list[CandidateRecord],
        decision: JudgeDecision,
    ) -> CandidateRecord | None:
        if not decision.candidate_id:
            return None
        for record in candidate_records:
            if record.candidate_id == decision.candidate_id:
                return record
        return None

    def _select_best_available_candidate(
        self, candidate_records: list[CandidateRecord]
    ) -> CandidateRecord | None:
        assessments = [record.assessment for record in candidate_records]
        index = choose_best_available_index(assessments)
        if index is None:
            return None
        return candidate_records[index]

    def _build_rate_limit_state(
        self, headers: dict[str, str], model: str
    ) -> RateLimitState:
        normalized = {key.lower(): value for key, value in headers.items()}
        return RateLimitState(
            model=model,
            remaining_requests=self._header_value(
                normalized,
                "x-ratelimit-remaining-requests",
                "ratelimit-remaining-requests",
            ),
            request_limit=self._header_value(
                normalized,
                "x-ratelimit-limit-requests",
                "ratelimit-limit-requests",
            ),
            remaining_tokens=self._header_value(
                normalized,
                "x-ratelimit-remaining-tokens",
                "ratelimit-remaining-tokens",
            ),
            token_limit=self._header_value(
                normalized,
                "x-ratelimit-limit-tokens",
                "ratelimit-limit-tokens",
            ),
            retry_after=self._header_value(normalized, "retry-after"),
            last_updated=datetime.now(timezone.utc).isoformat(),
        )

    def _header_value(self, headers: dict[str, str], *candidates: str) -> str | None:
        for candidate in candidates:
            value = headers.get(candidate)
            if value:
                return value
        return None

    def _detect_task_type(self, text: str, reply_mode: str) -> str:
        lowered = (text or "").casefold()
        if reply_mode == "planner":
            return "command_understanding"
        if reply_mode == "auto_reply":
            return "conversation"
        if any(
            marker in lowered
            for marker in ("summary", "summar", "ÑÑƒÐ¼Ð¼", "Ð¸Ñ‚Ð¾Ð³", "Ð¾ Ñ‡ÐµÐ¼")
        ):
            return "summary"
        if any(
            marker in lowered
            for marker in (
                "analysis",
                "analy",
                "Ñ€Ð°Ð·Ð±ÐµÑ€Ð¸",
                "ÑÑ€Ð°Ð²Ð½Ð¸",
                "compare",
                "Ð¿Ñ€Ð¾Ð°Ð½Ð°Ð»Ð¸Ð·",
            )
        ):
            return "analysis"
        return "command"

    def _effective_max_output_tokens(
        self, explicit_limit: int | None, response_style_mode: str
    ) -> int:
        base = explicit_limit or self._config.max_output_tokens
        mode = str(response_style_mode or "NORMAL").strip().upper()
        if mode == "SHORT":
            return max(120, int(base * 0.65))
        if mode == "DETAILED":
            return int(base * 1.45)
        if mode == "HUMANLIKE":
            return max(160, int(base * 0.9))
        if mode == "SAFE":
            return max(140, int(base * 0.85))
        return base

    async def generate_visitor_completion(
        self,
        *,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int = 700,
        temperature: float = 0.4,
        user_query: str | None = None,
        expected_language: str | None = None,
    ) -> str | None:
        """Separate visitor-only completion. Does NOT touch owner pipeline,
        judge model, autoswitch, or any owner-related logic."""
        visitor_model = model or self._config.visitor_primary_model
        try:
            raw = await self._request_chat_completion(
                model=visitor_model,
                messages=messages,
                max_output_tokens=max_tokens,
                temperature=temperature,
            )
            if not raw.text:
                return None
            cleaned = sanitize_ai_output(
                raw.text,
                user_query=user_query,
                expected_language=expected_language,
                response_mode="human_like_owner",
            )
            return cleaned or None
        except Exception as exc:
            LOGGER.warning(
                "visitor_completion_error model=%s error=%s",
                visitor_model,
                exc.__class__.__name__,
            )
            return None

    async def generate_visitor_judge_completion(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int = 180,
    ) -> str | None:
        """Small dedicated completion for visitor QA / review alerts."""
        try:
            raw = await self._request_chat_completion(
                model=model,
                messages=messages,
                max_output_tokens=max_tokens,
                temperature=0.0,
            )
            return (raw.text or "").strip() or None
        except Exception as exc:
            LOGGER.warning(
                "visitor_judge_completion_error model=%s error=%s",
                model,
                exc.__class__.__name__,
            )
            return None

