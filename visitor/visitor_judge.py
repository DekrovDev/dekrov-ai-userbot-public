from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

from infra.json_atomic import atomic_write_json


LOGGER = logging.getLogger("assistant.visitor.judge")

_ALLOWED_ISSUES = {
    "wrong_route",
    "robotic_tone",
    "raw_source_dump",
    "too_many_links",
    "formatting_issue",
    "too_long",
    "not_helpful",
    "missed_supportive_tone",
    "bad_draft_quality",
    "unsupported_claim",
}
_SOURCE_DUMP_MARKERS = (
    "portfolio:",
    "github:",
    "website:",
    "telegram channel:",
)
_URL_RE = re.compile(r"https?://|<a\s+href=", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(slots=True)
class VisitorJudgeVerdict:
    flagged: bool
    severity: str
    confidence: float
    issues: list[str]
    summary: str
    raw_text: str = ""


@dataclass(slots=True)
class VisitorJudgeIncident:
    signature: str
    count: int
    first_seen_at: float
    last_seen_at: float
    last_alert_at: float = 0.0
    severity: str = "low"
    summary: str = ""


def should_review_visitor_response(
    user_text: str,
    answer: str,
    *,
    category_value: str,
    route_value: str,
) -> bool:
    answer_text = _html_to_text(answer)
    user_text = (user_text or "").strip()
    if not user_text or not answer_text:
        return False

    answer_len = len(answer_text)
    link_count = count_links(answer)
    source_dump = looks_like_source_dump(answer)
    category = (category_value or "").strip().casefold()
    route = (route_value or "").strip().casefold()

    if category in {"general", "collaboration"}:
        return True
    if source_dump:
        return True
    if link_count >= 2:
        return True
    if answer_len >= 650:
        return True
    if category in {"links", "about_projects", "project_specific_question"} and (
        answer_len >= 260 or route.startswith("search_")
    ):
        return True
    return False


def build_visitor_judge_messages(
    *,
    user_text: str,
    answer: str,
    category_value: str,
    route_value: str,
) -> list[dict[str, str]]:
    plain_answer = _html_to_text(answer)[:1800]
    plain_user = (user_text or "").strip()[:900]
    system_prompt = (
        "You are a strict quality reviewer for a public Telegram visitor assistant. "
        "Your task is to detect user-visible quality problems, not safety policy violations. "
        "Flag only meaningful issues that a maintainer should know about. "
        "Allowed issue labels: wrong_route, robotic_tone, raw_source_dump, too_many_links, "
        "formatting_issue, too_long, not_helpful, missed_supportive_tone, bad_draft_quality, unsupported_claim. "
        "Return only JSON with keys flagged, severity, confidence, issues, summary. "
        "Severity must be low, medium, or high. Confidence must be a number from 0 to 1. "
        "Summary must be short, concrete, and in Russian."
    )
    user_prompt = (
        f"visitor_category: {category_value}\n"
        f"visitor_route: {route_value}\n\n"
        "Visitor message:\n"
        f"{plain_user}\n\n"
        "Assistant answer:\n"
        f"{plain_answer}\n\n"
        "Flag the answer if it is obviously too robotic, not actually helpful, gives a raw source dump, "
        "pushes links too hard, misses emotional support, formats poorly for Telegram, is too long, "
        "or turns a user request into the wrong kind of response."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def parse_visitor_judge_response(text: str) -> VisitorJudgeVerdict:
    raw = (text or "").strip()
    payload = _extract_json_payload(raw)
    if payload is None:
        return VisitorJudgeVerdict(
            flagged=False,
            severity="low",
            confidence=0.0,
            issues=[],
            summary="",
            raw_text=raw,
        )

    flagged = bool(payload.get("flagged", False))
    severity = str(payload.get("severity", "low") or "low").strip().lower()
    if severity not in {"low", "medium", "high"}:
        severity = "low"

    confidence_raw = payload.get("confidence", 0.0)
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(confidence, 1.0))

    issues_payload = payload.get("issues", [])
    if not isinstance(issues_payload, list):
        issues_payload = []
    issues: list[str] = []
    for item in issues_payload:
        label = str(item or "").strip().lower()
        if label in _ALLOWED_ISSUES and label not in issues:
            issues.append(label)

    summary = str(payload.get("summary", "") or "").strip()
    summary = re.sub(r"\s+", " ", summary)[:240]

    if not flagged:
        issues = []
        summary = ""

    return VisitorJudgeVerdict(
        flagged=flagged,
        severity=severity,
        confidence=confidence,
        issues=issues,
        summary=summary,
        raw_text=raw,
    )


def build_incident_signature(
    *,
    category_value: str,
    route_value: str,
    issues: list[str],
) -> str:
    normalized_issues = "-".join(sorted(issues)[:4]) or "unknown"
    category = (category_value or "unknown").strip().casefold()
    route = (route_value or "unknown").strip().casefold()
    return f"{category}|{route}|{normalized_issues}"


def format_visitor_judge_notification(
    *,
    user_id: int,
    username: str | None,
    first_name: str | None,
    user_text: str,
    answer: str,
    category_value: str,
    route_value: str,
    verdict: VisitorJudgeVerdict,
    incident: VisitorJudgeIncident,
) -> str:
    user_label = (
        f"@{username}"
        if username
        else (first_name or f"user_{user_id}")
    )
    issues = ", ".join(verdict.issues) if verdict.issues else "unknown"
    user_preview = html.escape(_truncate(_html_to_text(user_text), 500))
    answer_preview = html.escape(_truncate(_html_to_text(answer), 900))
    summary = html.escape(verdict.summary or "Ð‘ÐµÐ· Ð¿Ð¾ÑÑÐ½ÐµÐ½Ð¸Ñ")
    return (
        "<b>Visitor Judge Alert</b>\n\n"
        f"<b>User:</b> <code>{user_id}</code> ({html.escape(user_label)})\n"
        f"<b>Severity:</b> {html.escape(verdict.severity)} | "
        f"<b>Confidence:</b> {verdict.confidence:.2f}\n"
        f"<b>Category / Route:</b> {html.escape(category_value)} / {html.escape(route_value)}\n"
        f"<b>Issues:</b> {html.escape(issues)}\n"
        f"<b>Repeat count:</b> {incident.count}\n"
        f"<b>Summary:</b> {summary}\n\n"
        f"<b>Visitor message:</b>\n<blockquote>{user_preview}</blockquote>\n\n"
        f"<b>Bot answer:</b>\n<blockquote>{answer_preview}</blockquote>"
    )


class VisitorJudgeStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._incidents: dict[str, VisitorJudgeIncident] = {}

    async def load(self) -> None:
        async with self._lock:
            if self._path is None:
                return
            if not self._path.exists():
                await self._write_locked()
                return
            try:
                raw = await asyncio.to_thread(self._path.read_text, encoding="utf-8")
                payload = json.loads(raw or "{}")
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                LOGGER.warning("visitor_judge_store_load_failed", exc_info=True)
                payload = {}
            incidents_payload = payload.get("incidents", {})
            self._incidents = {}
            if isinstance(incidents_payload, dict):
                for signature, item in incidents_payload.items():
                    if not isinstance(item, dict):
                        continue
                    self._incidents[str(signature)] = VisitorJudgeIncident(
                        signature=str(signature),
                        count=max(0, int(item.get("count", 0) or 0)),
                        first_seen_at=float(item.get("first_seen_at", 0.0) or 0.0),
                        last_seen_at=float(item.get("last_seen_at", 0.0) or 0.0),
                        last_alert_at=float(item.get("last_alert_at", 0.0) or 0.0),
                        severity=str(item.get("severity", "low") or "low"),
                        summary=str(item.get("summary", "") or ""),
                    )
            await self._write_locked()

    async def register_incident(
        self,
        *,
        signature: str,
        severity: str,
        summary: str,
        repeat_threshold: int = 2,
        repeat_window_seconds: int = 3 * 24 * 60 * 60,
        alert_cooldown_seconds: int = 12 * 60 * 60,
    ) -> tuple[VisitorJudgeIncident, bool]:
        now = time.time()
        async with self._lock:
            incident = self._incidents.get(signature)
            if incident is None:
                incident = VisitorJudgeIncident(
                    signature=signature,
                    count=0,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                self._incidents[signature] = incident

            if incident.last_seen_at and (now - incident.last_seen_at) > repeat_window_seconds:
                incident.count = 0
                incident.first_seen_at = now

            incident.count += 1
            incident.last_seen_at = now
            incident.severity = severity
            incident.summary = summary[:240]

            should_alert = False
            if severity == "high":
                should_alert = not incident.last_alert_at or (
                    now - incident.last_alert_at
                ) >= alert_cooldown_seconds
            elif incident.count >= repeat_threshold:
                should_alert = not incident.last_alert_at or (
                    now - incident.last_alert_at
                ) >= alert_cooldown_seconds

            if should_alert:
                incident.last_alert_at = now

            await self._write_locked()
            return (
                VisitorJudgeIncident(
                    signature=incident.signature,
                    count=incident.count,
                    first_seen_at=incident.first_seen_at,
                    last_seen_at=incident.last_seen_at,
                    last_alert_at=incident.last_alert_at,
                    severity=incident.severity,
                    summary=incident.summary,
                ),
                should_alert,
            )

    async def _write_locked(self) -> None:
        if self._path is None:
            return
        payload = {
            "version": 1,
            "incidents": {
                signature: {
                    "count": incident.count,
                    "first_seen_at": incident.first_seen_at,
                    "last_seen_at": incident.last_seen_at,
                    "last_alert_at": incident.last_alert_at,
                    "severity": incident.severity,
                    "summary": incident.summary,
                }
                for signature, incident in self._incidents.items()
            },
        }
        await atomic_write_json(self._path, payload, indent=2)


def looks_like_source_dump(text: str) -> bool:
    lowered = _html_to_text(text).casefold()
    return any(marker in lowered for marker in _SOURCE_DUMP_MARKERS)


def count_links(text: str) -> int:
    return len(_URL_RE.findall(text or ""))


def _html_to_text(text: str) -> str:
    cleaned = html.unescape(text or "")
    cleaned = _TAG_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _extract_json_payload(text: str) -> dict[str, object] | None:
    if not text:
        return None
    candidates = [text]
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        candidates.insert(0, match.group(0))
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return None

