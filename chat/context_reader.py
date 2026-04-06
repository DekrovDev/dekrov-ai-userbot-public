from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from infra.telegram_compat import prepare_pyrogram_runtime

prepare_pyrogram_runtime()

from pyrogram import Client
from pyrogram.types import Message


@dataclass(slots=True)
class ContextLine:
    message_id: int
    author: str
    text: str
    timestamp: str
    reply_to_message_id: int | None = None


class ContextReader:
    def __init__(self, client: Client, owner_user_id: int, owner_label: str = "ProjectOwner") -> None:
        self._client = client
        self._owner_user_id = owner_user_id
        self._owner_label = owner_label or "ProjectOwner"

    async def collect_chat_context(
        self,
        chat_id: int | str,
        *,
        limit: int = 18,
        within_hours: int | None = None,
        scan_limit: int = 120,
        exclude_message_id: int | None = None,
    ) -> list[ContextLine]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=within_hours) if within_hours and within_hours > 0 else None
        collected: list[ContextLine] = []
        effective_scan_limit = max(limit * 4, scan_limit)

        async for message in self._client.get_chat_history(chat_id, limit=effective_scan_limit):
            if exclude_message_id is not None and message.id == exclude_message_id:
                continue
            line = self._to_context_line(message)
            if line is None:
                continue
            if cutoff is not None and self._message_datetime(message) < cutoff:
                if collected:
                    break
                continue
            collected.append(line)
            if len(collected) >= limit:
                break

        collected.reverse()
        return collected

    async def find_messages(
        self,
        chat_id: int | str,
        query: str,
        *,
        limit: int = 8,
        within_hours: int | None = None,
        scan_limit: int = 180,
    ) -> list[ContextLine]:
        query_terms = [term for term in query.casefold().split() if term]
        if not query_terms:
            return []

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=within_hours) if within_hours and within_hours > 0 else None
        matches: list[ContextLine] = []

        async for message in self._client.get_chat_history(chat_id, limit=max(limit * 8, scan_limit)):
            line = self._to_context_line(message)
            if line is None:
                continue
            if cutoff is not None and self._message_datetime(message) < cutoff:
                if matches:
                    break
                continue

            searchable = line.text.casefold()
            if not all(term in searchable for term in query_terms):
                continue

            matches.append(line)
            if len(matches) >= limit:
                break

        matches.reverse()
        return matches

    def format_context(self, lines: list[ContextLine]) -> str:
        if not lines:
            return "No useful recent chat context."

        rendered: list[str] = []
        for line in lines:
            reply_hint = f" ->#{line.reply_to_message_id}" if line.reply_to_message_id else ""
            rendered.append(f"[{line.timestamp}] {line.author}{reply_hint}: {line.text}")
        return "\n".join(rendered)

    def _to_context_line(self, message: Message) -> ContextLine | None:
        if getattr(message, "empty", False):
            return None
        if getattr(message, "service", None):
            return None
        if getattr(message, "new_chat_members", None) or getattr(message, "left_chat_member", None):
            return None
        if getattr(message, "pinned_message", None) or getattr(message, "video_chat_started", None):
            return None
        if getattr(message, "video_chat_ended", None) or getattr(message, "video_chat_members_invited", None):
            return None
        if getattr(message, "sticker", None) or getattr(message, "dice", None):
            return None

        text = (message.text or message.caption or "").strip()
        if not text:
            return None
        if self._is_noise_text(text):
            return None

        author = self._author_label(message)
        timestamp = self._message_datetime(message).astimezone(timezone.utc).strftime("%H:%M")
        return ContextLine(
            message_id=message.id,
            author=author,
            text=self._truncate(text, 350),
            timestamp=timestamp,
            reply_to_message_id=getattr(message, "reply_to_message_id", None),
        )

    def _author_label(self, message: Message) -> str:
        sender_chat = getattr(message, "sender_chat", None)
        if sender_chat is not None:
            return getattr(sender_chat, "title", None) or "Chat"

        user = getattr(message, "from_user", None)
        if user is None:
            return "Unknown"
        if user.id == self._owner_user_id:
            return self._owner_label
        username = getattr(user, "username", None)
        if username:
            return f"@{username}"
        full_name = " ".join(part for part in [getattr(user, "first_name", None), getattr(user, "last_name", None)] if part)
        return full_name or f"user_{user.id}"

    def _is_noise_text(self, text: str) -> bool:
        stripped = text.strip()
        if len(stripped) < 2:
            return True
        return not any(char.isalnum() for char in stripped)

    def _message_datetime(self, message: Message) -> datetime:
        date = getattr(message, "date", None)
        if isinstance(date, datetime):
            if date.tzinfo is None:
                return date.replace(tzinfo=timezone.utc)
            return date
        return datetime.now(timezone.utc)

    def _truncate(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 1].rstrip() + "â€¦"

