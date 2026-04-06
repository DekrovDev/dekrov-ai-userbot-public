from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from infra.json_atomic import atomic_write_json
from infra.state_sqlite import StateSQLite


@dataclass(slots=True)
class RateLimitState:
    model: str | None = None
    remaining_requests: str | None = None
    request_limit: str | None = None
    remaining_tokens: str | None = None
    token_limit: str | None = None
    retry_after: str | None = None
    last_updated: str | None = None


@dataclass(slots=True)
class ChatReplySettings:
    enabled: bool = True
    reply_probability: float = 0.35
    cooldown_seconds: int = 900
    min_delay_seconds: int = 25
    max_delay_seconds: int = 90
    max_replies_per_hour: int = 4
    allow_bots: bool = False
    min_message_length: int = 8


@dataclass(slots=True)
class ChatRuntimeState:
    last_reply_at: str | None = None
    recent_reply_timestamps: list[str] = field(default_factory=list)
    last_message_fingerprint: str | None = None
    last_message_at: str | None = None
    replies_sent_total: int = 0
    consecutive_ai_replies: int = 0
    last_reply_target_user_id: int | None = None
    user_reply_timestamps: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class PersistentState:
    active_model: str
    judge_model: str
    available_models: list[str] = field(default_factory=list)
    enabled_models: dict[str, bool] = field(default_factory=dict)
    fallback_enabled: bool = False
    ai_mode_enabled: bool = True
    response_style_mode: str = "NORMAL"
    command_mode_enabled: bool = True
    trigger_aliases: list[str] = field(default_factory=list)
    dot_prefix_required: bool = True
    auto_reply_enabled: bool = False
    reply_audience_mode: str = "ALL"
    reply_audience_flags: dict[str, bool] = field(
        default_factory=lambda: {
            "STRANGERS": True,
            "KNOWN": True,
            "FRIENDS": True,
            "BUSINESS": True,
        }
    )
    chat_bot_allowed_user_ids: list[int] = field(default_factory=list)
    reply_only_questions: bool = True
    chat_bot_owner_only: bool = True
    require_owner_mention_or_context: bool = True
    allowed_chat_ids: list[int] = field(default_factory=list)
    blocked_chat_ids: list[int] = field(default_factory=list)
    chat_settings: dict[str, ChatReplySettings] = field(default_factory=dict)
    chat_runtime: dict[str, ChatRuntimeState] = field(default_factory=dict)
    last_limits: RateLimitState = field(default_factory=RateLimitState)
    model_limits: dict[str, RateLimitState] = field(default_factory=dict)
    models_refreshed_at: str | None = None
    updated_at: str | None = None
    visitor_mode_enabled: bool = False

    @property
    def mode(self) -> str:
        return "fallback" if self.fallback_enabled else "manual"


