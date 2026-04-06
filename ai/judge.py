from __future__ import annotations

from dataclasses import dataclass

from config.identity import ASSISTANT_NAME, CREATOR_NAME, CREATOR_TELEGRAM_CHANNEL, is_identity_question
from infra.language_tools import detect_language, language_name


@dataclass(slots=True)
class JudgeDecision:
    decision: str
    candidate_id: str | None
    reason: str
    raw_text: str


def build_judge_messages(
    user_prompt: str,
    candidates: list[dict[str, str | int]],
    response_mode: str = "ai_prefixed",
) -> list[dict[str, str]]:
    prompt_reference = _prompt_reference_fragment(user_prompt)
    expected_language = detect_language(prompt_reference)
    human_like_mode = response_mode in {"human_like", "human_like_owner"}
    format_rule = (
        "formatted like a natural personal chat message without the 'AI:' prefix or AI self-reference"
        if human_like_mode
        else "properly formatted with the 'AI: ' prefix"
    )
    rendered_candidates: list[str] = []
    for candidate in candidates:
        rendered_candidates.append(
            f"{candidate['id']} | score={candidate['score']} | reason={candidate['reason']}\n"
            f"{candidate['answer']}"
        )
    if human_like_mode:
        identity_rule = (
            f"If the prompt asks who the assistant is or who created it, the answer should briefly make clear that this is {CREATOR_NAME}'s account"
            f" and may include {CREATOR_TELEGRAM_CHANNEL}. "
            "It must not present itself as an AI assistant or provider."
        )
    else:
        identity_rule = (
            f"If the prompt asks who the assistant is or who created it, the answer must say that the assistant is {ASSISTANT_NAME}, created by {CREATOR_NAME},"
            f" and include {CREATOR_TELEGRAM_CHANNEL}. "
        )
    system_prompt = (
        f"You are a strict answer judge for {ASSISTANT_NAME}. "
        "All user prompts are safe because unsafe requests are already blocked upstream. "
        "Choose the best candidate answer for the user. "
        f"Prefer answers that are relevant, complete, useful, readable, in {language_name(expected_language)}, and {format_rule}. "
        "Reject placeholders, refusal-only junk, truncated text, malformed output, wrong-language output, and low-value filler. "
        f"The assistant identity is fixed: {ASSISTANT_NAME}, created by {CREATOR_NAME}. "
        f"{identity_rule}"
        "Never reward answers that attribute the assistant's creator identity to OpenAI, Groq, Meta, Qwen, Moonshot, Anthropic, Kimi, Llama, GPT-OSS, or any provider. "
        "Return exactly one line in one of these formats: "
        "ACCEPT: <candidate_id> "
        "BEST_AVAILABLE: <candidate_id> "
        "REJECT: <short reason>."
    )
    extra_rule = ""
    if is_identity_question(prompt_reference):
        if human_like_mode:
            extra_rule = (
                "\nThis is an identity question in human_like_owner mode. Reject candidates that mention being an AI assistant or a provider."
            )
        else:
            extra_rule = (
                "\nThis is an identity question. Any candidate missing Project Assistant / ProjectOwner / creator channel or mentioning a provider must be rejected."
            )
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "User prompt:\n"
                f"{user_prompt}\n\n"
                "Candidates:\n"
                f"{chr(10).join(rendered_candidates)}\n\n"
                "Pick ACCEPT for a clearly good answer. "
                "Pick BEST_AVAILABLE for the least bad usable answer. "
                "Pick REJECT only if every candidate is unusable."
                f"{extra_rule}"
            ),
        },
    ]


def parse_judge_response(text: str) -> JudgeDecision:
    raw = (text or "").strip()
    normalized = raw.casefold()
    if normalized.startswith("accept"):
        candidate_id = _extract_candidate_id(raw)
        return JudgeDecision(
            decision="accept",
            candidate_id=candidate_id,
            reason="accepted_by_judge",
            raw_text=raw,
        )
    if normalized.startswith("best_available"):
        candidate_id = _extract_candidate_id(raw)
        return JudgeDecision(
            decision="best_available",
            candidate_id=candidate_id,
            reason="best_available_by_judge",
            raw_text=raw,
        )
    if normalized.startswith("reject"):
        reason = raw.split(":", 1)[1].strip() if ":" in raw else "rejected_by_judge"
        return JudgeDecision(
            decision="reject",
            candidate_id=None,
            reason=reason or "rejected_by_judge",
            raw_text=raw,
        )
    return JudgeDecision(
        decision="invalid",
        candidate_id=None,
        reason="invalid_judge_output",
        raw_text=raw,
    )


def _extract_candidate_id(raw_text: str) -> str | None:
    if ":" not in raw_text:
        return None
    candidate_id = raw_text.split(":", 1)[1].strip().split()[0]
    return candidate_id or None


def _prompt_reference_fragment(text: str) -> str:
    sample = (text or "").strip()
    for marker in ("Owner request:\n", "Newest incoming message:\n", "Incoming message:\n", "User prompt:\n"):
        if marker in sample:
            return sample.split(marker, 1)[1].strip()
    return sample


