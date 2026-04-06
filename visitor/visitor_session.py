from __future__ import annotations

import asyncio
import copy
import json
import logging
import time
from pathlib import Path

from infra.json_atomic import atomic_write_json

from .visitor_models import VisitorContext

LOGGER = logging.getLogger("assistant.visitor.session")


class VisitorSessionStore:
    """Persistent visitor session store.

    Stores lightweight metadata and active-session dialogue history.
    """

    def __init__(
        self,
        timeout_minutes: int = 30,
        path: Path | None = None,
    ) -> None:
        self._sessions: dict[int, VisitorContext] = {}
        self._blocked_users: set[int] = set()
        self._lock = asyncio.Lock()
        self._timeout_seconds = timeout_minutes * 60
        self._path = path

    async def load(self) -> dict[int, VisitorContext]:
        async with self._lock:
            if self._path is None:
                return copy.deepcopy(self._sessions)

            if not self._path.exists():
                await self._write_locked()
                return copy.deepcopy(self._sessions)

            try:
                raw = await asyncio.to_thread(self._path.read_text, encoding="utf-8")
                payload = json.loads(raw or "{}")
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                LOGGER.warning("visitor_session_load_failed", exc_info=True)
                payload = {}

            sessions_payload = payload.get("sessions", {})
            blocked_payload = payload.get("blocked_users", [])

            self._sessions = {}
            if isinstance(sessions_payload, dict):
                for user_id_str, item in sessions_payload.items():
                    try:
                        user_id = int(user_id_str)
                    except (TypeError, ValueError):
                        continue
                    if not isinstance(item, dict):
                        continue
                    self._sessions[user_id] = self._context_from_dict(user_id, item)

            self._blocked_users = set()
            if isinstance(blocked_payload, list):
                for value in blocked_payload:
                    try:
                        self._blocked_users.add(int(value))
                    except (TypeError, ValueError):
                        continue

            self._normalize_locked()
            await self._write_locked()
            return copy.deepcopy(self._sessions)

    async def is_blocked(self, user_id: int) -> bool:
        async with self._lock:
            return user_id in self._blocked_users

    async def block_user(self, user_id: int) -> None:
        async with self._lock:
            self._blocked_users.add(user_id)
            ctx = self._sessions.get(user_id)
            if ctx:
                ctx.active = False
                ctx.ai_offered_end = False
                ctx.temp_blocked_until = 0.0
            await self._write_locked()

    async def unblock_user(self, user_id: int) -> None:
        async with self._lock:
            self._blocked_users.discard(user_id)
            ctx = self._sessions.get(user_id)
            if ctx is not None:
                ctx.clear_moderation_flags()
            await self._write_locked()

    async def get_blocked_users(self) -> list[int]:
        async with self._lock:
            return list(self._blocked_users)

    async def get_or_create(self, user_id: int) -> VisitorContext:
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is None:
                ctx = VisitorContext(user_id=user_id)
                self._sessions[user_id] = ctx
                await self._write_locked()
            return ctx

    async def update_identity(
        self,
        user_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        only_if_missing: bool = True,
    ) -> VisitorContext:
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is None:
                ctx = VisitorContext(user_id=user_id)
                self._sessions[user_id] = ctx

            changed = False
            if username and ((not only_if_missing) or not ctx.username):
                if ctx.username != username:
                    ctx.username = username
                    changed = True
            if first_name and ((not only_if_missing) or not ctx.first_name):
                if ctx.first_name != first_name:
                    ctx.first_name = first_name
                    changed = True

            if changed:
                await self._write_locked()
            return ctx

    async def is_active(self, user_id: int) -> bool:
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is None or not ctx.active:
                return False
            if ctx.is_inactive(self._timeout_seconds):
                ctx.clear_session_memory()
                await self._write_locked()
                return False
            return True

    async def get_temporary_block_remaining(self, user_id: int) -> int:
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is None:
                return 0
            remaining = ctx.temporary_block_remaining_seconds()
            if remaining <= 0 and ctx.temp_blocked_until:
                ctx.temp_blocked_until = 0.0
                await self._write_locked()
                return 0
            return remaining

    async def get_restart_cooldown_remaining(self, user_id: int) -> int:
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is None:
                return 0
            remaining = ctx.restart_cooldown_remaining_seconds()
            if remaining <= 0 and ctx.restart_cooldown_until:
                ctx.restart_cooldown_until = 0.0
                await self._write_locked()
                return 0
            return remaining

    async def set_temporary_block(
        self,
        user_id: int,
        *,
        seconds: int,
        reason: str | None = None,
        text: str | None = None,
    ) -> VisitorContext:
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is None:
                ctx = VisitorContext(user_id=user_id)
                self._sessions[user_id] = ctx
            ctx.set_temporary_block(seconds)
            if reason:
                ctx.last_abuse_reason = reason
            if text:
                ctx.last_abuse_text = text
            await self._write_locked()
            return copy.deepcopy(ctx)

    async def register_abuse(
        self,
        user_id: int,
        *,
        reason: str,
        text: str,
        strike_threshold: int = 3,
        strike_window_seconds: int = 86400,
        temporary_block_seconds: int = 86400,
        owner_alert_cooldown_seconds: int = 900,
    ) -> tuple[VisitorContext, bool, bool]:
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is None:
                ctx = VisitorContext(user_id=user_id)
                self._sessions[user_id] = ctx

            strikes = ctx.register_abuse(
                reason,
                text,
                strike_window_seconds=strike_window_seconds,
            )

            blocked_now = False
            if strikes >= strike_threshold:
                ctx.set_temporary_block(temporary_block_seconds)
                blocked_now = True

            now = time.time()
            should_notify = (
                blocked_now
                or not ctx.last_owner_alert_at
                or (now - ctx.last_owner_alert_at) >= owner_alert_cooldown_seconds
            )
            if should_notify:
                ctx.last_owner_alert_at = now

            await self._write_locked()
            return copy.deepcopy(ctx), blocked_now, should_notify

    async def check_rate_limit(self, user_id: int, max_per_minute: int = 30) -> bool:
        """Return True if user is rate limited."""
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is None:
                return True
            limited = ctx.is_rate_limited(max_per_minute)
            await self._write_locked()
            return limited

    async def start_session(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> VisitorContext:
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is None:
                ctx = VisitorContext(user_id=user_id)
                self._sessions[user_id] = ctx
            ctx.clear_session_memory()
            ctx.active = True
            if username:
                ctx.username = username
            if first_name:
                ctx.first_name = first_name
            ctx.started_at = time.time()
            ctx.last_activity = time.time()
            ctx.restart_cooldown_until = 0.0
            await self._write_locked()
            return ctx

    async def end_session(self, user_id: int) -> None:
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is not None:
                ctx.clear_session_memory()
                await self._write_locked()

    async def end_session_with_cooldown(self, user_id: int, *, seconds: int) -> None:
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is None:
                ctx = VisitorContext(user_id=user_id)
                self._sessions[user_id] = ctx
            ctx.set_restart_cooldown(seconds)
            ctx.clear_session_memory()
            await self._write_locked()

    async def set_ai_offered_end(self, user_id: int) -> None:
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is not None:
                ctx.ai_offered_end = True
                await self._write_locked()

    async def cleanup_inactive(self) -> int:
        """End sessions inactive for more than timeout. Returns count ended."""
        ended = 0
        async with self._lock:
            for ctx in self._sessions.values():
                if ctx.active and ctx.is_inactive(self._timeout_seconds):
                    ctx.clear_session_memory()
                    ended += 1
            if ended:
                await self._write_locked()
        return ended

    async def clear_user(self, user_id: int) -> None:
        async with self._lock:
            removed = self._sessions.pop(user_id, None)
            was_blocked = user_id in self._blocked_users
            self._blocked_users.discard(user_id)
            if removed is not None or was_blocked:
                await self._write_locked()

    async def count_active(self) -> int:
        async with self._lock:
            return sum(
                1
                for ctx in self._sessions.values()
                if ctx.active and not ctx.is_inactive(self._timeout_seconds)
            )

    async def get_all_active(self) -> list[VisitorContext]:
        """Admin: get snapshot of all active sessions."""
        async with self._lock:
            return [
                ctx
                for ctx in self._sessions.values()
                if ctx.active and not ctx.is_inactive(self._timeout_seconds)
            ]

    async def get_all_sessions(self) -> list[VisitorContext]:
        """Admin: get all sessions (active + recent)."""
        async with self._lock:
            return list(self._sessions.values())

    async def record_topic(self, user_id: int, category: str) -> None:
        """Record topic for admin analytics."""
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is not None:
                ctx.record_topic(category)
                await self._write_locked()

    async def register_boundary_attempt(
        self,
        user_id: int,
        *,
        reset_window_seconds: int = 1800,
    ) -> int:
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is None:
                ctx = VisitorContext(user_id=user_id)
                self._sessions[user_id] = ctx
            streak = ctx.register_boundary_attempt(
                reset_window_seconds=reset_window_seconds
            )
            await self._write_locked()
            return streak

    async def reset_boundary_streak(self, user_id: int) -> None:
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is None or ctx.boundary_streak == 0:
                return
            ctx.reset_boundary_streak()
            await self._write_locked()

    async def register_low_signal(
        self,
        user_id: int,
        *,
        reset_window_seconds: int = 1800,
    ) -> int:
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is None:
                ctx = VisitorContext(user_id=user_id)
                self._sessions[user_id] = ctx
            streak = ctx.register_low_signal(reset_window_seconds=reset_window_seconds)
            await self._write_locked()
            return streak

    async def reset_low_signal_streak(self, user_id: int) -> None:
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is None or ctx.low_signal_streak == 0:
                return
            ctx.reset_low_signal_streak()
            await self._write_locked()

    async def add_exchange(
        self,
        user_id: int,
        *,
        user_text: str,
        assistant_text: str,
    ) -> None:
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is None or not ctx.active:
                return
            ctx.add_history_message("user", user_text)
            ctx.add_history_message("assistant", assistant_text)
            await self._write_locked()

    async def get_history(self, user_id: int) -> list[dict[str, str]]:
        async with self._lock:
            ctx = self._sessions.get(user_id)
            if ctx is None:
                return []
            return copy.deepcopy(ctx.conversation_history)

    def _normalize_locked(self) -> None:
        now = time.time()
        normalized: dict[int, VisitorContext] = {}

        for user_id, ctx in self._sessions.items():
            topic_counts = {
                str(key): int(value)
                for key, value in (ctx.topic_counts or {}).items()
                if isinstance(key, str) and isinstance(value, (int, float))
            }
            timestamps = []
            for ts in ctx.recent_message_timestamps or []:
                try:
                    value = float(ts)
                except (TypeError, ValueError):
                    continue
                if now - value < 60:
                    timestamps.append(value)

            normalized_ctx = VisitorContext(
                user_id=int(user_id),
                active=bool(ctx.active),
                username=ctx.username or None,
                first_name=ctx.first_name or None,
                started_at=float(ctx.started_at or now),
                last_activity=float(ctx.last_activity or now),
                message_count=max(0, int(ctx.message_count or 0)),
                topic_counts=topic_counts,
                conversation_history=[
                    {
                        "role": str(item.get("role", "")).strip(),
                        "content": str(item.get("content", "")).strip()[:4000],
                    }
                    for item in (ctx.conversation_history or [])
                    if isinstance(item, dict)
                    and str(item.get("role", "")).strip() in {"user", "assistant"}
                    and str(item.get("content", "")).strip()
                ],
                recent_message_timestamps=timestamps,
                ai_offered_end=bool(ctx.ai_offered_end),
                boundary_streak=max(0, int(ctx.boundary_streak or 0)),
                last_boundary_at=float(ctx.last_boundary_at or 0.0),
                low_signal_streak=max(0, int(ctx.low_signal_streak or 0)),
                last_low_signal_at=float(ctx.last_low_signal_at or 0.0),
                restart_cooldown_until=float(ctx.restart_cooldown_until or 0.0),
                abuse_strikes=max(0, int(ctx.abuse_strikes or 0)),
                last_abuse_at=float(ctx.last_abuse_at or 0.0),
                last_abuse_reason=ctx.last_abuse_reason or None,
                last_abuse_text=ctx.last_abuse_text or None,
                last_owner_alert_at=float(ctx.last_owner_alert_at or 0.0),
                temp_blocked_until=float(ctx.temp_blocked_until or 0.0),
            )
            if normalized_ctx.active and normalized_ctx.is_inactive(self._timeout_seconds):
                normalized_ctx.clear_session_memory()
            if not normalized_ctx.is_temporarily_blocked():
                normalized_ctx.temp_blocked_until = 0.0
            if normalized_ctx.restart_cooldown_remaining_seconds() <= 0:
                normalized_ctx.restart_cooldown_until = 0.0
            normalized[int(user_id)] = normalized_ctx

        self._sessions = normalized

    @staticmethod
    def _context_from_dict(user_id: int, payload: dict) -> VisitorContext:
        now = time.time()
        return VisitorContext(
            user_id=user_id,
            active=bool(payload.get("active", False)),
            username=str(payload.get("username")) if payload.get("username") else None,
            first_name=str(payload.get("first_name")) if payload.get("first_name") else None,
            started_at=float(payload.get("started_at", now) or now),
            last_activity=float(payload.get("last_activity", now) or now),
            message_count=max(0, int(payload.get("message_count", 0) or 0)),
            topic_counts=dict(payload.get("topic_counts", {}) or {}),
            conversation_history=list(payload.get("conversation_history", []) or []),
            recent_message_timestamps=list(
                payload.get("recent_message_timestamps", []) or []
            ),
            ai_offered_end=bool(payload.get("ai_offered_end", False)),
            boundary_streak=max(0, int(payload.get("boundary_streak", 0) or 0)),
            last_boundary_at=float(payload.get("last_boundary_at", 0.0) or 0.0),
            low_signal_streak=max(0, int(payload.get("low_signal_streak", 0) or 0)),
            last_low_signal_at=float(payload.get("last_low_signal_at", 0.0) or 0.0),
            restart_cooldown_until=float(payload.get("restart_cooldown_until", 0.0) or 0.0),
            abuse_strikes=max(0, int(payload.get("abuse_strikes", 0) or 0)),
            last_abuse_at=float(payload.get("last_abuse_at", 0.0) or 0.0),
            last_abuse_reason=str(payload.get("last_abuse_reason"))
            if payload.get("last_abuse_reason")
            else None,
            last_abuse_text=str(payload.get("last_abuse_text"))
            if payload.get("last_abuse_text")
            else None,
            last_owner_alert_at=float(payload.get("last_owner_alert_at", 0.0) or 0.0),
            temp_blocked_until=float(payload.get("temp_blocked_until", 0.0) or 0.0),
        )

    def _serialize_locked(self) -> dict[str, object]:
        return {
            "version": 1,
            "blocked_users": sorted(self._blocked_users),
            "sessions": {
                str(user_id): {
                    "active": ctx.active,
                    "username": ctx.username,
                    "first_name": ctx.first_name,
                    "started_at": ctx.started_at,
                    "last_activity": ctx.last_activity,
                    "message_count": ctx.message_count,
                    "topic_counts": dict(ctx.topic_counts),
                    "conversation_history": list(ctx.conversation_history),
                    "recent_message_timestamps": list(ctx.recent_message_timestamps),
                    "ai_offered_end": ctx.ai_offered_end,
                    "boundary_streak": ctx.boundary_streak,
                    "last_boundary_at": ctx.last_boundary_at,
                    "low_signal_streak": ctx.low_signal_streak,
                    "last_low_signal_at": ctx.last_low_signal_at,
                    "restart_cooldown_until": ctx.restart_cooldown_until,
                    "abuse_strikes": ctx.abuse_strikes,
                    "last_abuse_at": ctx.last_abuse_at,
                    "last_abuse_reason": ctx.last_abuse_reason,
                    "last_abuse_text": ctx.last_abuse_text,
                    "last_owner_alert_at": ctx.last_owner_alert_at,
                    "temp_blocked_until": ctx.temp_blocked_until,
                }
                for user_id, ctx in self._sessions.items()
            },
        }

    async def _write_locked(self) -> None:
        if self._path is None:
            return
        await atomic_write_json(self._path, self._serialize_locked(), indent=2)

