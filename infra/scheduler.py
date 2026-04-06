from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine

from infra.json_atomic import atomic_write_json


LOGGER = logging.getLogger("assistant.scheduler")


@dataclass(slots=True)
class ScheduledTask:
    task_id: str
    fire_at: str  # ISO timestamp UTC
    target_chat: str | int | None
    origin_chat_id: int
    message_text: str
    label: str = ""  # human-readable label for listing
    created_at: str = ""
    repeat_interval_seconds: int | None = None


class ReminderIntentLevel(str, Enum):
    NONE = "none"
    WEAK = "weak"
    STRONG = "strong"


@dataclass(slots=True)
class ScheduleIntentDetection:
    level: ReminderIntentLevel
    matched_signals: list[str] = field(default_factory=list)
    has_time_expression: bool = False
    has_reminder_verb: bool = False
    has_message_payload: bool = False
    has_repeat_pattern: bool = False


@dataclass(slots=True)
class ReminderParseResult:
    ok: bool
    intent_level: ReminderIntentLevel
    fire_at: datetime | None = None
    message_text: str | None = None
    target_chat: str | int | None = None
    label: str | None = None
    repeat_interval_seconds: int | None = None
    parse_warnings: list[str] = field(default_factory=list)
    parse_error: str | None = None
    matched_signals: list[str] = field(default_factory=list)
    source_text: str = ""

    def to_task_payload(self) -> dict[str, Any] | None:
        if not self.ok or self.fire_at is None or not self.message_text or not self.label:
            return None
        payload: dict[str, Any] = {
            "fire_at": self.fire_at,
            "message_text": self.message_text,
            "target_chat": self.target_chat,
            "label": self.label,
        }
        if self.repeat_interval_seconds is not None:
            payload["repeat_interval_seconds"] = self.repeat_interval_seconds
        return payload


