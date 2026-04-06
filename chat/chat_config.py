from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from infra.json_atomic import atomic_write_json

from config.settings import AppConfig
from state.state import ChatReplySettings

CHAT_PRIORITY_HIGH = "HIGH_PRIORITY"
CHAT_PRIORITY_NORMAL = "NORMAL_PRIORITY"
CHAT_PRIORITY_LOW = "LOW_PRIORITY"
CHAT_PRIORITY_PASSIVE = "PASSIVE"
CHAT_PRIORITIES = {
    CHAT_PRIORITY_HIGH,
    CHAT_PRIORITY_NORMAL,
    CHAT_PRIORITY_LOW,
    CHAT_PRIORITY_PASSIVE,
}


@dataclass(slots=True)
class ChatConfig:
    auto_reply_enabled: bool | None = None
    context_window_size: int | None = None
    summary_enabled: bool | None = None
    cross_chat_allowed: bool | None = None
    reply_probability: float | None = None
    reply_cooldown_seconds: int | None = None
    hourly_limit: int | None = None
    min_delay_seconds: int | None = None
    max_delay_seconds: int | None = None
    priority: str | None = None


@dataclass(slots=True)
class ResolvedChatConfig:
    auto_reply_enabled: bool
    context_window_size: int
    summary_enabled: bool
    cross_chat_allowed: bool
    reply_probability: float
    reply_cooldown_seconds: int
    hourly_limit: int
    min_delay_seconds: int
    max_delay_seconds: int
    priority: str


class ChatConfigStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._data: dict[str, ChatConfig] = {}

    async def load(self) -> dict[str, ChatConfig]:
        async with self._lock:
            if not self._path.exists():
                await self._write_locked()
                return copy.deepcopy(self._data)

            try:
                raw = await asyncio.to_thread(self._path.read_text, encoding="utf-8")
                payload = json.loads(raw or "{}")
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                payload = {}

            self._data = {
                str(chat_id): self._from_dict(item)
                for chat_id, item in (payload or {}).items()
                if item is not None
            }
            await self._write_locked()
            return copy.deepcopy(self._data)

    async def get_snapshot(self) -> dict[str, ChatConfig]:
        async with self._lock:
            return copy.deepcopy(self._data)

    async def get_chat(self, chat_id: int) -> ChatConfig:
        async with self._lock:
            return copy.deepcopy(self._data.get(str(chat_id), ChatConfig()))

    async def resolve_chat(
        self,
        chat_id: int,
        *,
        config: AppConfig,
        state_settings: ChatReplySettings | None,
    ) -> ResolvedChatConfig:
        async with self._lock:
            stored = self._data.get(str(chat_id), ChatConfig())
            fallback = state_settings or ChatReplySettings(
                enabled=True,
                reply_probability=config.default_reply_probability,
                cooldown_seconds=config.default_reply_cooldown_seconds,
                min_delay_seconds=config.default_reply_min_delay_seconds,
                max_delay_seconds=config.default_reply_max_delay_seconds,
                max_replies_per_hour=config.default_reply_hourly_limit,
                allow_bots=config.default_allow_bot_replies,
                min_message_length=config.default_reply_min_message_length,
            )
            priority = self._normalize_priority(stored.priority)
            auto_reply_enabled = (
                stored.auto_reply_enabled
                if stored.auto_reply_enabled is not None
                else fallback.enabled
            )
            reply_probability = self._clamp_probability(
                stored.reply_probability
                if stored.reply_probability is not None
                else fallback.reply_probability
            )
            reply_cooldown_seconds = max(
                0,
                stored.reply_cooldown_seconds
                if stored.reply_cooldown_seconds is not None
                else fallback.cooldown_seconds,
            )
            hourly_limit = max(
                1,
                stored.hourly_limit
                if stored.hourly_limit is not None
                else fallback.max_replies_per_hour,
            )
            min_delay_seconds = max(
                0,
                stored.min_delay_seconds
                if stored.min_delay_seconds is not None
                else fallback.min_delay_seconds,
            )
            max_delay_seconds = max(
                min_delay_seconds,
                stored.max_delay_seconds
                if stored.max_delay_seconds is not None
                else fallback.max_delay_seconds,
            )

            if priority == CHAT_PRIORITY_HIGH:
                reply_probability = self._clamp_probability(reply_probability * 1.2)
                reply_cooldown_seconds = max(20, int(reply_cooldown_seconds * 0.65))
                hourly_limit = max(hourly_limit, int(hourly_limit * 1.4))
                min_delay_seconds = max(0, int(min_delay_seconds * 0.7))
                max_delay_seconds = max(min_delay_seconds, int(max_delay_seconds * 0.8))
            elif priority == CHAT_PRIORITY_LOW:
                reply_probability = self._clamp_probability(reply_probability * 0.55)
                reply_cooldown_seconds = max(
                    reply_cooldown_seconds, int(reply_cooldown_seconds * 1.6)
                )
                hourly_limit = max(
                    1, min(hourly_limit, max(1, int(hourly_limit * 0.6)))
                )
                min_delay_seconds = max(min_delay_seconds, int(min_delay_seconds * 1.4))
                max_delay_seconds = max(min_delay_seconds, int(max_delay_seconds * 1.5))
            elif priority == CHAT_PRIORITY_PASSIVE:
                auto_reply_enabled = False

            return ResolvedChatConfig(
                auto_reply_enabled=auto_reply_enabled,
                context_window_size=max(
                    8, stored.context_window_size or config.default_context_window_size
                ),
                summary_enabled=stored.summary_enabled
                if stored.summary_enabled is not None
                else config.default_summary_enabled,
                cross_chat_allowed=stored.cross_chat_allowed
                if stored.cross_chat_allowed is not None
                else config.default_cross_chat_allowed,
                reply_probability=reply_probability,
                reply_cooldown_seconds=reply_cooldown_seconds,
                hourly_limit=hourly_limit,
                min_delay_seconds=min_delay_seconds,
                max_delay_seconds=max_delay_seconds,
                priority=priority,
            )

    async def upsert_chat(
        self, chat_id: int, patch: ChatConfig
    ) -> dict[str, ChatConfig]:
        async with self._lock:
            current = self._data.get(str(chat_id), ChatConfig())
            updated = ChatConfig(
                auto_reply_enabled=patch.auto_reply_enabled
                if patch.auto_reply_enabled is not None
                else current.auto_reply_enabled,
                context_window_size=patch.context_window_size
                if patch.context_window_size is not None
                else current.context_window_size,
                summary_enabled=patch.summary_enabled
                if patch.summary_enabled is not None
                else current.summary_enabled,
                cross_chat_allowed=patch.cross_chat_allowed
                if patch.cross_chat_allowed is not None
                else current.cross_chat_allowed,
                reply_probability=patch.reply_probability
                if patch.reply_probability is not None
                else current.reply_probability,
                reply_cooldown_seconds=(
                    patch.reply_cooldown_seconds
                    if patch.reply_cooldown_seconds is not None
                    else current.reply_cooldown_seconds
                ),
                hourly_limit=patch.hourly_limit
                if patch.hourly_limit is not None
                else current.hourly_limit,
                min_delay_seconds=patch.min_delay_seconds
                if patch.min_delay_seconds is not None
                else current.min_delay_seconds,
                max_delay_seconds=patch.max_delay_seconds
                if patch.max_delay_seconds is not None
                else current.max_delay_seconds,
                priority=patch.priority
                if patch.priority is not None
                else current.priority,
            )
            self._data[str(chat_id)] = updated
            await self._write_locked()
            return copy.deepcopy(self._data)

    def _from_dict(self, data: dict) -> ChatConfig:
        return ChatConfig(
            auto_reply_enabled=self._as_optional_bool(data.get("auto_reply_enabled")),
            context_window_size=self._as_optional_int(data.get("context_window_size")),
            summary_enabled=self._as_optional_bool(data.get("summary_enabled")),
            cross_chat_allowed=self._as_optional_bool(data.get("cross_chat_allowed")),
            reply_probability=self._as_optional_float(data.get("reply_probability")),
            reply_cooldown_seconds=self._as_optional_int(
                data.get("reply_cooldown_seconds")
            ),
            hourly_limit=self._as_optional_int(data.get("hourly_limit")),
            min_delay_seconds=self._as_optional_int(data.get("min_delay_seconds")),
            max_delay_seconds=self._as_optional_int(data.get("max_delay_seconds")),
            priority=self._normalize_priority(data.get("priority")),
        )

    async def _write_locked(self) -> None:
        await atomic_write_json(
            self._path,
            {chat_id: asdict(item) for chat_id, item in self._data.items()},
            indent=2,
        )

    def _as_optional_bool(self, value: object) -> bool | None:
        if value is None:
            return None
        return bool(value)

    def _as_optional_int(self, value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _as_optional_float(self, value: object) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _clamp_probability(self, value: float) -> float:
        return max(0.0, min(1.0, value))

    def _normalize_priority(self, value: object) -> str:
        cleaned = str(value or CHAT_PRIORITY_NORMAL).strip().upper()
        if cleaned not in CHAT_PRIORITIES:
            return CHAT_PRIORITY_NORMAL
        return cleaned
