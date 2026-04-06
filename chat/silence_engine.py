from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

from chat.context_reader import ContextLine
from ai.intent_classifier import IntentResult


EMOJI_LIKE_RE = re.compile(r"[\u2600-\u27BF\U0001F300-\U0001FAFF]", re.UNICODE)


@dataclass(slots=True)
class SilenceDecision:
    should_stay_silent: bool
    reason: str


def evaluate_silence(
    *,
    text: str,
    sender_user_id: int | None,
    message_has_sticker: bool,
    message_has_media_without_caption: bool,
    reply_to_owner: bool,
    mentions_owner: bool,
    recent_context: list[ContextLine],
    runtime,
    intent: IntentResult,
    min_meaningful_message_length: int,
    max_consecutive_ai_replies: int,
    user_reply_cooldown_seconds: int,
    now: datetime | None = None,
) -> SilenceDecision:
    current_time = now or datetime.now(timezone.utc)
    normalized = " ".join((text or "").split()).strip()

    if message_has_sticker:
        return SilenceDecision(True, "sticker_only")
    if message_has_media_without_caption:
        return SilenceDecision(True, "media_without_caption")
    if _is_emoji_only(normalized):
        return SilenceDecision(True, "emoji_only")
    if len(normalized) < max(1, min_meaningful_message_length) and intent.kind in {"reaction", "unclear"}:
        return SilenceDecision(True, "not_meaningful_enough")

    if intent.kind == "reaction" and not reply_to_owner and not mentions_owner:
        return SilenceDecision(True, "reaction_message")

    if _conversation_between_other_users_is_active(recent_context) and not any((reply_to_owner, mentions_owner)):
        return SilenceDecision(True, "other_users_conversation_active")

    if getattr(runtime, "consecutive_ai_replies", 0) >= max(1, max_consecutive_ai_replies):
        return SilenceDecision(True, "too_many_consecutive_ai_replies")

    if sender_user_id is not None:
        raw_timestamp = getattr(runtime, "user_reply_timestamps", {}).get(str(sender_user_id))
        replied_at = _parse_iso(raw_timestamp)
        if replied_at is not None and (current_time - replied_at).total_seconds() < max(0, user_reply_cooldown_seconds):
            return SilenceDecision(True, "sender_recently_replied")

    if getattr(runtime, "last_reply_at", None) and getattr(runtime, "consecutive_ai_replies", 0) > 0:
        replied_at = _parse_iso(runtime.last_reply_at)
        if replied_at is not None and (current_time - replied_at).total_seconds() < max(15, user_reply_cooldown_seconds // 2):
            if not any((reply_to_owner, mentions_owner)):
                return SilenceDecision(True, "recent_ai_reply_in_thread")

    return SilenceDecision(False, "ok")


def _is_emoji_only(text: str) -> bool:
    if not text:
        return False
    compact = "".join(char for char in text if not char.isspace())
    if not compact:
        return False
    if any(char.isalnum() for char in compact):
        return False
    if EMOJI_LIKE_RE.search(compact):
        return True
    categories = {unicodedata.category(char) for char in compact}
    return categories.issubset({"So", "Sk", "Sm", "Po"})


def _conversation_between_other_users_is_active(recent_context: list[ContextLine]) -> bool:
    if not recent_context:
        return False
    recent = recent_context[-5:]
    if any(getattr(line, "author", "") == "Owner" for line in recent):
        return False
    participants = {getattr(line, "author", "") for line in recent if getattr(line, "author", "")}
    participants.discard("Owner")
    return len(participants) >= 2


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