class StateStore:
    def __init__(
        self,
        path: Path,
        default_models: list[str],
        default_active_model: str,
        default_judge_model: str,
        default_enabled_models: dict[str, bool],
        default_trigger_aliases: list[str],
        default_dot_prefix_required: bool,
        default_command_mode_enabled: bool,
        default_auto_reply_enabled: bool,
        default_fallback_enabled: bool,
        db_path: Path | None = None,
    ) -> None:
        self._path = path
        self._db_path = db_path
        self._lock = asyncio.Lock()
        self._sqlite: StateSQLite | None = None
        self._default_models = self._dedupe_models(default_models)
        self._default_active_model = default_active_model
        self._default_judge_model = default_judge_model
        self._default_enabled_models = dict(default_enabled_models)
        self._default_trigger_aliases = self._normalize_aliases(default_trigger_aliases)
        self._default_dot_prefix_required = default_dot_prefix_required
        self._default_command_mode_enabled = default_command_mode_enabled
        self._default_auto_reply_enabled = default_auto_reply_enabled
        self._default_fallback_enabled = default_fallback_enabled
        self._state = self._default_state()

    async def set_chat_bot_owner_only(self, enabled: bool) -> PersistentState:
        async with self._lock:
            self._state.chat_bot_owner_only = enabled
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def add_chat_bot_allowed_user(self, user_id: int) -> PersistentState:
        async with self._lock:
            if user_id not in self._state.chat_bot_allowed_user_ids:
                self._state.chat_bot_allowed_user_ids.append(user_id)
            self._state.chat_bot_allowed_user_ids = sorted(
                set(self._state.chat_bot_allowed_user_ids)
            )
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def remove_chat_bot_allowed_user(self, user_id: int) -> PersistentState:
        async with self._lock:
            self._state.chat_bot_allowed_user_ids = [
                value
                for value in self._state.chat_bot_allowed_user_ids
                if value != user_id
            ]
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def clear_chat_bot_allowed_users(self) -> PersistentState:
        async with self._lock:
            self._state.chat_bot_allowed_user_ids = []
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def load(self) -> PersistentState:
        async with self._lock:
            # Инициализируем SQLite если указан db_path
            if self._db_path and not self._sqlite:
                self._sqlite = StateSQLite(self._db_path)

            # Пробуем загрузить из SQLite (если есть)
            if self._sqlite:
                loaded = self._load_from_sqlite()
                if loaded:
                    self._normalize_model_state_locked()
                    await self._write_locked()  # Dual-write: сохраняем в JSON
                    return copy.deepcopy(self._state)

            # Фоллбэк на JSON
            if not self._path.exists():
                await self._write_locked()
                return copy.deepcopy(self._state)

            try:
                raw = await asyncio.to_thread(self._path.read_text, encoding="utf-8")
                self._state = self._from_dict(json.loads(raw or "{}"))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                self._state = self._default_state()

            self._normalize_model_state_locked()
            await self._write_locked()
            return copy.deepcopy(self._state)

    async def get_snapshot(self) -> PersistentState:
        async with self._lock:
            return copy.deepcopy(self._state)

    async def set_active_model(self, model: str) -> PersistentState:
        async with self._lock:
            self._ensure_model_known_locked(model)
            self._state.enabled_models[model] = True
            self._state.active_model = model
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def set_judge_model(self, model: str) -> PersistentState:
        async with self._lock:
            self._ensure_model_known_locked(model)
            self._state.enabled_models[model] = True
            self._state.judge_model = model
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def set_models_and_active(
        self, models: list[str], active_model: str
    ) -> PersistentState:
        async with self._lock:
            self._sync_models_locked(models)
            self._ensure_model_known_locked(active_model)
            self._state.enabled_models[active_model] = True
            self._state.active_model = active_model
            self._normalize_model_state_locked()
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def sync_model_pool(self, models: list[str]) -> PersistentState:
        async with self._lock:
            self._sync_models_locked(models)
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def set_model_enabled(
        self, model: str, enabled: bool
    ) -> tuple[PersistentState, bool]:
        async with self._lock:
            self._ensure_model_known_locked(model)
            if (
                not enabled
                and self._enabled_model_count_locked() <= 1
                and self._state.enabled_models.get(model, True)
            ):
                return copy.deepcopy(self._state), False

            self._state.enabled_models[model] = enabled
            self._normalize_model_state_locked()
            await self._touch_and_write_locked()
            changed = self._state.enabled_models.get(model, True) == enabled
            return copy.deepcopy(self._state), changed

    async def set_fallback_enabled(self, enabled: bool) -> PersistentState:
        async with self._lock:
            self._state.fallback_enabled = enabled
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def set_ai_mode_enabled(self, enabled: bool) -> PersistentState:
        async with self._lock:
            self._state.ai_mode_enabled = enabled
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def set_response_style_mode(self, mode: str) -> PersistentState:
        async with self._lock:
            normalized = str(mode or "NORMAL").strip().upper()
            if normalized not in {"SHORT", "NORMAL", "DETAILED", "HUMANLIKE", "SAFE"}:
                normalized = "NORMAL"
            self._state.response_style_mode = normalized
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def set_command_mode_enabled(self, enabled: bool) -> PersistentState:
        async with self._lock:
            self._state.command_mode_enabled = enabled
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def set_trigger_aliases(self, aliases: list[str]) -> PersistentState:
        async with self._lock:
            normalized = self._normalize_aliases(aliases) or list(
                self._default_trigger_aliases
            )
            self._state.trigger_aliases = normalized
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def set_dot_prefix_required(self, enabled: bool) -> PersistentState:
        async with self._lock:
            self._state.dot_prefix_required = enabled
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def set_auto_reply_enabled(self, enabled: bool) -> PersistentState:
        async with self._lock:
            self._state.auto_reply_enabled = enabled
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def set_reply_audience_mode(self, mode: str) -> PersistentState:
        async with self._lock:
            normalized = str(mode or "ALL").strip().upper()
            if normalized not in {"ALL", "FRIENDS", "KNOWN", "STRANGERS", "BUSINESS"}:
                normalized = "ALL"
            self._state.reply_audience_mode = normalized
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def toggle_audience_flag(self, category: str) -> PersistentState:
        async with self._lock:
            normalized = str(category or "").strip().upper()
            if normalized not in {"STRANGERS", "KNOWN", "FRIENDS", "BUSINESS"}:
                return copy.deepcopy(self._state)
            flags = dict(self._state.reply_audience_flags)
            flags[normalized] = not flags.get(normalized, True)
            self._state.reply_audience_flags = flags
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def set_reply_only_questions(self, enabled: bool) -> PersistentState:
        async with self._lock:
            self._state.reply_only_questions = enabled
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def set_require_owner_mention_or_context(
        self, enabled: bool
    ) -> PersistentState:
        async with self._lock:
            self._state.require_owner_mention_or_context = enabled
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def set_visitor_mode_enabled(self, enabled: bool) -> PersistentState:
        async with self._lock:
            self._state.visitor_mode_enabled = enabled
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def allow_chat(self, chat_id: int) -> PersistentState:
        async with self._lock:
            if chat_id not in self._state.allowed_chat_ids:
                self._state.allowed_chat_ids.append(chat_id)
            self._state.allowed_chat_ids = self._dedupe_chat_ids(
                self._state.allowed_chat_ids
            )
            self._state.blocked_chat_ids = [
                value for value in self._state.blocked_chat_ids if value != chat_id
            ]
            self._ensure_chat_settings_locked(chat_id)
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def block_chat(self, chat_id: int) -> PersistentState:
        async with self._lock:
            if chat_id not in self._state.blocked_chat_ids:
                self._state.blocked_chat_ids.append(chat_id)
            self._state.blocked_chat_ids = self._dedupe_chat_ids(
                self._state.blocked_chat_ids
            )
            self._state.allowed_chat_ids = [
                value for value in self._state.allowed_chat_ids if value != chat_id
            ]
            self._ensure_chat_settings_locked(chat_id)
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def remove_allowed_chat(self, chat_id: int) -> PersistentState:
        async with self._lock:
            self._state.allowed_chat_ids = [
                value for value in self._state.allowed_chat_ids if value != chat_id
            ]
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def remove_blocked_chat(self, chat_id: int) -> PersistentState:
        async with self._lock:
            self._state.blocked_chat_ids = [
                value for value in self._state.blocked_chat_ids if value != chat_id
            ]
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def set_chat_probability(self, chat_id: int, value: float) -> PersistentState:
        value = max(0.0, min(1.0, value))
        async with self._lock:
            settings = self._ensure_chat_settings_locked(chat_id)
            settings.reply_probability = value
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def set_chat_cooldown(self, chat_id: int, seconds: int) -> PersistentState:
        seconds = max(0, seconds)
        async with self._lock:
            settings = self._ensure_chat_settings_locked(chat_id)
            settings.cooldown_seconds = seconds
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def set_chat_delay(
        self, chat_id: int, min_seconds: int, max_seconds: int
    ) -> PersistentState:
        min_seconds = max(0, min_seconds)
        max_seconds = max(min_seconds, max_seconds)
        async with self._lock:
            settings = self._ensure_chat_settings_locked(chat_id)
            settings.min_delay_seconds = min_seconds
            settings.max_delay_seconds = max_seconds
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def set_chat_hour_limit(self, chat_id: int, value: int) -> PersistentState:
        value = max(1, value)
        async with self._lock:
            settings = self._ensure_chat_settings_locked(chat_id)
            settings.max_replies_per_hour = value
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def update_limits(self, limits: RateLimitState) -> PersistentState:
        async with self._lock:
            if limits.model:
                self._state.model_limits[limits.model] = limits
            self._state.last_limits = limits
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def update_model_limits(self, limits: RateLimitState) -> PersistentState:
        return await self.update_limits(limits)

    async def record_auto_reply(
        self,
        chat_id: int,
        fingerprint: str,
        replied_at: str,
        target_user_id: int | None = None,
    ) -> PersistentState:
        async with self._lock:
            runtime = self._ensure_chat_runtime_locked(chat_id)
            now = self._parse_iso(replied_at)
            recent: list[str] = []

            for timestamp in runtime.recent_reply_timestamps:
                parsed = self._parse_iso(timestamp)
                if (
                    parsed is not None
                    and now is not None
                    and now - parsed <= timedelta(hours=1)
                ):
                    recent.append(timestamp)

            recent.append(replied_at)
            runtime.recent_reply_timestamps = recent
            runtime.last_reply_at = replied_at
            runtime.last_message_fingerprint = fingerprint
            runtime.last_message_at = replied_at
            runtime.replies_sent_total += 1
            runtime.consecutive_ai_replies += 1
            runtime.last_reply_target_user_id = target_user_id
            if target_user_id is not None:
                runtime.user_reply_timestamps[str(target_user_id)] = replied_at
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    async def record_owner_message(
        self, chat_id: int, recorded_at: str
    ) -> PersistentState:
        async with self._lock:
            runtime = self._ensure_chat_runtime_locked(chat_id)
            runtime.consecutive_ai_replies = 0
            runtime.last_reply_target_user_id = None
            runtime.last_message_at = recorded_at
            await self._touch_and_write_locked()
            return copy.deepcopy(self._state)

    def _default_state(self) -> PersistentState:
        enabled_models = {
            model: bool(self._default_enabled_models.get(model, True))
            for model in self._default_models
        }
        active_model = (
            self._default_active_model
            if self._default_active_model in self._default_models
            else self._default_models[0]
        )
        judge_model = (
            self._default_judge_model
            if self._default_judge_model in self._default_models
            else active_model
        )
        enabled_models[active_model] = True
        enabled_models[judge_model] = True
        return PersistentState(
            active_model=active_model,
            judge_model=judge_model,
            available_models=list(self._default_models),
            enabled_models=enabled_models,
            fallback_enabled=self._default_fallback_enabled,
            ai_mode_enabled=True,
            response_style_mode="NORMAL",
            command_mode_enabled=self._default_command_mode_enabled,
            trigger_aliases=list(self._default_trigger_aliases),
            dot_prefix_required=self._default_dot_prefix_required,
            auto_reply_enabled=self._default_auto_reply_enabled,
            reply_audience_mode="ALL",
            chat_bot_owner_only=True,
            chat_bot_allowed_user_ids=[],
            reply_only_questions=True,
            require_owner_mention_or_context=True,
            models_refreshed_at=self._now_iso(),
            updated_at=self._now_iso(),
            visitor_mode_enabled=False,
        )

    def _from_dict(self, data: dict) -> PersistentState:
        available_models = self._dedupe_models(
            data.get("available_models") or self._default_models
        )
        enabled_models_raw = data.get("enabled_models") or {}
        enabled_models = {
            model: bool(
                enabled_models_raw.get(
                    model, self._default_enabled_models.get(model, True)
                )
            )
            for model in available_models
        }
        active_model = data.get("active_model") or self._default_active_model
        judge_model = data.get("judge_model") or self._default_judge_model

        chat_settings = {
            str(key): self._chat_settings_from_dict(value)
            for key, value in (data.get("chat_settings") or {}).items()
        }
        chat_runtime = {
            str(key): self._chat_runtime_from_dict(value)
            for key, value in (data.get("chat_runtime") or {}).items()
        }
        last_limits = self._rate_limit_from_dict(data.get("last_limits") or {})
        model_limits = {
            str(key): self._rate_limit_from_dict(value)
            for key, value in (data.get("model_limits") or {}).items()
        }

        state = PersistentState(
            chat_bot_owner_only=bool(data.get("chat_bot_owner_only", True)),
            active_model=active_model,
            judge_model=judge_model,
            available_models=available_models,
            enabled_models=enabled_models,
            fallback_enabled=bool(
                data.get("fallback_enabled", self._default_fallback_enabled)
            ),
            ai_mode_enabled=bool(data.get("ai_mode_enabled", True)),
            response_style_mode=str(
                data.get("response_style_mode", "NORMAL") or "NORMAL"
            )
            .strip()
            .upper(),
            command_mode_enabled=bool(
                data.get("command_mode_enabled", self._default_command_mode_enabled)
            ),
            trigger_aliases=self._normalize_aliases(
                data.get("trigger_aliases") or self._default_trigger_aliases
            ),
            dot_prefix_required=bool(
                data.get("dot_prefix_required", self._default_dot_prefix_required)
            ),
            auto_reply_enabled=bool(
                data.get("auto_reply_enabled", self._default_auto_reply_enabled)
            ),
            reply_audience_mode=str(data.get("reply_audience_mode", "ALL") or "ALL")
            .strip()
            .upper(),
            reply_audience_flags=self._normalize_audience_flags(
                data.get("reply_audience_flags")
            ),
            reply_only_questions=bool(data.get("reply_only_questions", True)),
            require_owner_mention_or_context=bool(
                data.get("require_owner_mention_or_context", True)
            ),
            allowed_chat_ids=self._dedupe_chat_ids(data.get("allowed_chat_ids") or []),
            blocked_chat_ids=self._dedupe_chat_ids(data.get("blocked_chat_ids") or []),
            chat_settings=chat_settings,
            chat_runtime=chat_runtime,
            last_limits=last_limits,
            model_limits=model_limits,
            models_refreshed_at=data.get("models_refreshed_at")
            or data.get("updated_at")
            or self._now_iso(),
            updated_at=data.get("updated_at") or self._now_iso(),
            chat_bot_allowed_user_ids=sorted(
                set(int(x) for x in (data.get("chat_bot_allowed_user_ids") or []))
            ),
            visitor_mode_enabled=bool(data.get("visitor_mode_enabled", False)),
        )
        self._state = state
        self._normalize_model_state_locked()
        return self._state

    def _sync_models_locked(self, models: list[str]) -> None:
        normalized = self._dedupe_models(models) or list(self._default_models)
        existing_enabled = dict(self._state.enabled_models)
        existing_limits = dict(self._state.model_limits)
        self._state.available_models = normalized
        self._state.enabled_models = {
            model: bool(
                existing_enabled.get(
                    model, self._default_enabled_models.get(model, True)
                )
            )
            for model in normalized
        }
        self._state.model_limits = {
            model: existing_limits[model]
            for model in normalized
            if model in existing_limits
        }
        self._state.models_refreshed_at = self._now_iso()
        self._normalize_model_state_locked()

    def _normalize_model_state_locked(self) -> None:
        if not self._state.available_models:
            self._state.available_models = list(self._default_models)

        for model in self._state.available_models:
            self._state.enabled_models.setdefault(
                model, self._default_enabled_models.get(model, True)
            )

        self._state.enabled_models = {
            model: bool(
                self._state.enabled_models.get(
                    model, self._default_enabled_models.get(model, True)
                )
            )
            for model in self._state.available_models
        }
        self._state.model_limits = {
            model: value
            for model, value in self._state.model_limits.items()
            if model in self._state.available_models
        }

        if self._state.active_model not in self._state.available_models:
            self._state.active_model = self._pick_preferred_enabled_model_locked(
                self._default_active_model
            )
        if not self._state.enabled_models.get(self._state.active_model, True):
            self._state.active_model = self._pick_preferred_enabled_model_locked(
                self._default_active_model
            )
            self._state.enabled_models[self._state.active_model] = True

        if self._state.judge_model not in self._state.available_models:
            self._state.judge_model = self._pick_preferred_enabled_model_locked(
                self._default_judge_model
            )
        if not self._state.enabled_models.get(self._state.judge_model, True):
            self._state.judge_model = self._pick_preferred_enabled_model_locked(
                self._default_judge_model
            )
            self._state.enabled_models[self._state.judge_model] = True

    def _pick_preferred_enabled_model_locked(self, preferred_model: str) -> str:
        if (
            preferred_model in self._state.available_models
            and self._state.enabled_models.get(preferred_model, True)
        ):
            return preferred_model
        for candidate in [self._default_active_model, self._default_judge_model]:
            if (
                candidate in self._state.available_models
                and self._state.enabled_models.get(candidate, True)
            ):
                return candidate
        for candidate in self._state.available_models:
            if self._state.enabled_models.get(candidate, True):
                return candidate
        return self._state.available_models[0]

    def _enabled_model_count_locked(self) -> int:
        return sum(1 for value in self._state.enabled_models.values() if value)

    def _ensure_model_known_locked(self, model: str) -> None:
        if model not in self._state.available_models:
            self._state.available_models.append(model)
        self._state.available_models = self._dedupe_models(self._state.available_models)
        self._state.enabled_models.setdefault(
            model, self._default_enabled_models.get(model, True)
        )

    def _rate_limit_from_dict(self, data: dict) -> RateLimitState:
        return RateLimitState(
            model=data.get("model"),
            remaining_requests=data.get("remaining_requests"),
            request_limit=data.get("request_limit"),
            remaining_tokens=data.get("remaining_tokens"),
            token_limit=data.get("token_limit"),
            retry_after=data.get("retry_after"),
            last_updated=data.get("last_updated"),
        )

    def _chat_settings_from_dict(self, data: dict) -> ChatReplySettings:
        return ChatReplySettings(
            enabled=bool(data.get("enabled", True)),
            reply_probability=float(data.get("reply_probability", 0.35)),
            cooldown_seconds=int(data.get("cooldown_seconds", 900)),
            min_delay_seconds=int(data.get("min_delay_seconds", 25)),
            max_delay_seconds=int(data.get("max_delay_seconds", 90)),
            max_replies_per_hour=int(data.get("max_replies_per_hour", 4)),
            allow_bots=bool(data.get("allow_bots", False)),
            min_message_length=int(data.get("min_message_length", 8)),
        )

    def _chat_runtime_from_dict(self, data: dict) -> ChatRuntimeState:
        return ChatRuntimeState(
            last_reply_at=data.get("last_reply_at"),
            recent_reply_timestamps=list(data.get("recent_reply_timestamps") or []),
            last_message_fingerprint=data.get("last_message_fingerprint"),
            last_message_at=data.get("last_message_at"),
            replies_sent_total=int(data.get("replies_sent_total", 0)),
            consecutive_ai_replies=int(data.get("consecutive_ai_replies", 0)),
            last_reply_target_user_id=(
                int(data.get("last_reply_target_user_id"))
                if data.get("last_reply_target_user_id") is not None
                else None
            ),
            user_reply_timestamps={
                str(key): str(value)
                for key, value in (data.get("user_reply_timestamps") or {}).items()
            },
        )

    def _ensure_chat_settings_locked(self, chat_id: int) -> ChatReplySettings:
        key = str(chat_id)
        if key not in self._state.chat_settings:
            self._state.chat_settings[key] = ChatReplySettings()
        return self._state.chat_settings[key]

    def _ensure_chat_runtime_locked(self, chat_id: int) -> ChatRuntimeState:
        key = str(chat_id)
        if key not in self._state.chat_runtime:
            self._state.chat_runtime[key] = ChatRuntimeState()
        return self._state.chat_runtime[key]

    def _normalize_aliases(self, aliases: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in aliases:
            cleaned = str(value).strip().lstrip(".")
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(cleaned)
        return normalized

    def _normalize_audience_flags(self, raw: dict | None) -> dict[str, bool]:
        default = {"STRANGERS": True, "KNOWN": True, "FRIENDS": True, "BUSINESS": True}
        if not isinstance(raw, dict):
            return dict(default)
        result = dict(default)
        for key in default:
            if key in raw:
                result[key] = bool(raw[key])
        return result

    def _dedupe_models(self, models: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in models:
            cleaned = str(value).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized

    def _dedupe_chat_ids(self, chat_ids: list[int]) -> list[int]:
        normalized: list[int] = []
        seen: set[int] = set()
        for value in chat_ids:
            chat_id = int(value)
            if chat_id in seen:
                continue
            seen.add(chat_id)
            normalized.append(chat_id)
        return normalized

    def _parse_iso(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def _touch_and_write_locked(self) -> None:
        self._state.updated_at = self._now_iso()
        await self._write_locked()

    def _load_from_sqlite(self) -> bool:
        """Загрузить данные из SQLite.

        Returns:
            True если данные успешно загружены
        """
        if not self._sqlite:
            return False

        try:
            # Загружаем конфигурацию
            config = self._sqlite.get_all_config()
            if not config:
                return False

            # Восстанавливаем state из SQLite данных
            self._state.active_model = config.get(
                "active_model", self._default_active_model
            )
            self._state.judge_model = config.get(
                "judge_model", self._default_judge_model
            )
            self._state.available_models = config.get(
                "available_models", list(self._default_models)
            )
            self._state.enabled_models = config.get(
                "enabled_models", dict(self._default_enabled_models)
            )
            self._state.fallback_enabled = config.get(
                "fallback_enabled", self._default_fallback_enabled
            )
            self._state.ai_mode_enabled = config.get("ai_mode_enabled", True)
            self._state.response_style_mode = config.get(
                "response_style_mode", "NORMAL"
            )
            self._state.command_mode_enabled = config.get(
                "command_mode_enabled", self._default_command_mode_enabled
            )
            self._state.trigger_aliases = config.get(
                "trigger_aliases", list(self._default_trigger_aliases)
            )
            self._state.dot_prefix_required = config.get(
                "dot_prefix_required", self._default_dot_prefix_required
            )
            self._state.auto_reply_enabled = config.get(
                "auto_reply_enabled", self._default_auto_reply_enabled
            )
            self._state.reply_audience_mode = config.get("reply_audience_mode", "ALL")
            self._state.reply_audience_flags = config.get(
                "reply_audience_flags",
                {"STRANGERS": True, "KNOWN": True, "FRIENDS": True, "BUSINESS": True},
            )
            self._state.chat_bot_allowed_user_ids = config.get(
                "chat_bot_allowed_user_ids", []
            )
            self._state.reply_only_questions = config.get("reply_only_questions", True)
            self._state.chat_bot_owner_only = config.get("chat_bot_owner_only", True)
            self._state.require_owner_mention_or_context = config.get(
                "require_owner_mention_or_context", True
            )
            self._state.allowed_chat_ids = config.get("allowed_chat_ids", [])
            self._state.blocked_chat_ids = config.get("blocked_chat_ids", [])
            self._state.models_refreshed_at = config.get("models_refreshed_at")
            self._state.updated_at = config.get("updated_at")
            self._state.visitor_mode_enabled = config.get("visitor_mode_enabled", False)

            # Загружаем chat_settings (из config)
            chat_settings_raw = config.get("chat_settings", {})
            self._state.chat_settings = {
                str(key): self._chat_settings_from_dict(value)
                for key, value in chat_settings_raw.items()
            }

            # Загружаем chat_runtime из отдельной таблицы
            chat_runtime = self._sqlite.get_all_chat_runtime()
            self._state.chat_runtime = {
                str(key): self._chat_runtime_from_dict(value)
                for key, value in chat_runtime.items()
            }

            # Загружаем last_limits
            last_limits_raw = config.get("last_limits", {})
            self._state.last_limits = self._rate_limit_from_dict(last_limits_raw)

            # Загружаем model_limits из отдельной таблицы
            model_limits = self._sqlite.get_all_model_limits()
            self._state.model_limits = {
                str(model_name): self._rate_limit_from_dict(data)
                for model_name, data in model_limits.items()
            }

            return True

        except Exception:
            return False

    async def _write_locked(self) -> None:
        await atomic_write_json(self._path, asdict(self._state), indent=2)
        # Dual-write: сохраняем в SQLite
        if self._sqlite:
            await asyncio.to_thread(self._write_sqlite)

    def _write_sqlite(self) -> None:
        """Сохранить данные в SQLite (dual-write)."""
        if not self._sqlite:
            return

        try:
            # Простые ключи конфигурации
            simple_keys = [
                "active_model",
                "judge_model",
                "available_models",
                "enabled_models",
                "fallback_enabled",
                "ai_mode_enabled",
                "response_style_mode",
                "command_mode_enabled",
                "trigger_aliases",
                "dot_prefix_required",
                "auto_reply_enabled",
                "reply_audience_mode",
                "reply_audience_flags",
                "chat_bot_allowed_user_ids",
                "reply_only_questions",
                "chat_bot_owner_only",
                "require_owner_mention_or_context",
                "allowed_chat_ids",
                "blocked_chat_ids",
                "chat_settings",
                "last_limits",
                "models_refreshed_at",
                "updated_at",
                "visitor_mode_enabled",
            ]

            state_dict = asdict(self._state)
            for key in simple_keys:
                if key in state_dict:
                    self._sqlite.set_config(key, state_dict[key])

            # Chat runtime
            for chat_id, runtime_data in self._state.chat_runtime.items():
                runtime_dict = asdict(runtime_data)
                self._sqlite.set_chat_runtime(chat_id, runtime_dict)

            # Model limits
            for model_name, limits in self._state.model_limits.items():
                limits_dict = asdict(limits)
                limits_dict["model"] = model_name
                self._sqlite.set_model_limit(model_name, limits_dict)

        except Exception:
            # Игнорируем ошибки SQLite, JSON остаётся основным
            pass
