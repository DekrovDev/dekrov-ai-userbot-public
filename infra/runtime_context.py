from __future__ import annotations

from typing import Any, Iterable

from infra.telegram_compat import prepare_pyrogram_runtime

prepare_pyrogram_runtime()

from pyrogram import enums


def get_chat_type_label(chat: Any | None) -> str:
    if chat is None:
        return "unknown"

    chat_type = getattr(chat, "type", None)
    if chat_type == enums.ChatType.PRIVATE:
        return "private"
    if chat_type == enums.ChatType.BOT:
        return "bot"
    if chat_type == enums.ChatType.GROUP:
        return "group"
    if chat_type == enums.ChatType.SUPERGROUP:
        return "supergroup"
    if chat_type == enums.ChatType.CHANNEL:
        return "channel"
    return "unknown"


def describe_chat_location(chat: Any | None) -> str:
    if chat is None:
        return "unknown chat"

    chat_type = getattr(chat, "type", None)
    if chat_type == enums.ChatType.PRIVATE:
        first_name = getattr(chat, "first_name", "") or ""
        last_name = getattr(chat, "last_name", "") or ""
        username = getattr(chat, "username", None)
        full_name = f"{first_name} {last_name}".strip()
        if username and full_name:
            return f"private chat with @{username} ({full_name})"
        if username:
            return f"private chat with @{username}"
        if full_name:
            return f"private chat with {full_name}"
        return "private chat"

    if chat_type == enums.ChatType.BOT:
        title = getattr(chat, "title", None) or getattr(chat, "first_name", None)
        return f'bot chat "{title}"' if title else "bot chat"

    if chat_type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        title = getattr(chat, "title", None) or "unnamed group"
        return f'group "{title}"'

    if chat_type == enums.ChatType.CHANNEL:
        title = getattr(chat, "title", None) or "unnamed channel"
        return f'channel "{title}"'

    return "chat"


def _normalize_items(items: Iterable[str] | None) -> str | None:
    if not items:
        return None
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    if not cleaned:
        return None
    return "; ".join(cleaned)


def build_runtime_context_block(
    *,
    interface: str,
    transport: str,
    actor: str,
    chat: Any | None = None,
    reply_surface: str | None = None,
    memory_scope: str | None = None,
    capabilities: Iterable[str] | None = None,
    restrictions: Iterable[str] | None = None,
    notes: Iterable[str] | None = None,
) -> str:
    lines = [
        "Runtime context:",
        f"- interface: {interface}",
        f"- transport: {transport}",
        f"- actor: {actor}",
    ]

    if reply_surface:
        lines.append(f"- reply_surface: {reply_surface}")

    lines.append(f"- chat_type: {get_chat_type_label(chat)}")
    lines.append(f"- location: {describe_chat_location(chat)}")

    chat_id = getattr(chat, "id", None)
    if chat_id is not None:
        lines.append(f"- chat_id: {chat_id}")

    if memory_scope:
        lines.append(f"- memory_scope: {memory_scope}")

    capabilities_line = _normalize_items(capabilities)
    if capabilities_line:
        lines.append(f"- capabilities: {capabilities_line}")

    restrictions_line = _normalize_items(restrictions)
    if restrictions_line:
        lines.append(f"- restrictions: {restrictions_line}")

    notes_line = _normalize_items(notes)
    if notes_line:
        lines.append(f"- notes: {notes_line}")

    return "\n".join(lines)
