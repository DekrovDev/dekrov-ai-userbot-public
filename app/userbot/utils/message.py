"""Утилиты для работы с сообщениями Telegram.

Извлечение текста, URL, медиа (фото, аудио) из сообщений.
"""

from __future__ import annotations

import base64
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyrogram.types import Message


def extract_urls_from_text(text: str | None) -> list[str]:
    """Извлечь URL из текста.

    Args:
        text: Текст для поиска URL

    Returns:
        Список найденных URL
    """
    if not text:
        return []
    return re.findall(r"https?://[^\s<>()\"']+", text, flags=re.IGNORECASE)


def extract_message_urls(message: Message | None) -> list[str]:
    """Извлечь все URL из сообщения (text, caption, web_page).

    Args:
        message: Сообщение Telegram

    Returns:
        Список уникальных URL
    """
    if message is None:
        return []
    urls: list[str] = []
    seen: set[str] = set()

    for raw in (getattr(message, "text", None), getattr(message, "caption", None)):
        for url in extract_urls_from_text(raw):
            normalized = url.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                urls.append(normalized)

    web_page = getattr(message, "web_page", None)
    page_url = getattr(web_page, "url", None) if web_page is not None else None
    if page_url and page_url not in seen:
        urls.append(page_url)

    return urls


def extract_message_text_content(message: Message | None) -> str:
    """Извлечь текстовое содержимое сообщения (text + caption).

    Args:
        message: Сообщение Telegram

    Returns:
        Объединённый текст из text и caption
    """
    if message is None:
        return ""
    parts: list[str] = []
    for raw in (getattr(message, "text", None), getattr(message, "caption", None)):
        value = (raw or "").strip()
        if value and value not in parts:
            parts.append(value)
    return "\n\n".join(parts).strip()


def extract_message_text(message: Message) -> str:
    """Извлечь текст из сообщения (text или caption).

    Args:
        message: Сообщение Telegram

    Returns:
        Текст сообщения
    """
    return (message.text or message.caption or "").strip()


def is_message_from_owner(message: Message, owner_user_id: int) -> bool:
    """Проверить, что сообщение от владельца.

    Args:
        message: Сообщение Telegram
        owner_user_id: ID владельца

    Returns:
        True если сообщение от владельца
    """
    user = getattr(message, "from_user", None)
    return bool(user and user.id == owner_user_id)


async def download_message_photo(
    client, message: Message
) -> tuple[str, str] | None:
    """Скачать фото/изображение из сообщения.

    Args:
        client: Клиент Pyrogram
        message: Сообщение Telegram

    Returns:
        Кортеж (base64_data, mime_type) или None
    """
    photo = getattr(message, "photo", None)
    doc = getattr(message, "document", None)
    sticker = getattr(message, "sticker", None)

    if photo is None and doc is None and sticker is None:
        return None
    if doc is not None:
        mime = getattr(doc, "mime_type", "") or ""
        if not mime.startswith("image/"):
            return None

    try:
        buf = await client.download_media(message, in_memory=True)
        if buf is None:
            return None
        raw = bytes(buf.getvalue()) if hasattr(buf, "getvalue") else bytes(buf)
        if not raw:
            return None
        data = base64.b64encode(raw).decode("utf-8")
        if doc is not None:
            mime = getattr(doc, "mime_type", "image/jpeg") or "image/jpeg"
        else:
            mime = "image/jpeg"
        return data, mime
    except Exception:
        return None


async def get_reply_photo_base64(
    client, message: Message
) -> tuple[str, str] | None:
    """Получить base64 фото из отвечённого сообщения.

    Args:
        client: Клиент Pyrogram
        message: Сообщение Telegram

    Returns:
        Кортеж (base64_data, mime_type) или None
    """
    try:
        reply_id = getattr(message, "reply_to_message_id", None)
        if reply_id is None:
            return None
        msgs = await client.get_messages(message.chat.id, reply_id)
        reply = msgs if not isinstance(msgs, list) else (msgs[0] if msgs else None)
        if reply is None:
            return None
        return await download_message_photo(client, reply)
    except Exception:
        return None


async def get_message_audio_bytes(
    client, message: Message
) -> tuple[bytes, str] | None:
    """Скачать voice/audio из сообщения.

    Args:
        client: Клиент Pyrogram
        message: Сообщение Telegram

    Returns:
        Кортеж (bytes_data, filename) или None
    """
    try:
        voice = getattr(message, "voice", None)
        audio = getattr(message, "audio", None)
        video_note = getattr(message, "video_note", None)
        if voice is None and audio is None and video_note is None:
            return None
        buf = await client.download_media(message, in_memory=True)
        if buf is None:
            return None
        raw = bytes(buf.getvalue()) if hasattr(buf, "getvalue") else bytes(buf)
        if not raw:
            return None
        if voice is not None or video_note is not None:
            filename = "voice.ogg"
        else:
            filename = getattr(audio, "file_name", None) or "audio.mp3"
        return raw, filename
    except Exception:
        return None


async def get_reply_audio_bytes(
    client, message: Message
) -> tuple[bytes, str] | None:
    """Получить аудио из отвечённого сообщения.

    Args:
        client: Клиент Pyrogram
        message: Сообщение Telegram

    Returns:
        Кортеж (bytes_data, filename) или None
    """
    try:
        reply_id = getattr(message, "reply_to_message_id", None)
        if reply_id is None:
            return None
        msgs = await client.get_messages(message.chat.id, reply_id)
        reply = msgs if not isinstance(msgs, list) else (msgs[0] if msgs else None)
        if reply is None:
            return None
        return await get_message_audio_bytes(client, reply)
    except Exception:
        return None


async def transcribe_message_audio(
    client, groq_client, message: Message
) -> str | None:
    """Транскрибировать voice из сообщения или отвечённого сообщения.

    Args:
        client: Клиент Pyrogram
        groq_client: Groq-клиент для транскрипции
        message: Сообщение Telegram

    Returns:
        Текст транскрипции или None
    """
    audio_data = await get_reply_audio_bytes(client, message)
    if audio_data is None:
        audio_data = await get_message_audio_bytes(client, message)
    if audio_data is None:
        return None

    audio_bytes, filename = audio_data
    return await groq_client.transcribe_audio(audio_bytes, filename)
