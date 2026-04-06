from __future__ import annotations

import asyncio
import copy
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from infra.json_atomic import atomic_write_json


WORD_RE = re.compile(r"[A-Za-z\u0400-\u04FF][A-Za-z\u0400-\u04FF0-9_-]{2,}", re.UNICODE)
FORMAL_MARKERS = ("пожалуйста", "благодарю", "будьте добры", "please", "thank you")
INFORMAL_MARKERS = ("ну", "типа", "короче", "ок", "ага", "лол", "lol", "btw", "imho")
TECH_MARKERS = {
    "api",
    "bot",
    "proxy",
    "server",
    "linux",
    "ubuntu",
    "kali",
    "python",
    "config",
    "token",
    "model",
    "code",
    "docker",
    "nginx",
}
STOPWORDS = {
    "как",
    "что",
    "это",
    "про",
    "для",
    "или",
    "the",
    "and",
    "you",
    "with",
    "this",
    "that",
}


@dataclass(slots=True)
class UserProfile:
    username: str | None = None
    message_count: int = 0
    avg_message_length: float = 0.0
    typical_tone: str = "neutral"
    common_topics: list[str] = field(default_factory=list)
    interaction_frequency: float = 0.0
    last_interaction_time: str | None = None


@dataclass(slots=True)
class SpecialTargetSettings:
    enabled: bool = True
    human_like: bool = True
    bypass_delay: bool = True
    bypass_probability: bool = True
    bypass_cooldown: bool = True
    reply_only_questions: bool = False
    require_owner_mention_or_context: bool = False
    auto_transcribe: bool = False
    allowed_chat_ids: list[int] = field(default_factory=list)
    username: str | None = None
    # Per-chat flag overrides: {chat_id_str: {flag: value}}
    chat_overrides: dict = field(default_factory=dict)

    def resolve_for_chat(self, chat_id: int) -> "SpecialTargetSettings":
        """Return a copy with per-chat overrides applied."""
        overrides = self.chat_overrides.get(str(chat_id), {})
        if not overrides:
            return self
        import copy

        copy_ = copy.copy(self)
        for key, val in overrides.items():
            if hasattr(copy_, key) and isinstance(val, bool):
                setattr(copy_, key, val)
        return copy_


@dataclass(slots=True)
class SpecialTargetPatch:
    enabled: bool | None = None
    human_like: bool | None = None
    bypass_delay: bool | None = None
    bypass_probability: bool | None = None
    bypass_cooldown: bool | None = None
    reply_only_questions: bool | None = None
    require_owner_mention_or_context: bool | None = None
    auto_transcribe: bool | None = None
    allowed_chat_ids: list[int] | None = None
    username: str | None = None
    chat_overrides: dict | None = None


@dataclass(slots=True)
class CloseContactProfile:
    relation_type: str = "LESS_CLOSE"
    username: str | None = None
    comment: str = ""
    updated_at: str | None = None


@dataclass(slots=True)
class CloseContactPatch:
    relation_type: str | None = None
    username: str | None = None
    comment: str | None = None
    updated_at: str | None = None


class UserMemoryStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._profiles: dict[str, UserProfile] = {}
        self._special_targets: dict[str, SpecialTargetSettings] = {}
        self._close_contacts: dict[str, CloseContactProfile] = {}

    async def load(self) -> dict[str, UserProfile]:
        async with self._lock:
            if not self._path.exists():
                await self._write_locked()
                return copy.deepcopy(self._profiles)

            try:
                raw = await asyncio.to_thread(self._path.read_text, encoding="utf-8")
                payload = json.loads(raw or "{}")
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                payload = {}

            profiles_payload, special_targets_payload, close_contacts_payload = (
                self._split_payload(payload)
            )
            self._profiles = {
                str(user_id): self._from_dict(item)
                for user_id, item in profiles_payload.items()
                if isinstance(item, dict)
            }
            self._special_targets = {
                str(user_id): self._special_target_from_dict(item)
                for user_id, item in special_targets_payload.items()
                if isinstance(item, dict)
            }
            self._close_contacts = {
                str(user_id): self._close_contact_from_dict(item)
                for user_id, item in close_contacts_payload.items()
                if isinstance(item, dict)
            }
            await self._write_locked()
            return copy.deepcopy(self._profiles)

    async def observe_message(
        self,
        *,
        user_id: int,
        username: str | None,
        text: str,
        at: datetime | None = None,
    ) -> UserProfile:
        normalized = " ".join((text or "").split()).strip()
        if not normalized:
            return await self.get_profile(user_id)

        when = at or datetime.now(timezone.utc)
        async with self._lock:
            key = str(user_id)
            profile = self._profiles.get(key, UserProfile())
            old_count = profile.message_count
            profile.message_count += 1
            profile.username = username or profile.username
            profile.avg_message_length = _running_average(
                profile.avg_message_length, len(normalized), profile.message_count
            )
            profile.typical_tone = _detect_tone(profile.typical_tone, normalized)
            profile.common_topics = _merge_topics(
                profile.common_topics, _extract_topics(normalized)
            )
            profile.interaction_frequency = _compute_interaction_frequency(
                profile, when
            )
            profile.last_interaction_time = when.isoformat()
            self._profiles[key] = profile
            special_target = self._special_targets.get(key)
            if special_target is not None and username:
                special_target.username = username
            close_contact = self._close_contacts.get(key)
            if close_contact is not None and username:
                close_contact.username = username
            if old_count != profile.message_count:
                await self._write_locked()
            return copy.deepcopy(profile)

    async def get_profile(self, user_id: int) -> UserProfile:
        async with self._lock:
            return copy.deepcopy(self._profiles.get(str(user_id), UserProfile()))

    async def get_all_profiles(self) -> dict[str, UserProfile]:
        async with self._lock:
            return copy.deepcopy(self._profiles)

    async def cleanup_stale_profiles(
        self, *, max_age_days: int = 30, min_messages: int = 5
    ) -> int:
        """Remove inactive profiles and bot profiles. Returns count removed."""
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        async with self._lock:
            to_remove: list[str] = []
            for uid_str, profile in self._profiles.items():
                if uid_str in self._special_targets:
                    continue
                if uid_str in self._close_contacts:
                    continue
                # Remove bot profiles (username ends with "bot")
                uname = (profile.username or "").strip().casefold()
                if uname.endswith("bot"):
                    to_remove.append(uid_str)
                    continue
                if profile.message_count >= min_messages:
                    continue
                last = profile.last_interaction_time
                if last:
                    try:
                        last_dt = datetime.fromisoformat(last)
                        if last_dt.tzinfo is None:
                            last_dt = last_dt.replace(tzinfo=timezone.utc)
                        if last_dt > cutoff:
                            continue
                    except Exception:
                        pass
                to_remove.append(uid_str)
            for uid_str in to_remove:
                self._profiles.pop(uid_str, None)
            if to_remove:
                await self._write_locked()
        return len(to_remove)

    async def find_user_id_by_username(self, username: str | None) -> int | None:
        normalized = str(username or "").strip().lstrip("@").casefold()
        if not normalized:
            return None
        async with self._lock:
            for user_id, profile in self._profiles.items():
                if (profile.username or "").strip().lstrip(
                    "@"
                ).casefold() == normalized:
                    try:
                        return int(user_id)
                    except ValueError:
                        continue
            for user_id, profile in self._special_targets.items():
                if (profile.username or "").strip().lstrip(
                    "@"
                ).casefold() == normalized:
                    try:
                        return int(user_id)
                    except ValueError:
                        continue
            for user_id, profile in self._close_contacts.items():
                if (profile.username or "").strip().lstrip(
                    "@"
                ).casefold() == normalized:
                    try:
                        return int(user_id)
                    except ValueError:
                        continue
        return None

    async def build_instruction(self, user_id: int | None) -> str:
        if user_id is None:
            return ""
        profile = await self.get_profile(user_id)
        close_contact = await self.get_close_contact(user_id)
        if profile.message_count <= 0:
            if close_contact is None:
                return ""

        hints: list[str] = []
        if close_contact is not None:
            relation_label = _relation_label(close_contact.relation_type)
            hints.append(f"The owner marked this person as {relation_label}.")
            if close_contact.comment:
                hints.append(
                    f"Persistent note about communication: {close_contact.comment}"
                )
        if profile.typical_tone == "informal":
            hints.append(
                "The current chat partner usually writes informally, so relaxed simple wording fits better."
            )
        elif profile.typical_tone == "formal":
            hints.append(
                "The current chat partner often sounds more formal, so a cleaner and slightly tidier reply fits."
            )

        if any(topic in TECH_MARKERS for topic in profile.common_topics):
            hints.append(
                "This user often discusses technical topics, so a slightly more precise reply can fit."
            )
        else:
            hints.append(
                "Prefer an easy conversational explanation over a dry technical answer."
            )

        if profile.interaction_frequency >= 1.5:
            hints.append(
                "This looks like a recurring chat partner, so a familiar conversational tone is fine."
            )

        return " ".join(hints[:4])

    async def get_special_target(
        self, user_id: int | None
    ) -> SpecialTargetSettings | None:
        if user_id is None:
            return None
        async with self._lock:
            target = self._special_targets.get(str(user_id))
            return copy.deepcopy(target) if target is not None else None

    async def get_special_targets_snapshot(self) -> dict[str, SpecialTargetSettings]:
        async with self._lock:
            return copy.deepcopy(self._special_targets)

    async def get_close_contact(
        self, user_id: int | None
    ) -> CloseContactProfile | None:
        if user_id is None:
            return None
        async with self._lock:
            value = self._close_contacts.get(str(user_id))
            return copy.deepcopy(value) if value is not None else None

    async def get_close_contacts_snapshot(self) -> dict[str, CloseContactProfile]:
        async with self._lock:
            return copy.deepcopy(self._close_contacts)

    async def upsert_special_target(
        self, user_id: int, patch: SpecialTargetPatch
    ) -> SpecialTargetSettings:
        async with self._lock:
            key = str(user_id)
            current = self._special_targets.get(key, SpecialTargetSettings())
            updated = SpecialTargetSettings(
                enabled=current.enabled
                if patch.enabled is None
                else bool(patch.enabled),
                human_like=current.human_like
                if patch.human_like is None
                else bool(patch.human_like),
                bypass_delay=current.bypass_delay
                if patch.bypass_delay is None
                else bool(patch.bypass_delay),
                bypass_probability=(
                    current.bypass_probability
                    if patch.bypass_probability is None
                    else bool(patch.bypass_probability)
                ),
                bypass_cooldown=current.bypass_cooldown
                if patch.bypass_cooldown is None
                else bool(patch.bypass_cooldown),
                reply_only_questions=(
                    current.reply_only_questions
                    if patch.reply_only_questions is None
                    else bool(patch.reply_only_questions)
                ),
                require_owner_mention_or_context=(
                    current.require_owner_mention_or_context
                    if patch.require_owner_mention_or_context is None
                    else bool(patch.require_owner_mention_or_context)
                ),
                allowed_chat_ids=(
                    list(current.allowed_chat_ids)
                    if patch.allowed_chat_ids is None
                    else self._normalize_chat_ids(patch.allowed_chat_ids)
                ),
                username=patch.username
                if patch.username is not None
                else current.username,
                chat_overrides=patch.chat_overrides
                if patch.chat_overrides is not None
                else dict(current.chat_overrides),
            )
            self._special_targets[key] = updated
            await self._write_locked()
            return copy.deepcopy(updated)

    async def remove_special_target(self, user_id: int) -> bool:
        async with self._lock:
            removed = self._special_targets.pop(str(user_id), None)
            if removed is None:
                return False
            await self._write_locked()
            return True

    async def upsert_close_contact(
        self, user_id: int, patch: CloseContactPatch
    ) -> CloseContactProfile:
        async with self._lock:
            key = str(user_id)
            current = self._close_contacts.get(key, CloseContactProfile())
            updated = CloseContactProfile(
                relation_type=_normalize_relation_type(
                    current.relation_type
                    if patch.relation_type is None
                    else str(patch.relation_type)
                ),
                username=patch.username
                if patch.username is not None
                else current.username,
                comment=(
                    patch.comment if patch.comment is not None else current.comment
                ).strip(),
                updated_at=patch.updated_at
                if patch.updated_at is not None
                else _now_iso(),
            )
            self._close_contacts[key] = updated
            await self._write_locked()
            return copy.deepcopy(updated)

    async def remove_close_contact(self, user_id: int) -> bool:
        async with self._lock:
            removed = self._close_contacts.pop(str(user_id), None)
            if removed is None:
                return False
            await self._write_locked()
            return True

    def _from_dict(self, data: dict) -> UserProfile:
        return UserProfile(
            username=data.get("username"),
            message_count=int(data.get("message_count", 0)),
            avg_message_length=float(data.get("avg_message_length", 0.0)),
            typical_tone=str(data.get("typical_tone", "neutral") or "neutral"),
            common_topics=[str(item) for item in (data.get("common_topics") or [])][:8],
            interaction_frequency=float(data.get("interaction_frequency", 0.0)),
            last_interaction_time=data.get("last_interaction_time"),
        )

    def _special_target_from_dict(self, data: dict) -> SpecialTargetSettings:
        return SpecialTargetSettings(
            enabled=bool(data.get("enabled", True)),
            human_like=bool(data.get("human_like", True)),
            bypass_delay=bool(data.get("bypass_delay", True)),
            bypass_probability=bool(data.get("bypass_probability", True)),
            bypass_cooldown=bool(data.get("bypass_cooldown", True)),
            reply_only_questions=bool(data.get("reply_only_questions", False)),
            require_owner_mention_or_context=bool(
                data.get("require_owner_mention_or_context", False)
            ),
            allowed_chat_ids=self._normalize_chat_ids(
                data.get("allowed_chat_ids") or []
            ),
            username=data.get("username"),
            chat_overrides={
                str(k): {fk: bool(fv) for fk, fv in v.items() if isinstance(fv, bool)}
                for k, v in (data.get("chat_overrides") or {}).items()
                if isinstance(v, dict)
            },
        )

    def _close_contact_from_dict(self, data: dict) -> CloseContactProfile:
        return CloseContactProfile(
            relation_type=_normalize_relation_type(
                data.get("relation_type", "LESS_CLOSE")
            ),
            username=data.get("username"),
            comment=str(data.get("comment", "") or "").strip(),
            updated_at=data.get("updated_at"),
        )

    async def _write_locked(self) -> None:
        await atomic_write_json(
            self._path,
            {
                "profiles": {
                    user_id: asdict(profile)
                    for user_id, profile in self._profiles.items()
                },
                "special_targets": {
                    user_id: asdict(target)
                    for user_id, target in self._special_targets.items()
                },
                "close_contacts": {
                    user_id: asdict(contact)
                    for user_id, contact in self._close_contacts.items()
                },
            },
            indent=2,
        )

    def _split_payload(self, payload: object) -> tuple[dict, dict, dict]:
        if not isinstance(payload, dict):
            return {}, {}, {}
        if (
            "profiles" in payload
            or "special_targets" in payload
            or "close_contacts" in payload
        ):
            profiles = payload.get("profiles") or {}
            special_targets = payload.get("special_targets") or {}
            close_contacts = payload.get("close_contacts") or {}
            return (
                profiles if isinstance(profiles, dict) else {},
                special_targets if isinstance(special_targets, dict) else {},
                close_contacts if isinstance(close_contacts, dict) else {},
            )
        return payload, {}, {}

    def _normalize_chat_ids(self, values: list[int] | list[str]) -> list[int]:
        normalized: list[int] = []
        seen: set[int] = set()
        for value in values:
            try:
                chat_id = int(value)
            except (TypeError, ValueError):
                continue
            if chat_id in seen:
                continue
            seen.add(chat_id)
            normalized.append(chat_id)
        return normalized