class SchedulerStore:
    """Persistent scheduler that survives restarts by saving tasks to JSON."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._tasks: dict[str, ScheduledTask] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._fire_callback: (
            Callable[[ScheduledTask], Coroutine[Any, Any, None]] | None
        ) = None

    def set_fire_callback(
        self, cb: Callable[[ScheduledTask], Coroutine[Any, Any, None]]
    ) -> None:
        self._fire_callback = cb

    async def load(self) -> None:
        async with self._lock:
            if not self._path.exists():
                await self._write_locked()
                return
            try:
                raw = await asyncio.to_thread(self._path.read_text, encoding="utf-8")
                data = json.loads(raw or "{}")
            except Exception:
                data = {}
            now = datetime.now(timezone.utc)
            for task_id, item in (data.get("tasks") or {}).items():
                try:
                    task = self._task_from_dict(item)
                    next_fire = self._advance_to_future_fire_at(task, now)
                    if next_fire is None:
                        LOGGER.info("scheduler_skip_expired task_id=%s", task_id)
                        continue
                    task.fire_at = next_fire.isoformat()
                    self._tasks[task_id] = task
                except Exception:
                    LOGGER.debug(
                        "scheduler_load_task_failed task_id=%s", task_id, exc_info=True
                    )
            await self._write_locked()
        LOGGER.info("scheduler_loaded tasks=%d", len(self._tasks))

    async def start_all(self) -> None:
        async with self._lock:
            task_ids = list(self._tasks.keys())
        for task_id in task_ids:
            await self._spawn(task_id)

    async def add(
        self,
        *,
        task_id: str,
        fire_at: datetime,
        target_chat: str | int | None,
        origin_chat_id: int,
        message_text: str,
        label: str = "",
        repeat_interval_seconds: int | None = None,
    ) -> ScheduledTask:
        task = ScheduledTask(
            task_id=task_id,
            fire_at=fire_at.isoformat(),
            target_chat=target_chat,
            origin_chat_id=origin_chat_id,
            message_text=message_text,
            label=label,
            created_at=datetime.now(timezone.utc).isoformat(),
            repeat_interval_seconds=(
                int(repeat_interval_seconds)
                if repeat_interval_seconds not in (None, "", 0)
                else None
            ),
        )
        async with self._lock:
            self._tasks[task_id] = task
            await self._write_locked()
        await self._spawn(task_id)
        LOGGER.info(
            "scheduler_task_added task_id=%s fire_at=%s repeat=%s",
            task_id,
            fire_at.isoformat(),
            task.repeat_interval_seconds,
        )
        return task

    async def cancel(self, task_id: str) -> bool:
        async with self._lock:
            task = self._tasks.pop(task_id, None)
            if task is None:
                return False
            running = self._running.pop(task_id, None)
            if running and not running.done():
                running.cancel()
            await self._write_locked()
        LOGGER.info("scheduler_task_cancelled task_id=%s", task_id)
        return True

    async def list_tasks(self) -> list[ScheduledTask]:
        async with self._lock:
            return list(self._tasks.values())

    async def cancel_all(self) -> None:
        async with self._lock:
            for task in self._running.values():
                if not task.done():
                    task.cancel()
            self._running.clear()
            self._tasks.clear()
            await self._write_locked()

    async def _spawn(self, task_id: str) -> None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            existing = self._running.get(task_id)
            if existing and not existing.done():
                return
        loop_task = asyncio.create_task(self._run_task(task_id))
        async with self._lock:
            self._running[task_id] = loop_task

    async def _run_task(self, task_id: str) -> None:
        async with self._lock:
            task = self._tasks.get(task_id)
        if task is None:
            return

        should_reschedule = False
        try:
            now = datetime.now(timezone.utc)
            fire_at = datetime.fromisoformat(task.fire_at)
            delay = (fire_at - now).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)

            async with self._lock:
                still_here = task_id in self._tasks
            if not still_here:
                return

            if self._fire_callback is not None:
                await self._fire_callback(task)
            LOGGER.info("scheduler_task_fired task_id=%s", task_id)
            should_reschedule = bool(task.repeat_interval_seconds)
        except asyncio.CancelledError:
            LOGGER.info("scheduler_task_cancelled task_id=%s", task_id)
            return
        except Exception:
            LOGGER.exception("scheduler_task_failed task_id=%s", task_id)
            should_reschedule = bool(task.repeat_interval_seconds)
        finally:
            removed = False
            async with self._lock:
                current = self._tasks.get(task_id)
                self._running.pop(task_id, None)
                if current is None:
                    await self._write_locked()
                    removed = True
                elif should_reschedule:
                    current.fire_at = self._next_repeating_fire_at(current).isoformat()
                    self._tasks[task_id] = current
                else:
                    self._tasks.pop(task_id, None)
                await self._write_locked()
            if should_reschedule and not removed:
                await self._spawn(task_id)

    async def _write_locked(self) -> None:
        await atomic_write_json(
            self._path,
            {"tasks": {tid: asdict(task) for tid, task in self._tasks.items()}},
            indent=2,
        )

    def _task_from_dict(self, data: dict[str, Any]) -> ScheduledTask:
        return ScheduledTask(
            task_id=str(data.get("task_id", "")),
            fire_at=str(data.get("fire_at", "")),
            target_chat=data.get("target_chat"),
            origin_chat_id=int(data.get("origin_chat_id", 0)),
            message_text=str(data.get("message_text", "")),
            label=str(data.get("label", "")),
            created_at=str(data.get("created_at", "")),
            repeat_interval_seconds=(
                int(data.get("repeat_interval_seconds"))
                if data.get("repeat_interval_seconds") not in (None, "", 0)
                else None
            ),
        )

    def _advance_to_future_fire_at(
        self, task: ScheduledTask, now: datetime
    ) -> datetime | None:
        fire_at = datetime.fromisoformat(task.fire_at)
        if fire_at > now:
            return fire_at
        interval = int(task.repeat_interval_seconds or 0)
        if interval <= 0:
            return None
        diff_seconds = max(0.0, (now - fire_at).total_seconds())
        skipped = int(diff_seconds // interval) + 1
        return fire_at + timedelta(seconds=interval * skipped)

    def _next_repeating_fire_at(self, task: ScheduledTask) -> datetime:
        fire_at = datetime.fromisoformat(task.fire_at)
        interval = max(1, int(task.repeat_interval_seconds or 0))
        candidate = fire_at + timedelta(seconds=interval)
        now = datetime.now(timezone.utc)
        if candidate > now:
            return candidate
        diff_seconds = max(0.0, (now - candidate).total_seconds())
        skipped = int(diff_seconds // interval) + 1
        return candidate + timedelta(seconds=interval * skipped)


EXPLICIT_REMINDER_PATTERNS = (
    (r"(?iu)\bremind(?:\s+me)?\b", "explicit:remind"),
    (r"(?iu)\bset(?:\s+a)?\s+reminder\b", "explicit:set_reminder"),
    (r"(?iu)\bcreate\s+reminder\b", "explicit:create_reminder"),
    (r"(?iu)\bschedule\s+reminder\b", "explicit:schedule_reminder"),
    (r"(?iu)\balert\s+me\b", "explicit:alert_me"),
    (r"(?iu)\bset\s+timer\b", "explicit:set_timer"),
    (r"(?iu)\bstart\s+timer\b", "explicit:start_timer"),
    (r"(?iu)\bping\s+me\b", "explicit:ping_me"),
    (r"(?iu)\bÐ½Ð°Ð¿Ð¾Ð¼Ð½Ð¸(?:\s+Ð¼Ð½Ðµ)?\b", "explicit:Ð½Ð°Ð¿Ð¾Ð¼Ð½Ð¸"),
    (r"(?iu)\bÐ¿Ð¾ÑÑ‚Ð°Ð²[ÑŒÐ¹]\s+Ð½Ð°Ð¿Ð¾Ð¼Ð¸Ð½Ð°Ð½Ð¸\w*\b", "explicit:Ð¿Ð¾ÑÑ‚Ð°Ð²ÑŒ_Ð½Ð°Ð¿Ð¾Ð¼Ð¸Ð½Ð°Ð½Ð¸Ðµ"),
    (r"(?iu)\bÑÐ¾Ð·Ð´Ð°[Ð¹Ñ‚ÑŒ]\s+Ð½Ð°Ð¿Ð¾Ð¼Ð¸Ð½Ð°Ð½Ð¸\w*\b", "explicit:ÑÐ¾Ð·Ð´Ð°Ð¹_Ð½Ð°Ð¿Ð¾Ð¼Ð¸Ð½Ð°Ð½Ð¸Ðµ"),
    (r"(?iu)\bÑƒÑÑ‚Ð°Ð½Ð¾Ð²Ð¸\s+Ð½Ð°Ð¿Ð¾Ð¼Ð¸Ð½Ð°Ð½Ð¸\w*\b", "explicit:ÑƒÑÑ‚Ð°Ð½Ð¾Ð²Ð¸_Ð½Ð°Ð¿Ð¾Ð¼Ð¸Ð½Ð°Ð½Ð¸Ðµ"),
    (r"(?iu)\bÐ¿Ð¾ÑÑ‚Ð°Ð²[ÑŒÐ¹]\s+Ñ‚Ð°Ð¹Ð¼ÐµÑ€\b", "explicit:Ð¿Ð¾ÑÑ‚Ð°Ð²ÑŒ_Ñ‚Ð°Ð¹Ð¼ÐµÑ€"),
    (r"(?iu)\bÐ·Ð°Ð¿ÑƒÑÑ‚Ð¸\s+Ñ‚Ð°Ð¹Ð¼ÐµÑ€\b", "explicit:Ð·Ð°Ð¿ÑƒÑÑ‚Ð¸_Ñ‚Ð°Ð¹Ð¼ÐµÑ€"),
)

WEAK_REMINDER_PATTERNS = (
    (r"(?iu)\bdon'?t\s+forget\b", "weak:dont_forget"),
    (r"(?iu)\bmust\s+not\s+forget\b", "weak:must_not_forget"),
    (r"(?iu)\bremind\s+myself\b", "weak:remind_myself"),
    (r"(?iu)\btodo\s*:", "weak:todo"),
    (r"(?iu)\bto\s+do\s*:", "weak:to_do"),
    (r"(?iu)\bÐ½Ðµ\s+Ð·Ð°Ð±Ñ‹Ñ‚ÑŒ\b", "weak:Ð½Ðµ_Ð·Ð°Ð±Ñ‹Ñ‚ÑŒ"),
    (r"(?iu)\bÐ½Ð°Ð´Ð¾\s+Ð½Ðµ\s+Ð·Ð°Ð±Ñ‹Ñ‚ÑŒ\b", "weak:Ð½Ð°Ð´Ð¾_Ð½Ðµ_Ð·Ð°Ð±Ñ‹Ñ‚ÑŒ"),
    (r"(?iu)\bÐ½Ðµ\s+Ð·Ð°Ð±ÑƒÐ´ÑŒ\b", "weak:Ð½Ðµ_Ð·Ð°Ð±ÑƒÐ´ÑŒ"),
)

HELP_QUERY_PATTERNS = (
    r"(?iu)\bhow\s+to\s+(?:list|see|view|remove|cancel)\s+reminder",
    r"(?iu)\b(?:ÐºÐ°Ðº|Ð³Ð´Ðµ)\s+(?:Ð¿Ð¾ÑÐ¼Ð¾Ñ‚Ñ€ÐµÑ‚ÑŒ|ÑƒÐ²Ð¸Ð´ÐµÑ‚ÑŒ|ÑƒÐ´Ð°Ð»Ð¸Ñ‚ÑŒ|Ð¾Ñ‚Ð¼ÐµÐ½Ð¸Ñ‚ÑŒ)\s+Ð½Ð°Ð¿Ð¾Ð¼Ð¸Ð½Ð°Ð½Ð¸\w*",
)

REPEAT_PATTERNS = (
    r"(?iu)\bevery\s+(?:\d+\s*)?(?:second|seconds|secs?|sec|minute|minutes|mins?|min|hour|hours|hrs?|hr|day|days|week|weeks)\b",
    r"(?iu)\bevery\s+(?:hour|day|week)\b",
    r"(?iu)\bÐºÐ°Ð¶Ð´(?:Ñ‹Ð¹|Ð°Ñ|Ð¾Ðµ|ÑƒÑŽ|Ñ‹Ðµ)\s+(?:\d+\s*)?(?:ÑÐµÐº\w*|Ð¼Ð¸Ð½\w*|Ñ‡Ð°Ñ\w*|Ð´Ð½\w*|Ð´ÐµÐ½\w*|Ð½ÐµÐ´ÐµÐ»\w*)\b",
    r"(?iu)\bÑ€Ð°Ð·\s+Ð²\s+(?:\d+\s*)?(?:ÑÐµÐº\w*|Ð¼Ð¸Ð½\w*|Ñ‡Ð°Ñ\w*|Ð´Ð½\w*|Ð´ÐµÐ½\w*|Ð½ÐµÐ´ÐµÐ»\w*)\b",
)

TIME_PATTERNS = (
    r"(?iu)\bin\s+\d+\s*(?:seconds?|secs?|sec|s|minutes?|mins?|min|m|hours?|hrs?|hr|h|days?)\b",
    r"(?iu)\bÑ‡ÐµÑ€ÐµÐ·\s+\d+\s*(?:ÑÐµÐº\w*|Ð¼Ð¸Ð½\w*|Ñ‡Ð°Ñ\w*|Ð´Ð½\w*|Ð´ÐµÐ½\w*)\b",
    r"(?iu)\b\d{1,2}[:\.]\d{2}\b",
    r"(?iu)\b(?:at|Ð²)\s+\d{1,2}\b",
    r"(?iu)\b(?:today|tomorrow|ÑÐµÐ³Ð¾Ð´Ð½Ñ|Ð·Ð°Ð²Ñ‚Ñ€Ð°)\b",
)

PAYLOAD_HINT_PATTERNS = (
    r'(?s)["\'](.+?)["\']',
    r"(?iu)\b(?:about|to|message|text|send|write|notify|post|ping)\b\s+.+$",
    r"(?iu)\b(?:Ð½Ð°Ð¿Ð¾Ð¼Ð½Ð¸(?:\s+Ð¼Ð½Ðµ)?|Ð½Ð°Ð¿Ð¸ÑˆÐ¸|Ð¿Ð¸ÑˆÐ¸|Ð¾Ñ‚Ð¿Ñ€Ð°Ð²ÑŒ|Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐ¹|ÑÐºÐ¸Ð½ÑŒ|ÑÐ¾Ð¾Ð±Ñ‰Ð°Ð¹)\b\s+.+$",
)

DELIVERY_VERB_PATTERNS = (
    r"(?iu)\b(?:send|write|notify|post|ping)\b",
    r"(?iu)\b(?:Ð½Ð°Ð¿Ð¸ÑˆÐ¸|Ð¿Ð¸ÑˆÐ¸|Ð¾Ñ‚Ð¿Ñ€Ð°Ð²ÑŒ|Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐ¹|ÑÐºÐ¸Ð½ÑŒ|ÑÐ¾Ð¾Ð±Ñ‰Ð°Ð¹)\b",
)


# Override reminder patterns with normalized Unicode-safe rules.
EXPLICIT_REMINDER_PATTERNS = (
    (r"(?iu)\bremind(?:\s+me)?\b", "explicit:remind"),
    (r"(?iu)\bset(?:\s+a)?\s+reminder\b", "explicit:set_reminder"),
    (r"(?iu)\bcreate\s+reminder\b", "explicit:create_reminder"),
    (r"(?iu)\bschedule\s+reminder\b", "explicit:schedule_reminder"),
    (r"(?iu)\balert\s+me\b", "explicit:alert_me"),
    (r"(?iu)\bset\s+timer\b", "explicit:set_timer"),
    (r"(?iu)\bstart\s+timer\b", "explicit:start_timer"),
    (r"(?iu)\bping\s+me\b", "explicit:ping_me"),
    (r"(?iu)\bÐ½Ð°Ð¿Ð¾Ð¼Ð½Ð¸(?:\s+Ð¼Ð½Ðµ)?\b", "explicit:Ð½Ð°Ð¿Ð¾Ð¼Ð½Ð¸"),
    (r"(?iu)\bÐ¿Ð¾ÑÑ‚Ð°Ð²(?:ÑŒ|ÑŒÑ‚Ðµ)?\s+Ð½Ð°Ð¿Ð¾Ð¼Ð¸Ð½Ð°Ð½Ð¸\w*\b", "explicit:Ð¿Ð¾ÑÑ‚Ð°Ð²ÑŒ_Ð½Ð°Ð¿Ð¾Ð¼Ð¸Ð½Ð°Ð½Ð¸Ðµ"),
    (r"(?iu)\bÑÐ¾Ð·Ð´Ð°(?:Ð¹|Ð¹Ñ‚Ðµ|Ñ‚ÑŒ)\s+Ð½Ð°Ð¿Ð¾Ð¼Ð¸Ð½Ð°Ð½Ð¸\w*\b", "explicit:ÑÐ¾Ð·Ð´Ð°Ð¹_Ð½Ð°Ð¿Ð¾Ð¼Ð¸Ð½Ð°Ð½Ð¸Ðµ"),
    (r"(?iu)\bÑƒÑÑ‚Ð°Ð½Ð¾Ð²Ð¸\s+Ð½Ð°Ð¿Ð¾Ð¼Ð¸Ð½Ð°Ð½Ð¸\w*\b", "explicit:ÑƒÑÑ‚Ð°Ð½Ð¾Ð²Ð¸_Ð½Ð°Ð¿Ð¾Ð¼Ð¸Ð½Ð°Ð½Ð¸Ðµ"),
    (r"(?iu)\bÐ¿Ð¾ÑÑ‚Ð°Ð²(?:ÑŒ|ÑŒÑ‚Ðµ)?\s+Ñ‚Ð°Ð¹Ð¼ÐµÑ€\b", "explicit:Ð¿Ð¾ÑÑ‚Ð°Ð²ÑŒ_Ñ‚Ð°Ð¹Ð¼ÐµÑ€"),
    (r"(?iu)\bÐ·Ð°Ð¿ÑƒÑÑ‚Ð¸\s+Ñ‚Ð°Ð¹Ð¼ÐµÑ€\b", "explicit:Ð·Ð°Ð¿ÑƒÑÑ‚Ð¸_Ñ‚Ð°Ð¹Ð¼ÐµÑ€"),
)

WEAK_REMINDER_PATTERNS = (
    (r"(?iu)\bdon'?t\s+forget\b", "weak:dont_forget"),
    (r"(?iu)\bmust\s+not\s+forget\b", "weak:must_not_forget"),
    (r"(?iu)\bremind\s+myself\b", "weak:remind_myself"),
    (r"(?iu)\btodo\s*:", "weak:todo"),
    (r"(?iu)\bto\s+do\s*:", "weak:to_do"),
    (r"(?iu)\bÐ½Ðµ\s+Ð·Ð°Ð±Ñ‹Ñ‚ÑŒ\b", "weak:Ð½Ðµ_Ð·Ð°Ð±Ñ‹Ñ‚ÑŒ"),
    (r"(?iu)\bÐ½Ð°Ð´Ð¾\s+Ð½Ðµ\s+Ð·Ð°Ð±Ñ‹Ñ‚ÑŒ\b", "weak:Ð½Ð°Ð´Ð¾_Ð½Ðµ_Ð·Ð°Ð±Ñ‹Ñ‚ÑŒ"),
    (r"(?iu)\bÐ½Ðµ\s+Ð·Ð°Ð±ÑƒÐ´ÑŒ\b", "weak:Ð½Ðµ_Ð·Ð°Ð±ÑƒÐ´ÑŒ"),
)

HELP_QUERY_PATTERNS = (
    r"(?iu)\bhow\s+to\s+(?:list|see|view|remove|cancel)\s+reminder",
    r"(?iu)\b(?:ÐºÐ°Ðº|Ð³Ð´Ðµ)\s+(?:Ð¿Ð¾ÑÐ¼Ð¾Ñ‚Ñ€ÐµÑ‚ÑŒ|ÑƒÐ²Ð¸Ð´ÐµÑ‚ÑŒ|ÑƒÐ´Ð°Ð»Ð¸Ñ‚ÑŒ|Ð¾Ñ‚Ð¼ÐµÐ½Ð¸Ñ‚ÑŒ)\s+Ð½Ð°Ð¿Ð¾Ð¼Ð¸Ð½Ð°Ð½Ð¸\w*",
)

REPEAT_PATTERNS = (
    r"(?iu)\bevery\s+(?:\d+\s*)?(?:second|seconds|secs?|sec|minute|minutes|mins?|min|hour|hours|hrs?|hr|day|days|week|weeks)\b",
    r"(?iu)\bevery\s+(?:hour|day|week)\b",
    r"(?iu)\bÐºÐ°Ð¶Ð´(?:Ñ‹Ð¹|Ð°Ñ|Ð¾Ðµ|ÑƒÑŽ|Ñ‹Ðµ)\s+(?:\d+\s*)?(?:ÑÐµÐº\w*|Ð¼Ð¸Ð½\w*|Ñ‡Ð°Ñ\w*|Ð´Ð½\w*|Ð´ÐµÐ½\w*|Ð½ÐµÐ´ÐµÐ»\w*)\b",
    r"(?iu)\bÑ€Ð°Ð·\s+Ð²\s+(?:\d+\s*)?(?:ÑÐµÐº\w*|Ð¼Ð¸Ð½\w*|Ñ‡Ð°Ñ\w*|Ð´Ð½\w*|Ð´ÐµÐ½\w*|Ð½ÐµÐ´ÐµÐ»\w*)\b",
)

TIME_PATTERNS = (
    r"(?iu)\bin\s+\d+\s*(?:seconds?|secs?|sec|s|minutes?|mins?|min|m|hours?|hrs?|hr|h|days?)\b",
    r"(?iu)\bÑ‡ÐµÑ€ÐµÐ·\s+\d+\s*(?:ÑÐµÐº\w*|Ð¼Ð¸Ð½\w*|Ñ‡Ð°Ñ\w*|Ð´Ð½\w*|Ð´ÐµÐ½\w*)\b",
    r"(?iu)\b\d{1,2}[:\.]\d{2}\b",
    r"(?iu)\b(?:at|Ð²)\s+\d{1,2}\b",
    r"(?iu)\b(?:today|tomorrow|ÑÐµÐ³Ð¾Ð´Ð½Ñ|Ð·Ð°Ð²Ñ‚Ñ€Ð°)\b",
)

PAYLOAD_HINT_PATTERNS = (
    r'(?s)["\'](.+?)["\']',
    r"(?iu)\b(?:about|to|message|text|send|write|notify|post|ping)\b\s+.+$",
    r"(?iu)\b(?:Ð½Ð°Ð¿Ð¾Ð¼Ð½Ð¸(?:\s+Ð¼Ð½Ðµ)?|Ð½Ð°Ð¿Ð¸ÑˆÐ¸|Ð¿Ð¸ÑˆÐ¸|Ð¾Ñ‚Ð¿Ñ€Ð°Ð²ÑŒ|Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐ¹|ÑÐºÐ¸Ð½ÑŒ|ÑÐ¾Ð¾Ð±Ñ‰Ð°Ð¹)\b\s+.+$",
)

DELIVERY_VERB_PATTERNS = (
    r"(?iu)\b(?:send|write|notify|post|ping)\b",
    r"(?iu)\b(?:Ð½Ð°Ð¿Ð¸ÑˆÐ¸|Ð¿Ð¸ÑˆÐ¸|Ð¾Ñ‚Ð¿Ñ€Ð°Ð²ÑŒ|Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐ¹|ÑÐºÐ¸Ð½ÑŒ|ÑÐ¾Ð¾Ð±Ñ‰Ð°Ð¹)\b",
)

def detect_schedule_intent(prompt: str) -> ScheduleIntentDetection:
    normalized = " ".join((prompt or "").strip().split())
    lowered = normalized.casefold()
    if not lowered:
        return ScheduleIntentDetection(level=ReminderIntentLevel.NONE)

    matched_signals: list[str] = []
    if any(re.search(pattern, normalized) for pattern in HELP_QUERY_PATTERNS):
        return ScheduleIntentDetection(
            level=ReminderIntentLevel.NONE,
            matched_signals=["meta:help_query"],
        )

    has_explicit_verb = False
    for pattern, signal in EXPLICIT_REMINDER_PATTERNS:
        if re.search(pattern, normalized):
            has_explicit_verb = True
            matched_signals.append(signal)
    explicit_fallback_markers = (
        "\u043d\u0430\u043f\u043e\u043c\u043d\u0438",
        "\u043f\u043e\u0441\u0442\u0430\u0432\u044c \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435",
        "\u0441\u043e\u0437\u0434\u0430\u0439 \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435",
        "\u0443\u0441\u0442\u0430\u043d\u043e\u0432\u0438 \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435",
        "\u043f\u043e\u0441\u0442\u0430\u0432\u044c \u0442\u0430\u0439\u043c\u0435\u0440",
        "\u0437\u0430\u043f\u0443\u0441\u0442\u0438 \u0442\u0430\u0439\u043c\u0435\u0440",
    )
    if not has_explicit_verb and any(marker in lowered for marker in explicit_fallback_markers):
        has_explicit_verb = True
        matched_signals.append("explicit:fallback_ru")

    has_weak_verb = False
    for pattern, signal in WEAK_REMINDER_PATTERNS:
        if re.search(pattern, normalized):
            has_weak_verb = True
            matched_signals.append(signal)
    weak_fallback_markers = (
        "\u043d\u0435 \u0437\u0430\u0431\u044b\u0442\u044c",
        "\u043d\u0430\u0434\u043e \u043d\u0435 \u0437\u0430\u0431\u044b\u0442\u044c",
        "\u043d\u0435 \u0437\u0430\u0431\u0443\u0434\u044c",
    )
    if not has_weak_verb and any(marker in lowered for marker in weak_fallback_markers):
        has_weak_verb = True
        matched_signals.append("weak:fallback_ru")

    has_time_expression = any(re.search(pattern, normalized) for pattern in TIME_PATTERNS)
    if not has_time_expression and any(
        marker in lowered
        for marker in (
            "\u0437\u0430\u0432\u0442\u0440\u0430",
            "\u0441\u0435\u0433\u043e\u0434\u043d\u044f",
            "\u0432\u0435\u0447\u0435\u0440",
            "\u0432\u0435\u0447\u0435\u0440\u0430",
            "\u0443\u0442\u0440\u043e\u043c",
            "\u043d\u043e\u0447\u044c\u044e",
        )
    ):
        has_time_expression = True
    if has_time_expression:
        matched_signals.append("signal:time_expression")

    has_repeat_pattern = any(re.search(pattern, normalized) for pattern in REPEAT_PATTERNS)
    if not has_repeat_pattern and any(
        marker in lowered
        for marker in (
            "\u043a\u0430\u0436\u0434\u044b\u0439 \u0447\u0430\u0441",
            "\u043a\u0430\u0436\u0434\u044b\u0439 \u0434\u0435\u043d\u044c",
            "\u0440\u0430\u0437 \u0432 \u0434\u0435\u043d\u044c",
        )
    ):
        has_repeat_pattern = True
    if has_repeat_pattern:
        matched_signals.append("signal:repeat_pattern")

    has_payload = any(re.search(pattern, normalized) for pattern in PAYLOAD_HINT_PATTERNS)
    if has_payload:
        matched_signals.append("signal:payload")
    has_delivery_verb = any(
        re.search(pattern, normalized) for pattern in DELIVERY_VERB_PATTERNS
    )
    if has_delivery_verb:
        matched_signals.append("signal:delivery_verb")

    level = ReminderIntentLevel.NONE
    if has_explicit_verb and (has_time_expression or has_repeat_pattern):
        level = ReminderIntentLevel.STRONG
    elif has_repeat_pattern and has_payload and has_delivery_verb:
        level = ReminderIntentLevel.STRONG
    elif has_explicit_verb:
        level = ReminderIntentLevel.WEAK
    elif has_weak_verb and (has_time_expression or has_repeat_pattern):
        level = ReminderIntentLevel.WEAK
    elif has_weak_verb:
        level = ReminderIntentLevel.WEAK

    return ScheduleIntentDetection(
        level=level,
        matched_signals=matched_signals,
        has_time_expression=has_time_expression,
        has_reminder_verb=has_explicit_verb or has_weak_verb,
        has_message_payload=has_payload,
        has_repeat_pattern=has_repeat_pattern,
    )


def looks_like_schedule_request(prompt: str) -> bool:
    return detect_schedule_intent(prompt).level == ReminderIntentLevel.STRONG


def parse_reminder_request(prompt: str, *, allow_default_message: bool = True) -> ReminderParseResult:
    normalized = " ".join((prompt or "").strip().split())
    detection = detect_schedule_intent(normalized)
    result = ReminderParseResult(
        ok=False,
        intent_level=detection.level,
        matched_signals=detection.matched_signals,
        source_text=normalized,
    )
    LOGGER.debug(
        "schedule_intent_detected level=%s signals=%s",
        detection.level.value,
        ",".join(detection.matched_signals) or "-",
    )
    if detection.level == ReminderIntentLevel.NONE:
        result.parse_error = "no_schedule_intent"
        return result
    if detection.level != ReminderIntentLevel.STRONG:
        result.parse_error = "intent_not_strong_enough"
        return result

    lowered = normalized.casefold()
    now = datetime.now(timezone.utc)
    repeat_interval_seconds = parse_repeat_interval(lowered)
    fire_at = parse_fire_at(normalized, lowered, now, repeat_interval_seconds)
    if fire_at is None:
        result.parse_error = "time_not_parsed"
        return result

    message_text = extract_message(normalized)
    if not message_text:
        if not allow_default_message:
            result.parse_error = "message_not_parsed"
            return result
        message_text = "\u23f0 \u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435."
        result.parse_warnings.append("used_default_message")
    elif not message_text.startswith(("\u23f0", "\u2709", "\U0001F514")):
        message_text = f"\u23f0 {message_text}"

    target_chat = extract_target_chat(normalized)
    label = _build_schedule_label(fire_at, message_text, repeat_interval_seconds)

    result.ok = True
    result.fire_at = fire_at
    result.message_text = message_text
    result.target_chat = target_chat
    result.label = label
    result.repeat_interval_seconds = repeat_interval_seconds
    LOGGER.debug(
        "schedule_parse_result ok=%s level=%s error=%s repeat=%s signals=%s",
        result.ok,
        result.intent_level.value,
        result.parse_error or "-",
        result.repeat_interval_seconds or 0,
        ",".join(result.matched_signals) or "-",
    )
    return validate_parsed_reminder(result)


def parse_repeat_interval(lowered: str) -> int | None:
    fixed_patterns = (
        (r"(?iu)\bevery\s+hour\b", 3600),
        (r"(?iu)\bevery\s+day\b", 86400),
        (r"(?iu)\bevery\s+week\b", 604800),
        (
            r"(?iu)\b(?:\u043a\u0430\u0436\u0434(?:\u044b\u0439|\u0430\u044f|\u043e\u0435|\u0443\u044e))\s+\u0447\u0430\u0441\b",
            3600,
        ),
        (
            r"(?iu)\b(?:\u043a\u0430\u0436\u0434(?:\u044b\u0439|\u0430\u044f|\u043e\u0435|\u0443\u044e))\s+\u0434\u0435\u043d\u044c\b",
            86400,
        ),
        (r"(?iu)\b(?:\u0440\u0430\u0437)\s+\u0432\s+\u0447\u0430\u0441\b", 3600),
        (r"(?iu)\b(?:\u0440\u0430\u0437)\s+\u0432\s+\u0434\u0435\u043d\u044c\b", 86400),
    )
    for pattern, value in fixed_patterns:
        if re.search(pattern, lowered):
            return value

    numeric_patterns = (
        (r"(?iu)\bevery\s+(\d+)\s*(seconds?|secs?|sec|s)\b", 1),
        (r"(?iu)\bevery\s+(\d+)\s*(minutes?|mins?|min|m)\b", 60),
        (r"(?iu)\bevery\s+(\d+)\s*(hours?|hrs?|hr|h)\b", 3600),
        (r"(?iu)\bevery\s+(\d+)\s*(days?|d)\b", 86400),
        (r"(?iu)\bevery\s+(\d+)\s*(weeks?)\b", 604800),
        (
            r"(?iu)\b(?:\u043a\u0430\u0436\u0434(?:\u044b\u0435)?)\s+(\d+)\s*(?:\u0441\u0435\u043a\w*)\b",
            1,
        ),
        (
            r"(?iu)\b(?:\u043a\u0430\u0436\u0434(?:\u044b\u0435)?)\s+(\d+)\s*(?:\u043c\u0438\u043d\w*)\b",
            60,
        ),
        (
            r"(?iu)\b(?:\u043a\u0430\u0436\u0434(?:\u044b\u0435)?)\s+(\d+)\s*(?:\u0447\u0430\u0441\w*)\b",
            3600,
        ),
        (
            r"(?iu)\b(?:\u043a\u0430\u0436\u0434(?:\u044b\u0435)?)\s+(\d+)\s*(?:\u0434\u043d\w*|\u0434\u0435\u043d\w*)\b",
            86400,
        ),
        (
            r"(?iu)\b(?:\u0440\u0430\u0437)\s+\u0432\s+(\d+)\s*(?:\u0441\u0435\u043a\w*)\b",
            1,
        ),
        (
            r"(?iu)\b(?:\u0440\u0430\u0437)\s+\u0432\s+(\d+)\s*(?:\u043c\u0438\u043d\w*)\b",
            60,
        ),
        (
            r"(?iu)\b(?:\u0440\u0430\u0437)\s+\u0432\s+(\d+)\s*(?:\u0447\u0430\u0441\w*)\b",
            3600,
        ),
        (
            r"(?iu)\b(?:\u0440\u0430\u0437)\s+\u0432\s+(\d+)\s*(?:\u0434\u043d\w*|\u0434\u0435\u043d\w*)\b",
            86400,
        ),
    )
    for pattern, multiplier in numeric_patterns:
        match = re.search(pattern, lowered)
        if match:
            return int(match.group(1)) * multiplier
    return None


def parse_fire_at(
    normalized: str,
    lowered: str,
    now: datetime,
    repeat_interval_seconds: int | None,
) -> datetime | None:
    time_match = re.search(r"\b(\d{1,2})[:\.](\d{2})\b", lowered)
    hour_only_match = re.search(r"(?iu)\b(?:at|\u0432)\s+(\d{1,2})\b", lowered)
    tomorrow_markers = ("tomorrow", "\u0437\u0430\u0432\u0442\u0440\u0430")
    today_markers = ("today", "\u0441\u0435\u0433\u043e\u0434\u043d\u044f")
    evening_markers = (
        "evening",
        "tonight",
        "pm",
        "p.m",
        "\u0432\u0435\u0447\u0435\u0440",
        "\u0432\u0435\u0447\u0435\u0440\u0430",
        "\u0432\u0435\u0447\u0435\u0440\u043e\u043c",
        "\u043d\u043e\u0447\u044c",
        "\u043d\u043e\u0447\u0438",
        "\u043d\u043e\u0447\u044c\u044e",
    )
    morning_markers = (
        "morning",
        "am",
        "a.m",
        "\u0443\u0442\u0440\u043e",
        "\u0443\u0442\u0440\u0430",
        "\u0443\u0442\u0440\u043e\u043c",
    )

    def _adjust_hour(hour: int) -> int:
        if any(marker in lowered for marker in evening_markers) and 1 <= hour <= 11:
            return hour + 12
        if any(marker in lowered for marker in morning_markers) and hour == 12:
            return 0
        return max(0, min(23, hour))

    if repeat_interval_seconds == 86400 and time_match:
        hour, minute = int(time_match.group(1)), int(time_match.group(2))
        hour = _adjust_hour(hour)
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now or any(marker in lowered for marker in tomorrow_markers):
            candidate += timedelta(days=1)
        return candidate

    relative_patterns = (
        (r"(?iu)\bin\s+(\d+)\s*(?:seconds?|secs?|sec|s)\b", 1),
        (r"(?iu)\bin\s+(\d+)\s*(?:minutes?|mins?|min|m)\b", 60),
        (r"(?iu)\bin\s+(\d+)\s*(?:hours?|hrs?|hr|h)\b", 3600),
        (r"(?iu)\bin\s+(\d+)\s*(?:days?)\b", 86400),
        (
            r"(?iu)\b(?:\u0447\u0435\u0440\u0435\u0437)\s+(\d+)\s*(?:\u0441\u0435\u043a\w*)\b",
            1,
        ),
        (
            r"(?iu)\b(?:\u0447\u0435\u0440\u0435\u0437)\s+(\d+)\s*(?:\u043c\u0438\u043d\w*)\b",
            60,
        ),
        (
            r"(?iu)\b(?:\u0447\u0435\u0440\u0435\u0437)\s+(\d+)\s*(?:\u0447\u0430\u0441\w*)\b",
            3600,
        ),
        (
            r"(?iu)\b(?:\u0447\u0435\u0440\u0435\u0437)\s+(\d+)\s*(?:\u0434\u043d\w*|\u0434\u0435\u043d\w*)\b",
            86400,
        ),
    )
    for pattern, multiplier in relative_patterns:
        match = re.search(pattern, lowered)
        if match:
            return now + timedelta(seconds=int(match.group(1)) * multiplier)

    if time_match:
        hour, minute = int(time_match.group(1)), int(time_match.group(2))
        hour = _adjust_hour(hour)
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if any(marker in lowered for marker in tomorrow_markers):
            candidate += timedelta(days=1)
        elif candidate <= now and not any(marker in lowered for marker in today_markers):
            candidate += timedelta(days=1)
        return candidate

    if hour_only_match:
        hour = _adjust_hour(int(hour_only_match.group(1)))
        candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if any(marker in lowered for marker in tomorrow_markers):
            candidate += timedelta(days=1)
        elif candidate <= now and not any(marker in lowered for marker in today_markers):
            candidate += timedelta(days=1)
        return candidate

    if repeat_interval_seconds is not None:
        return now + timedelta(seconds=repeat_interval_seconds)
    return None


def extract_message(normalized: str) -> str | None:
    quoted = re.search(r'(?s)["\'](.+?)["\']', normalized)
    if quoted:
        value = " ".join(quoted.group(1).split()).strip()
        if value:
            return value

    patterns = (
        r"(?iu)\b(?:about|to|message|text)\b\s+(.+)$",
        r"(?iu)\b(?:send|write|notify|post|ping)\b\s+(.+)$",
        r"(?iu)\b(?:\u043d\u0430\u043f\u043e\u043c\u043d\u0438(?:\s+\u043c\u043d\u0435)?|\u043d\u0430\u043f\u0438\u0448\u0438|\u043f\u0438\u0448\u0438|\u043e\u0442\u043f\u0440\u0430\u0432\u044c|\u043e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u0439|\u0441\u043a\u0438\u043d\u044c|\u0441\u043e\u043e\u0431\u0449\u0430\u0439)\b\s+(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            candidate = _strip_schedule_metadata(match.group(1))
            if len(candidate) >= 2:
                return candidate
    return None


def extract_target_chat(normalized: str) -> str | int | None:
    match = re.search(
        r"(?iu)(?:to\s+chat|in\s+chat|send\s+to|write\s+to|\u0432\s+\u0447\u0430\u0442|\u0432\s+ÐºÐ°Ð½Ð°Ð»|\u0434\u043b\u044f\s+Ñ‡Ð°Ñ‚Ð°)\s+(@[A-Za-z0-9_]{3,32}|-?\d{6,})",
        normalized,
    )
    if not match:
        return None
    ref = match.group(1).strip()
    return int(ref) if ref.lstrip("-").isdigit() else ref


def _strip_schedule_metadata(text: str) -> str:
    candidate = " ".join((text or "").split()).strip(" .,;:")
    cleanup_patterns = (
        r"(?iu)\bin\s+\d+\s*(?:seconds?|secs?|sec|minutes?|mins?|min|hours?|hrs?|hr|days?)\b",
        r"(?iu)\b(?:\u0447\u0435\u0440\u0435\u0437)\s+\d+\s*(?:\u0441\u0435\u043a\w*|\u043c\u0438\u043d\w*|\u0447\u0430\u0441\w*|\u0434\u043d\w*|\u0434\u0435\u043d\w*)\b",
        r"(?iu)\bevery\s+(?:\d+\s*)?(?:second|seconds|sec|minute|minutes|min|hour|hours|day|days|week|weeks)\b",
        r"(?iu)\b(?:\u043a\u0430\u0436\u0434(?:\u044b\u0439|\u0430\u044f|\u043e\u0435|\u0443\u044e|\u044b\u0435))\s+(?:\d+\s*)?(?:\u0441\u0435\u043a\w*|\u043c\u0438\u043d\w*|\u0447\u0430\u0441\w*|\u0434\u0435\u043d\w*|\u043d\u0435\u0434\u0435\u043b\w*)\b",
        r"(?iu)\b(?:\u0440\u0430\u0437)\s+\u0432\s+(?:\d+\s*)?(?:\u0441\u0435\u043a\w*|\u043c\u0438\u043d\w*|\u0447\u0430\u0441\w*|\u0434\u0435\u043d\w*|\u043d\u0435\u0434\u0435\u043b\w*)\b",
        r"(?iu)\b(?:today|tomorrow|\u0441\u0435\u0433\u043e\u0434\u043d\u044f|\u0437\u0430\u0432\u0442\u0440\u0430)\b",
        r"(?iu)\b\d{1,2}[:\.]\d{2}\b",
    )
    for pattern in cleanup_patterns:
        candidate = re.sub(pattern, " ", candidate)
    candidate = re.sub(
        r"(?iu)^(?:to|about|message|text|send|write|notify|post|ping|"
        r"\u0432|\u0434\u043b\u044f|"
        r"\u043d\u0430\u043f\u043e\u043c\u043d\u0438(?:\s+\u043c\u043d\u0435)?|"
        r"\u043d\u0430\u043f\u0438\u0448\u0438|"
        r"\u043f\u0438\u0448\u0438|"
        r"\u043e\u0442\u043f\u0440\u0430\u0432\u044c|"
        r"\u043e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u0439|"
        r"\u0441\u043a\u0438\u043d\u044c|"
        r"\u0441\u043e\u043e\u0431\u0449\u0430\u0439)\s+",
        "",
        candidate,
    )
    candidate = re.sub(r"\s{2,}", " ", candidate).strip(" .,;:")
    return candidate


def _build_schedule_label(
    fire_at: datetime, message_text: str, repeat_interval_seconds: int | None
) -> str:
    short_text = " ".join((message_text or "").split())[:40]
    if repeat_interval_seconds:
        return f"Every {_humanize_interval(repeat_interval_seconds)} - {short_text}"
    return f"{fire_at.strftime('%d.%m %H:%M')} UTC - {short_text}"


def _humanize_interval(seconds: int) -> str:
    if seconds % 604800 == 0:
        value = seconds // 604800
        unit = "week" if value == 1 else "weeks"
        return f"{value} {unit}"
    if seconds % 86400 == 0:
        value = seconds // 86400
        unit = "day" if value == 1 else "days"
        return f"{value} {unit}"
    if seconds % 3600 == 0:
        value = seconds // 3600
        unit = "hour" if value == 1 else "hours"
        return f"{value} {unit}"
    if seconds % 60 == 0:
        value = seconds // 60
        unit = "minute" if value == 1 else "minutes"
        return f"{value} {unit}"
    unit = "second" if seconds == 1 else "seconds"
    return f"{seconds} {unit}"


def validate_parsed_reminder(result: ReminderParseResult) -> ReminderParseResult:
    if result.fire_at is None:
        result.ok = False
        result.parse_error = result.parse_error or "missing_fire_at"
        return result
    if result.target_chat is not None:
        if isinstance(result.target_chat, str) and not re.fullmatch(
            r"@[A-Za-z0-9_]{3,32}", result.target_chat
        ):
            result.ok = False
            result.parse_error = "invalid_target_chat"
            return result
    if not result.message_text or not result.message_text.strip():
        result.ok = False
        result.parse_error = result.parse_error or "missing_message_text"
        return result
    if result.repeat_interval_seconds is not None and result.repeat_interval_seconds <= 0:
        result.ok = False
        result.parse_error = "invalid_repeat_interval"
        return result
    result.ok = True
    return result


# Final override for reminder patterns using ASCII-safe unicode escapes.
EXPLICIT_REMINDER_PATTERNS = (
    (r"(?iu)\bremind(?:\s+me)?\b", "explicit:remind"),
    (r"(?iu)\bset(?:\s+a)?\s+reminder\b", "explicit:set_reminder"),
    (r"(?iu)\bcreate\s+reminder\b", "explicit:create_reminder"),
    (r"(?iu)\bschedule\s+reminder\b", "explicit:schedule_reminder"),
    (r"(?iu)\balert\s+me\b", "explicit:alert_me"),
    (r"(?iu)\bset\s+timer\b", "explicit:set_timer"),
    (r"(?iu)\bstart\s+timer\b", "explicit:start_timer"),
    (r"(?iu)\bping\s+me\b", "explicit:ping_me"),
    (r"(?iu)\b\u043d\u0430\u043f\u043e\u043c\u043d\u0438(?:\s+\u043c\u043d\u0435)?\b", "explicit:napomni"),
    (r"(?iu)\b\u043f\u043e\u0441\u0442\u0430\u0432(?:\u044c|\u044c\u0442\u0435)?\s+\u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\w*\b", "explicit:set_reminder_ru"),
    (r"(?iu)\b\u0441\u043e\u0437\u0434\u0430(?:\u0439|\u0439\u0442\u0435|\u0442\u044c)\s+\u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\w*\b", "explicit:create_reminder_ru"),
    (r"(?iu)\b\u0443\u0441\u0442\u0430\u043d\u043e\u0432\u0438\s+\u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\w*\b", "explicit:install_reminder_ru"),
    (r"(?iu)\b\u043f\u043e\u0441\u0442\u0430\u0432(?:\u044c|\u044c\u0442\u0435)?\s+\u0442\u0430\u0439\u043c\u0435\u0440\b", "explicit:set_timer_ru"),
    (r"(?iu)\b\u0437\u0430\u043f\u0443\u0441\u0442\u0438\s+\u0442\u0430\u0439\u043c\u0435\u0440\b", "explicit:start_timer_ru"),
)

WEAK_REMINDER_PATTERNS = (
    (r"(?iu)\bdon'?t\s+forget\b", "weak:dont_forget"),
    (r"(?iu)\bmust\s+not\s+forget\b", "weak:must_not_forget"),
    (r"(?iu)\bremind\s+myself\b", "weak:remind_myself"),
    (r"(?iu)\btodo\s*:", "weak:todo"),
    (r"(?iu)\bto\s+do\s*:", "weak:to_do"),
    (r"(?iu)\b\u043d\u0435\s+\u0437\u0430\u0431\u044b\u0442\u044c\b", "weak:ne_zabyt"),
    (r"(?iu)\b\u043d\u0430\u0434\u043e\s+\u043d\u0435\s+\u0437\u0430\u0431\u044b\u0442\u044c\b", "weak:nado_ne_zabyt"),
    (r"(?iu)\b\u043d\u0435\s+\u0437\u0430\u0431\u0443\u0434\u044c\b", "weak:ne_zabud"),
)

HELP_QUERY_PATTERNS = (
    r"(?iu)\bhow\s+to\s+(?:list|see|view|remove|cancel)\s+reminder",
    r"(?iu)\b(?:\u043a\u0430\u043a|\u0433\u0434\u0435)\s+(?:\u043f\u043e\u0441\u043c\u043e\u0442\u0440\u0435\u0442\u044c|\u0443\u0432\u0438\u0434\u0435\u0442\u044c|\u0443\u0434\u0430\u043b\u0438\u0442\u044c|\u043e\u0442\u043c\u0435\u043d\u0438\u0442\u044c)\s+\u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\w*",
)

REPEAT_PATTERNS = (
    r"(?iu)\bevery\s+(?:\d+\s*)?(?:second|seconds|secs?|sec|minute|minutes|mins?|min|hour|hours|hrs?|hr|day|days|week|weeks)\b",
    r"(?iu)\bevery\s+(?:hour|day|week)\b",
    r"(?iu)\b\u043a\u0430\u0436\u0434(?:\u044b\u0439|\u0430\u044f|\u043e\u0435|\u0443\u044e|\u044b\u0435)\s+(?:\d+\s*)?(?:\u0441\u0435\u043a\w*|\u043c\u0438\u043d\w*|\u0447\u0430\u0441\w*|\u0434\u043d\w*|\u0434\u0435\u043d\w*|\u043d\u0435\u0434\u0435\u043b\w*)\b",
    r"(?iu)\b\u0440\u0430\u0437\s+\u0432\s+(?:\d+\s*)?(?:\u0441\u0435\u043a\w*|\u043c\u0438\u043d\w*|\u0447\u0430\u0441\w*|\u0434\u043d\w*|\u0434\u0435\u043d\w*|\u043d\u0435\u0434\u0435\u043b\w*)\b",
)

TIME_PATTERNS = (
    r"(?iu)\bin\s+\d+\s*(?:seconds?|secs?|sec|s|minutes?|mins?|min|m|hours?|hrs?|hr|h|days?)\b",
    r"(?iu)\b\u0447\u0435\u0440\u0435\u0437\s+\d+\s*(?:\u0441\u0435\u043a\w*|\u043c\u0438\u043d\w*|\u0447\u0430\u0441\w*|\u0434\u043d\w*|\u0434\u0435\u043d\w*)\b",
    r"(?iu)\b\d{1,2}[:\.]\d{2}\b",
    r"(?iu)\b(?:at|\u0432)\s+\d{1,2}\b",
    r"(?iu)\b(?:today|tomorrow|\u0441\u0435\u0433\u043e\u0434\u043d\u044f|\u0437\u0430\u0432\u0442\u0440\u0430)\b",
)

PAYLOAD_HINT_PATTERNS = (
    r'(?s)["\'](.+?)["\']',
    r"(?iu)\b(?:about|to|message|text|send|write|notify|post|ping)\b\s+.+$",
    r"(?iu)\b(?:\u043d\u0430\u043f\u043e\u043c\u043d\u0438(?:\s+\u043c\u043d\u0435)?|\u043d\u0430\u043f\u0438\u0448\u0438|\u043f\u0438\u0448\u0438|\u043e\u0442\u043f\u0440\u0430\u0432\u044c|\u043e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u0439|\u0441\u043a\u0438\u043d\u044c|\u0441\u043e\u043e\u0431\u0449\u0430\u0439)\b\s+.+$",
)

DELIVERY_VERB_PATTERNS = (
    r"(?iu)\b(?:send|write|notify|post|ping)\b",
    r"(?iu)\b(?:\u043d\u0430\u043f\u0438\u0448\u0438|\u043f\u0438\u0448\u0438|\u043e\u0442\u043f\u0440\u0430\u0432\u044c|\u043e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u0439|\u0441\u043a\u0438\u043d\u044c|\u0441\u043e\u043e\u0431\u0449\u0430\u0439)\b",
)

