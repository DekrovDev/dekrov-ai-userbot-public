from __future__ import annotations

"""
visitor_inbox.py - Visitor -> Owner question system with persistence.

Flow:
1. Visitor presses "ask owner"
2. Bot asks them to type a question
3. Question is stored in inbox and owner receives a notification
4. Owner replies via /vreply <id> <text>
5. Reply is sent back to the visitor
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from infra.json_atomic import atomic_write_json

LOGGER = logging.getLogger("assistant.visitor.inbox")

_QUESTION_TTL = 86400  # 24 hours


@dataclass
class InboxMessage:
    id: int
    user_id: int
    username: str | None
    first_name: str | None
    question: str
    created_at: float = field(default_factory=time.time)
    answered: bool = False
    answer: str | None = None

    @property
    def display_name(self) -> str:
        if self.first_name:
            return self.first_name
        if self.username:
            return f"@{self.username}"
        return f"user_{self.user_id}"

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > _QUESTION_TTL

    @property
    def age_str(self) -> str:
        age = time.time() - self.created_at
        if age < 60:
            return "Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ñ‡Ñ‚Ð¾"
        if age < 3600:
            return f"{int(age / 60)} Ð¼Ð¸Ð½ Ð½Ð°Ð·Ð°Ð´"
        if age < 86400:
            return f"{int(age / 3600)} Ñ‡ Ð½Ð°Ð·Ð°Ð´"
        return f"{int(age / 86400)} Ð´ Ð½Ð°Ð·Ð°Ð´"


class VisitorInbox:
    """Stores visitor questions and owner replies."""

    def __init__(self, path: Path | None = None) -> None:
        self._messages: dict[int, InboxMessage] = {}
        self._pending_question: dict[int, bool] = {}
        self._lock = asyncio.Lock()
        self._next_id = 1
        self._path = path

    async def load(self) -> dict[int, InboxMessage]:
        async with self._lock:
            if self._path is None:
                return dict(self._messages)

            if not self._path.exists():
                await self._write_locked()
                return dict(self._messages)

            try:
                raw = await asyncio.to_thread(self._path.read_text, encoding="utf-8")
                payload = json.loads(raw or "{}")
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                LOGGER.warning("visitor_inbox_load_failed", exc_info=True)
                payload = {}

            messages_payload = payload.get("messages", {})
            pending_payload = payload.get("pending_question", [])
            next_id = payload.get("next_id", 1)

            self._messages = {}
            if isinstance(messages_payload, dict):
                for msg_id_str, item in messages_payload.items():
                    try:
                        msg_id = int(msg_id_str)
                    except (TypeError, ValueError):
                        continue
                    if not isinstance(item, dict):
                        continue
                    self._messages[msg_id] = self._message_from_dict(msg_id, item)

            self._pending_question = {}
            if isinstance(pending_payload, list):
                for user_id in pending_payload:
                    try:
                        self._pending_question[int(user_id)] = True
                    except (TypeError, ValueError):
                        continue

            try:
                self._next_id = max(1, int(next_id))
            except (TypeError, ValueError):
                self._next_id = 1

            self._normalize_locked()
            await self._write_locked()
            return dict(self._messages)

    # ========================
    # VISITOR SIDE
    # ========================

    async def set_awaiting_question(self, user_id: int) -> None:
        async with self._lock:
            self._pending_question[user_id] = True
            await self._write_locked()

    async def is_awaiting_question(self, user_id: int) -> bool:
        async with self._lock:
            return self._pending_question.get(user_id, False)

    async def submit_question(
        self,
        user_id: int,
        question: str,
        username: str | None = None,
        first_name: str | None = None,
    ) -> InboxMessage:
        async with self._lock:
            self._pending_question.pop(user_id, None)
            msg = InboxMessage(
                id=self._next_id,
                user_id=user_id,
                username=username,
                first_name=first_name,
                question=question,
            )
            self._messages[self._next_id] = msg
            self._next_id += 1
            await self._write_locked()
            return msg

    async def cancel_question(self, user_id: int) -> None:
        async with self._lock:
            self._pending_question.pop(user_id, None)
            await self._write_locked()

    async def get_reply_for_user(self, user_id: int) -> InboxMessage | None:
        async with self._lock:
            for msg in self._messages.values():
                if msg.user_id == user_id and msg.answered and msg.answer:
                    return msg
        return None

    # ========================
    # OWNER SIDE
    # ========================

    async def get_message(self, msg_id: int) -> InboxMessage | None:
        async with self._lock:
            return self._messages.get(msg_id)

    async def reply_to(self, msg_id: int, answer: str) -> InboxMessage | None:
        async with self._lock:
            msg = self._messages.get(msg_id)
            if msg is None:
                return None
            msg.answered = True
            msg.answer = answer
            await self._write_locked()
            return msg

    async def delete_message(self, msg_id: int) -> bool:
        async with self._lock:
            if msg_id not in self._messages:
                return False
            del self._messages[msg_id]
            await self._write_locked()
            return True

    async def list_unanswered(self) -> list[InboxMessage]:
        async with self._lock:
            return [
                message
                for message in self._messages.values()
                if not message.answered and not message.is_expired
            ]

    async def list_all(self) -> list[InboxMessage]:
        async with self._lock:
            return [
                message for message in self._messages.values() if not message.is_expired
            ]

    async def cleanup_expired(self) -> int:
        async with self._lock:
            expired = [msg_id for msg_id, msg in self._messages.items() if msg.is_expired]
            for msg_id in expired:
                del self._messages[msg_id]
            if expired:
                await self._write_locked()
            return len(expired)

    async def format_inbox(self) -> str:
        messages = await self.list_all()
        if not messages:
            return "ðŸ“­ Ð’Ñ…Ð¾Ð´ÑÑ‰Ð¸Ñ… Ð²Ð¾Ð¿Ñ€Ð¾ÑÐ¾Ð² Ð¾Ñ‚ Ð¿Ð¾ÑÐµÑ‚Ð¸Ñ‚ÐµÐ»ÐµÐ¹ Ð¿Ð¾ÐºÐ° Ð½ÐµÑ‚."

        unanswered = [m for m in messages if not m.answered]
        answered = [m for m in messages if m.answered]

        lines = [f"<b>ðŸ“¬ Ð’Ñ…Ð¾Ð´ÑÑ‰Ð¸Ðµ Ð²Ð¾Ð¿Ñ€Ð¾ÑÑ‹ ({len(messages)})</b>\n"]

        if unanswered:
            lines.append(f"<b>Ð–Ð´ÑƒÑ‚ Ð¾Ñ‚Ð²ÐµÑ‚Ð° ({len(unanswered)}):</b>")
            for msg in unanswered[:10]:
                q_short = (
                    msg.question[:80] + "..." if len(msg.question) > 80 else msg.question
                )
                lines.append(
                    f"<b>#{msg.id}</b> {msg.display_name} â€¢ {msg.age_str}\n"
                    f"  {q_short}"
                )
            lines.append("")

        if answered:
            lines.append(f"<b>ÐžÑ‚Ð²ÐµÑ‡ÐµÐ½Ð½Ñ‹Ðµ ({len(answered)}):</b>")
            for msg in answered[:5]:
                lines.append(f"  #{msg.id} {msg.display_name} âœ“")

        lines.append("\nÐžÑ‚Ð²ÐµÑ‚Ð¸Ñ‚ÑŒ: <code>/vreply &lt;id&gt; &lt;Ñ‚ÐµÐºÑÑ‚&gt;</code>")
        lines.append("Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ: <code>/vdelete &lt;id&gt;</code>")
        return "\n".join(lines)

    def _normalize_locked(self) -> None:
        self._messages = {
            msg_id: msg
            for msg_id, msg in self._messages.items()
            if not msg.is_expired
        }
        if self._messages:
            self._next_id = max(self._next_id, max(self._messages) + 1)
        else:
            self._next_id = max(1, self._next_id)
        self._pending_question = {
            int(user_id): True for user_id in self._pending_question.keys()
        }

    @staticmethod
    def _message_from_dict(msg_id: int, payload: dict) -> InboxMessage:
        now = time.time()
        return InboxMessage(
            id=msg_id,
            user_id=int(payload.get("user_id", 0) or 0),
            username=str(payload.get("username")) if payload.get("username") else None,
            first_name=str(payload.get("first_name")) if payload.get("first_name") else None,
            question=str(payload.get("question", "") or ""),
            created_at=float(payload.get("created_at", now) or now),
            answered=bool(payload.get("answered", False)),
            answer=str(payload.get("answer")) if payload.get("answer") else None,
        )

    def _serialize_locked(self) -> dict[str, object]:
        return {
            "version": 1,
            "next_id": self._next_id,
            "pending_question": sorted(self._pending_question),
            "messages": {
                str(msg_id): {
                    "user_id": msg.user_id,
                    "username": msg.username,
                    "first_name": msg.first_name,
                    "question": msg.question,
                    "created_at": msg.created_at,
                    "answered": msg.answered,
                    "answer": msg.answer,
                }
                for msg_id, msg in self._messages.items()
            },
        }

    async def _write_locked(self) -> None:
        if self._path is None:
            return
        await atomic_write_json(self._path, self._serialize_locked(), indent=2)


def format_owner_notification(msg: InboxMessage) -> str:
    """Message sent to owner when visitor submits a question."""
    return (
        f"ðŸ“© <b>ÐÐ¾Ð²Ñ‹Ð¹ Ð²Ð¾Ð¿Ñ€Ð¾Ñ Ð¾Ñ‚ Ð¿Ð¾ÑÐµÑ‚Ð¸Ñ‚ÐµÐ»Ñ</b>\n\n"
        f"<b>ÐžÑ‚:</b> {msg.display_name}"
        + (f" (@{msg.username})" if msg.username else "")
        + f"\n<b>ID:</b> <code>{msg.user_id}</code>\n"
        f"<b>Ð’Ð¾Ð¿Ñ€Ð¾Ñ #{msg.id}:</b>\n{msg.question}\n\n"
        f"ÐžÑ‚Ð²ÐµÑ‚Ð¸Ñ‚ÑŒ: <code>/vreply {msg.id} Ð²Ð°Ñˆ Ð¾Ñ‚Ð²ÐµÑ‚</code>"
    )


def format_visitor_reply(answer: str, question: str) -> str:
    """Message sent to visitor when owner replies."""
    return (
        f"âœ‰ï¸ <b>ÐžÑ‚Ð²ÐµÑ‚ Ð¾Ñ‚ ProjectOwner</b>\n\n"
        f"<i>ÐÐ° Ð²Ð°Ñˆ Ð²Ð¾Ð¿Ñ€Ð¾Ñ: {question[:100]}</i>\n\n"
        f"{answer}"
    )


AWAITING_QUESTION_MESSAGE = (
    "âœï¸ <b>ÐÐ°Ð¿Ð¸ÑˆÐ¸Ñ‚Ðµ Ð²Ð°Ñˆ Ð²Ð¾Ð¿Ñ€Ð¾Ñ</b>\n\n"
    "ProjectOwner Ð¿Ð¾Ð»ÑƒÑ‡Ð¸Ñ‚ ÐµÐ³Ð¾ Ð¸ Ð¾Ñ‚Ð²ÐµÑ‚Ð¸Ñ‚ Ð»Ð¸Ñ‡Ð½Ð¾.\n"
    "<i>ÐžÑ‚Ð¿Ñ€Ð°Ð²ÑŒÑ‚Ðµ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ Ð¸Ð»Ð¸ Ð½Ð°Ð¶Ð¼Ð¸Ñ‚Ðµ /cancel Ð´Ð»Ñ Ð¾Ñ‚Ð¼ÐµÐ½Ñ‹.</i>"
)


QUESTION_SENT_MESSAGE = (
    "âœ… <b>Ð’Ð¾Ð¿Ñ€Ð¾Ñ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð»ÐµÐ½</b>\n\n"
    "ProjectOwner Ð¿Ð¾Ð»ÑƒÑ‡Ð¸Ð» Ð²Ð°ÑˆÐµ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ Ð¸ Ð¾Ñ‚Ð²ÐµÑ‚Ð¸Ñ‚, ÐºÐ°Ðº Ñ‚Ð¾Ð»ÑŒÐºÐ¾ ÑÐ¼Ð¾Ð¶ÐµÑ‚.\n"
    "<i>ÐžÑ‚Ð²ÐµÑ‚ Ð¿Ñ€Ð¸Ð´Ñ‘Ñ‚ ÑÑŽÐ´Ð° Ð² ÑÑ‚Ð¾Ñ‚ Ð¶Ðµ Ñ‡Ð°Ñ‚.</i>"
)