def _running_average(current: float, value: float, count: int) -> float:
    if count <= 1:
        return float(value)
    return current + ((float(value) - current) / float(count))


def _detect_tone(current_tone: str, text: str) -> str:
    lowered = text.casefold()
    formal_score = sum(1 for marker in FORMAL_MARKERS if marker in lowered)
    informal_score = sum(1 for marker in INFORMAL_MARKERS if marker in lowered)
    if informal_score > formal_score:
        return "informal"
    if formal_score > informal_score:
        return "formal"
    return current_tone or "neutral"


def _extract_topics(text: str) -> list[str]:
    topics: list[str] = []
    seen: set[str] = set()
    for token in WORD_RE.findall((text or "").casefold()):
        if token in STOPWORDS or len(token) < 3:
            continue
        if token in seen:
            continue
        seen.add(token)
        topics.append(token)
        if len(topics) >= 5:
            break
    return topics


def _normalize_relation_type(value: str | None) -> str:
    normalized = str(value or "LESS_CLOSE").strip().upper()
    aliases = {
        "CLOSE": "CLOSE",
        "LESS_CLOSE": "LESS_CLOSE",
        "LESS": "LESS_CLOSE",
        "PLAN": "PLANS",
        "PLANS": "PLANS",
        "BUSINESS": "BUSINESS",
        "WORK": "BUSINESS",
        "DEAL": "BUSINESS",
    }
    return aliases.get(normalized, "LESS_CLOSE")


def _relation_label(value: str | None) -> str:
    labels = {
        "CLOSE": "a close person",
        "LESS_CLOSE": "a familiar but less close person",
        "PLANS": "a person important for plans and coordination",
        "BUSINESS": "a person for serious and business-like communication",
    }
    return labels.get(_normalize_relation_type(value), "a familiar person")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _merge_topics(existing: list[str], incoming: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for token in [*(existing or []), *(incoming or [])]:
        cleaned = str(token).strip().casefold()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        merged.append(cleaned)
        if len(merged) >= 8:
            break
    return merged


def _compute_interaction_frequency(
    profile: UserProfile, current_time: datetime
) -> float:
    previous = _parse_iso(profile.last_interaction_time)
    if previous is None:
        return 0.0
    delta_hours = max(1.0, (current_time - previous).total_seconds() / 3600.0)
    raw_frequency = 24.0 / delta_hours
    if profile.interaction_frequency <= 0:
        return min(raw_frequency, 24.0)
    return round(
        (profile.interaction_frequency * 0.7) + (min(raw_frequency, 24.0) * 0.3), 3
    )


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
