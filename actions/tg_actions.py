from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from infra.telegram_compat import prepare_pyrogram_runtime

prepare_pyrogram_runtime()

from pyrogram import Client, enums, raw, types as pyrogram_types
from pyrogram.errors import RPCError
from pyrogram.file_id import FileId, FileType

from chat.context_reader import ContextReader


FAVORITES_ALIASES = {
    "me", "saved", "saved messages", "saved_messages", "favorites", "favourites",
    "Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½Ð¾Ðµ", "Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½Ð¾Ð³Ð¾", "Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½Ð¾Ð¼Ñƒ", "Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½Ñ‹Ð¼", "Ð² Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½Ð¾Ðµ", "Ð² Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½Ð¾Ð¼",
    "Ð¼Ð¾Ð¸ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ", "Ð¼Ð¾Ð¸Ñ… ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ð¹",
}
CURRENT_CHAT_ALIASES = {"this chat", "current chat", "ÑÑ‚Ð¾Ñ‚ Ñ‡Ð°Ñ‚", "ÑÑ‚Ð° Ð³Ñ€ÑƒÐ¿Ð¿Ð°", "ÑÑŽÐ´Ð°", "Ñ‚ÑƒÑ‚", "here"}
STICKER_QUERY_TOKEN_RE = re.compile(r"[a-z0-9\u0400-\u04ff]{2,}", re.IGNORECASE)
STICKER_GENERIC_QUERY_TOKENS = {
    "sticker",
    "stickers",
    "emoji",
    "emoticon",
    "send",
    "forward",
    "copy",
    "similar",
    "suitable",
    "matching",
    "any",
    "with",
    "by",
    "for",
    "\u0441\u0442\u0438\u043a\u0435\u0440",
    "\u0441\u0442\u0438\u043a\u0435\u0440\u044b",
    "\u044d\u043c\u043e\u0434\u0437\u0438",
    "\u0441\u043c\u0430\u0439\u043b",
    "\u043e\u0442\u043f\u0440\u0430\u0432\u044c",
    "\u0441\u043a\u0438\u043d\u044c",
    "\u043f\u0435\u0440\u0435\u043a\u0438\u043d\u044c",
    "\u043f\u043e\u0445\u043e\u0436\u0438\u0439",
    "\u043f\u043e\u0434\u0445\u043e\u0434\u044f\u0449\u0438\u0439",
    "\u043b\u044e\u0431\u043e\u0439",
    "\u0441",
    "\u043f\u043e",
}
STICKER_EMOJI_ALIASES = {
    "kiss": ["\U0001f618", "\U0001f48b", "\U0001f60d", "\u2764\ufe0f"],
    "\u043f\u043e\u0446\u0435\u043b": ["\U0001f618", "\U0001f48b", "\U0001f60d", "\u2764\ufe0f"],
    "\u0446\u0435\u043b\u0443": ["\U0001f618", "\U0001f48b", "\U0001f60d", "\u2764\ufe0f"],
    "love": ["\u2764\ufe0f", "\U0001f496", "\U0001f970", "\U0001f60d", "\U0001f618"],
    "\u043b\u044e\u0431": ["\u2764\ufe0f", "\U0001f496", "\U0001f970", "\U0001f60d", "\U0001f618"],
    "\u0441\u0435\u0440\u0434": ["\u2764\ufe0f", "\U0001f496", "\U0001f970", "\U0001f60d", "\U0001f618"],
    "\u0441\u0435\u0440\u0434\u0435\u0447": ["\u2764\ufe0f", "\U0001f496", "\U0001f970", "\U0001f60d", "\U0001f618"],
    "laugh": ["\U0001f602", "\U0001f923", "\U0001f606", "\U0001f605"],
    "funny": ["\U0001f602", "\U0001f923", "\U0001f606", "\U0001f605"],
    "\u0441\u043c\u0435\u0445": ["\U0001f602", "\U0001f923", "\U0001f606", "\U0001f605"],
    "\u0441\u043c\u0435\u0448": ["\U0001f602", "\U0001f923", "\U0001f606", "\U0001f605"],
    "\u0440\u0436\u0430": ["\U0001f602", "\U0001f923", "\U0001f606", "\U0001f605"],
    "sad": ["\U0001f622", "\U0001f62d", "\U0001f97a", "\u2639\ufe0f"],
    "\u0433\u0440\u0443\u0441\u0442": ["\U0001f622", "\U0001f62d", "\U0001f97a", "\u2639\ufe0f"],
    "\u043f\u043b\u0430\u0447": ["\U0001f622", "\U0001f62d", "\U0001f97a", "\u2639\ufe0f"],
    "angry": ["\U0001f621", "\U0001f92c", "\U0001f620"],
    "mad": ["\U0001f621", "\U0001f92c", "\U0001f620"],
    "\u0437\u043b": ["\U0001f621", "\U0001f92c", "\U0001f620"],
    "\u0431\u0435\u0441": ["\U0001f621", "\U0001f92c", "\U0001f620"],
    "cool": ["\U0001f60e", "\U0001f525", "\U0001f918", "\U0001f44d"],
    "\u043a\u0440\u0443\u0442": ["\U0001f60e", "\U0001f525", "\U0001f918", "\U0001f44d"],
    "\u043a\u043b\u0430\u0441\u0441": ["\U0001f60e", "\U0001f525", "\U0001f918", "\U0001f44d"],
    "fire": ["\U0001f525", "\u2764\ufe0f\u200d\U0001f525"],
    "\u043e\u0433\u043e\u043d": ["\U0001f525", "\u2764\ufe0f\u200d\U0001f525"],
    "heart": ["\u2764\ufe0f", "\U0001f496", "\U0001f49b", "\U0001f49c", "\U0001f49a"],
    "cry": ["\U0001f622", "\U0001f62d", "\U0001f97a"],
    "\u043f\u0430\u043b\u0435\u0446": ["\U0001f44d"],
    "thumb": ["\U0001f44d"],
}
STICKER_LOOSE_QUERY_MARKERS = {
    "any",
    "similar",
    "suitable",
    "\u043b\u044e\u0431\u043e\u0439",
    "\u043f\u043e\u0445\u043e\u0436",
}
STICKER_SOURCE_WEIGHTS = {
    "favorites": 140,
    "recent": 120,
    "telegram_emoji": 105,
    "dialog_history": 70,
}
STICKER_DIALOG_CACHE_TTL_SECONDS = 180.0
STICKER_ACCOUNT_CACHE_TTL_SECONDS = 180.0
STICKER_EMOJI_CACHE_TTL_SECONDS = 600.0


@dataclass(slots=True)
class ResolvedReference:
    kind: str
    lookup: str | int
    label: str
    chat_id: int | None = None
    user_id: int | None = None
    username: str | None = None


@dataclass(slots=True)
class StickerQueryProfile:
    normalized_query: str
    query_tokens: list[str]
    exact_emojis: set[str]
    desired_emojis: set[str]
    allow_loose: bool
    wants_generic_any: bool


class TelegramActionService:
    def __init__(self, client: Client, context_reader: ContextReader) -> None:
        self._client = client
        self._context_reader = context_reader
        self._recent_sticker_cache: tuple[float, list[dict[str, Any]]] | None = None
        self._account_sticker_cache: tuple[float, list[dict[str, Any]]] | None = None
        self._emoji_sticker_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    async def resolve_chat(self, reference: str | int | None, *, current_chat_id: int | None = None) -> ResolvedReference:
        if reference is None:
            if current_chat_id is None:
                raise ValueError("No chat target is available.")
            return await self.resolve_chat(current_chat_id, current_chat_id=current_chat_id)
        if isinstance(reference, int):
            chat = await self._client.get_chat(reference)
            return self._chat_to_reference(chat, lookup=reference)

        raw = str(reference).strip()
        lowered = raw.casefold()
        if not raw:
            raise ValueError("Empty chat reference.")
        if lowered in FAVORITES_ALIASES:
            chat = await self._client.get_chat("me")
            return self._chat_to_reference(chat, lookup="me", label_override="Saved Messages")
        if lowered in CURRENT_CHAT_ALIASES:
            if current_chat_id is None:
                raise ValueError("Current chat target is not available.")
            chat = await self._client.get_chat(current_chat_id)
            return self._chat_to_reference(chat, lookup=current_chat_id)
        if raw.lstrip("-").isdigit():
            chat_id = int(raw)
            chat = await self._client.get_chat(chat_id)
            return self._chat_to_reference(chat, lookup=chat_id)
        if raw.startswith("@") or raw.startswith("https://t.me/") or raw.startswith("http://t.me/"):
            chat = await self._client.get_chat(raw)
            return self._chat_to_reference(chat, lookup=raw)

        direct = await self._try_get_chat(raw)
        if direct is not None:
            return self._chat_to_reference(direct, lookup=raw)

        dialogs = await self._collect_dialogs(limit=200)
        normalized = raw.casefold()
        exact_matches = [dialog for dialog in dialogs if self._dialog_matches_exact(dialog, normalized)]
        if exact_matches:
            return exact_matches[0]
        partial_matches = [dialog for dialog in dialogs if self._dialog_matches_partial(dialog, normalized)]
        if partial_matches:
            return partial_matches[0]
        raise ValueError(f'Could not resolve chat target "{raw}".')

    async def resolve_user(self, reference: str | int | None, *, fallback_user_id: int | None = None) -> ResolvedReference:
        if reference is None:
            if fallback_user_id is None:
                raise ValueError("No user target is available.")
            return await self.resolve_user(fallback_user_id)
        if isinstance(reference, int):
            user = await self._client.get_users(reference)
            return self._user_to_reference(user, lookup=reference)

        raw = str(reference).strip()
        if not raw:
            raise ValueError("Empty user reference.")
        if raw.lstrip("-").isdigit():
            return await self.resolve_user(int(raw))
        if raw.startswith("@"):
            user = await self._client.get_users(raw[1:])
            return self._user_to_reference(user, lookup=raw)
        try:
            user = await self._client.get_users(raw)
            return self._user_to_reference(user, lookup=raw)
        except Exception:
            pass

        chat_ref = await self.resolve_chat(raw)
        if chat_ref.user_id is None:
            raise ValueError(f'Could not resolve user target "{raw}".')
        return chat_ref

    async def send_message(self, chat_lookup: str | int, text: str, *, reply_to_message_id: int | None = None) -> Any:
        return await self._client.send_message(
            chat_lookup,
            text,
            reply_to_message_id=reply_to_message_id,
            disable_web_page_preview=True,
        )

    async def send_photo(
        self,
        chat_lookup: str | int,
        photo: str,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> Any:
        return await self._client.send_photo(
            chat_lookup,
            photo,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_video(
        self,
        chat_lookup: str | int,
        video: str,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> Any:
        return await self._client.send_video(
            chat_lookup,
            video,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_video_note(
        self,
        chat_lookup: str | int,
        video_note: str,
        *,
        reply_to_message_id: int | None = None,
    ) -> Any:
        return await self._client.send_video_note(
            chat_lookup,
            video_note,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_animation(
        self,
        chat_lookup: str | int,
        animation: str,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> Any:
        return await self._client.send_animation(
            chat_lookup,
            animation,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_document(
        self,
        chat_lookup: str | int,
        document: str,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> Any:
        return await self._client.send_document(
            chat_lookup,
            document,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_audio(
        self,
        chat_lookup: str | int,
        audio: str,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> Any:
        return await self._client.send_audio(
            chat_lookup,
            audio,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_voice(
        self,
        chat_lookup: str | int,
        voice: str,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> Any:
        return await self._client.send_voice(
            chat_lookup,
            voice,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_sticker(
        self,
        chat_lookup: str | int,
        sticker: str,
        *,
        reply_to_message_id: int | None = None,
    ) -> Any:
        return await self._client.send_sticker(
            chat_lookup,
            sticker,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_media_group(
        self,
        chat_lookup: str | int,
        media_items: list[dict[str, Any]],
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> Any:
        prepared_items = [
            self._build_media_group_item(
                item,
                caption=caption if index == 0 else None,
            )
            for index, item in enumerate(media_items[:10])
        ]
        if not prepared_items:
            raise ValueError("Media group must contain at least one item.")
        return await self._client.send_media_group(
            chat_lookup,
            prepared_items,
            reply_to_message_id=reply_to_message_id,
        )

    def _build_media_group_item(
        self,
        item: dict[str, Any],
        *,
        caption: str | None = None,
    ) -> Any:
        kind = str(item.get("kind", "")).strip().casefold()
        media = str(item.get("media", "")).strip()
        item_caption = str(item.get("caption", "")).strip() or caption
        if not media:
            raise ValueError("Media group item is missing media.")
        if kind == "photo":
            return pyrogram_types.InputMediaPhoto(media=media, caption=item_caption)
        if kind == "video":
            return pyrogram_types.InputMediaVideo(media=media, caption=item_caption)
        if kind == "audio":
            return pyrogram_types.InputMediaAudio(media=media, caption=item_caption)
        if kind == "document":
            return pyrogram_types.InputMediaDocument(media=media, caption=item_caption)
        raise ValueError(f"Unsupported media group item kind: {kind}")

    async def send_contact(
        self,
        chat_lookup: str | int,
        phone_number: str,
        first_name: str,
        *,
        last_name: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> Any:
        return await self._client.send_contact(
            chat_lookup,
            phone_number=phone_number,
            first_name=first_name,
            last_name=last_name,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_location(
        self,
        chat_lookup: str | int,
        latitude: float,
        longitude: float,
        *,
        reply_to_message_id: int | None = None,
    ) -> Any:
        return await self._client.send_location(
            chat_lookup,
            latitude=latitude,
            longitude=longitude,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_venue(
        self,
        chat_lookup: str | int,
        latitude: float,
        longitude: float,
        title: str,
        address: str,
        *,
        reply_to_message_id: int | None = None,
    ) -> Any:
        return await self._client.send_venue(
            chat_lookup,
            latitude=latitude,
            longitude=longitude,
            title=title,
            address=address,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_poll(
        self,
        chat_lookup: str | int,
        question: str,
        options: list[str],
        *,
        reply_to_message_id: int | None = None,
    ) -> Any:
        return await self._client.send_poll(
            chat_lookup,
            question=question,
            options=options,
            reply_to_message_id=reply_to_message_id,
        )

    async def send_dice(
        self,
        chat_lookup: str | int,
        emoji: str = "ðŸŽ²",
        *,
        reply_to_message_id: int | None = None,
    ) -> Any:
        return await self._client.send_dice(
            chat_lookup,
            emoji=emoji,
            reply_to_message_id=reply_to_message_id,
        )

    async def edit_message(self, chat_id: int | str, message_id: int, text: str) -> Any:
        return await self._client.edit_message_text(chat_id, message_id, text, disable_web_page_preview=True)

    async def edit_message_caption(self, chat_id: int | str, message_id: int, caption: str) -> Any:
        return await self._client.edit_message_caption(chat_id, message_id, caption)

    async def edit_message_media(
        self,
        chat_id: int | str,
        message_id: int,
        media_kind: str,
        media: str,
        *,
        caption: str | None = None,
    ) -> Any:
        prepared_media = self._build_edit_media_input(media_kind, media, caption=caption)
        return await self._client.edit_message_media(chat_id, message_id, prepared_media)

    def _build_edit_media_input(
        self,
        media_kind: str,
        media: str,
        *,
        caption: str | None = None,
    ) -> Any:
        kind = str(media_kind or "").strip().casefold()
        asset = str(media or "").strip()
        if not asset:
            raise ValueError("Replacement media is missing.")
        if kind == "photo":
            return pyrogram_types.InputMediaPhoto(media=asset, caption=caption)
        if kind == "video":
            return pyrogram_types.InputMediaVideo(media=asset, caption=caption)
        if kind == "animation":
            return pyrogram_types.InputMediaAnimation(media=asset, caption=caption)
        if kind == "document":
            return pyrogram_types.InputMediaDocument(media=asset, caption=caption)
        if kind == "audio":
            return pyrogram_types.InputMediaAudio(media=asset, caption=caption)
        raise ValueError(f"Unsupported edit media kind: {media_kind}")

    async def edit_message_reply_markup(
        self,
        chat_id: int | str,
        message_id: int,
        *,
        buttons: list[dict[str, str]] | None = None,
    ) -> Any:
        reply_markup = self._build_inline_reply_markup(buttons)
        return await self._client.edit_message_reply_markup(
            chat_id,
            message_id,
            reply_markup=reply_markup,
        )

    def _build_inline_reply_markup(self, buttons: list[dict[str, str]] | None) -> Any:
        if not buttons:
            return None
        row: list[Any] = []
        for button in buttons:
            text = str(button.get("text", "")).strip()
            url = str(button.get("url", "")).strip()
            callback_data = str(button.get("callback_data", "")).strip()
            if not text:
                raise ValueError("Inline button text is required.")
            if url:
                row.append(pyrogram_types.InlineKeyboardButton(text=text, url=url))
                continue
            if callback_data:
                row.append(pyrogram_types.InlineKeyboardButton(text=text, callback_data=callback_data))
                continue
            raise ValueError("Inline button must have either url or callback_data.")
        if not row:
            return None
        return pyrogram_types.InlineKeyboardMarkup([row])

    async def delete_messages(self, chat_id: int | str, message_ids: list[int]) -> Any:
        return await self._client.delete_messages(chat_id, message_ids)

    async def forward_messages(self, target_chat: str | int, source_chat: str | int, message_ids: list[int]) -> Any:
        return await self._client.forward_messages(target_chat, source_chat, message_ids)

    async def copy_message(
        self,
        target_chat: str | int,
        source_chat: str | int,
        message_id: int,
        *,
        caption: str | None = None,
    ) -> Any:
        return await self._client.copy_message(target_chat, source_chat, message_id, caption=caption)

    async def send_reaction(self, chat_id: int | str, message_id: int, emoji: str) -> Any:
        return await self._client.send_reaction(chat_id, message_id, emoji)

    async def mark_read(self, chat_id: int | str) -> Any:
        return await self._client.read_chat_history(chat_id)

    async def pin_message(self, chat_id: int | str, message_id: int) -> Any:
        return await self._client.pin_chat_message(chat_id, message_id, disable_notification=True)

    async def unpin_message(self, chat_id: int | str, message_id: int | None = None) -> Any:
        if message_id is None:
            return await self._client.unpin_all_chat_messages(chat_id)
        return await self._client.unpin_chat_message(chat_id, message_id)

    async def archive_chat(self, chat_id: int) -> Any:
        return await self._client.archive_chats([chat_id])

    async def unarchive_chat(self, chat_id: int) -> Any:
        return await self._client.unarchive_chats([chat_id])

    async def get_chat_history(self, chat_lookup: str | int, *, limit: int = 10, within_hours: int | None = None) -> list[str]:
        lines = await self._context_reader.collect_chat_context(
            chat_lookup,
            limit=max(1, min(limit, 100)),
            within_hours=within_hours,
            scan_limit=max(50, limit * 6),
        )
        return [f"[{line.timestamp}] {line.author}: {line.text}" for line in lines]

    async def get_chat_info(self, chat_lookup: str | int) -> dict[str, Any]:
        chat = await self._client.get_chat(chat_lookup)
        linked_chat = getattr(chat, "linked_chat", None)
        return {
            "id": getattr(chat, "id", None),
            "type": getattr(getattr(chat, "type", None), "value", getattr(chat, "type", None)),
            "title": getattr(chat, "title", None),
            "username": getattr(chat, "username", None),
            "first_name": getattr(chat, "first_name", None),
            "last_name": getattr(chat, "last_name", None),
            "bio": getattr(chat, "bio", None),
            "description": getattr(chat, "description", None),
            "members_count": getattr(chat, "members_count", None),
            "linked_chat": None if linked_chat is None else {
                "id": getattr(linked_chat, "id", None),
                "type": getattr(getattr(linked_chat, "type", None), "value", getattr(linked_chat, "type", None)),
                "title": getattr(linked_chat, "title", None),
                "username": getattr(linked_chat, "username", None),
            },
        }

    async def get_linked_chat_info(self, chat_lookup: str | int) -> dict[str, Any]:
        chat = await self._client.get_chat(chat_lookup)
        linked_chat = getattr(chat, "linked_chat", None)
        result = {
            "source_chat": {
                "id": getattr(chat, "id", None),
                "type": getattr(getattr(chat, "type", None), "value", getattr(chat, "type", None)),
                "title": getattr(chat, "title", None),
                "username": getattr(chat, "username", None),
                "description": getattr(chat, "description", None),
            },
            "linked_chat": None,
        }
        if linked_chat is not None:
            result["linked_chat"] = {
                "id": getattr(linked_chat, "id", None),
                "type": getattr(getattr(linked_chat, "type", None), "value", getattr(linked_chat, "type", None)),
                "title": getattr(linked_chat, "title", None),
                "username": getattr(linked_chat, "username", None),
                "description": getattr(linked_chat, "description", None),
            }
        return result

    async def get_post_comments(
        self,
        chat_lookup: str | int,
        message_id: int,
        *,
        limit: int = 5,
    ) -> dict[str, Any]:
        source_chat = await self._client.get_chat(chat_lookup)
        result: dict[str, Any] = {
            "source_chat": self._serialize_chat_brief(source_chat),
            "post_message_id": message_id,
            "discussion_chat": None,
            "discussion_message": None,
            "replies_count": 0,
            "replies": [],
        }
        try:
            discussion_message = await self._client.get_discussion_message(chat_lookup, message_id)
        except Exception:
            result["error"] = "discussion_not_found"
            return result
        discussion_chat = getattr(discussion_message, "chat", None)
        result["discussion_chat"] = self._serialize_chat_brief(discussion_chat)
        result["discussion_message"] = self._serialize_message_brief(discussion_message)
        try:
            result["replies_count"] = int(await self._client.get_discussion_replies_count(chat_lookup, message_id))
        except Exception:
            result["replies_count"] = 0
        replies: list[dict[str, Any]] = []
        async for reply in self._client.get_discussion_replies(chat_lookup, message_id, limit=max(1, min(limit, 20))):
            replies.append(self._serialize_message_brief(reply))
        result["replies"] = replies
        return result

    async def comment_channel_post(
        self,
        chat_lookup: str | int,
        message_id: int,
        text: str,
    ) -> dict[str, Any]:
        discussion_message = await self._client.get_discussion_message(chat_lookup, message_id)
        discussion_chat = getattr(discussion_message, "chat", None)
        discussion_chat_id = getattr(discussion_chat, "id", None)
        discussion_message_id = getattr(discussion_message, "id", None)
        if discussion_chat_id is None or discussion_message_id is None:
            raise ValueError("No discussion thread found for this post.")
        sent = await self.send_message(discussion_chat_id, text, reply_to_message_id=discussion_message_id)
        return {
            "source_chat": self._serialize_chat_brief(await self._client.get_chat(chat_lookup)),
            "discussion_chat": self._serialize_chat_brief(discussion_chat),
            "discussion_message": self._serialize_message_brief(discussion_message),
            "sent_message_id": getattr(sent, "id", None),
        }

    async def get_user_info(self, user_lookup: str | int) -> dict[str, Any]:
        user = await self._client.get_users(user_lookup)
        return {
            "id": getattr(user, "id", None),
            "username": getattr(user, "username", None),
            "first_name": getattr(user, "first_name", None),
            "last_name": getattr(user, "last_name", None),
            "is_bot": getattr(user, "is_bot", None),
            "is_contact": getattr(user, "is_contact", None),
            "is_mutual_contact": getattr(user, "is_mutual_contact", None),
            "is_deleted": getattr(user, "is_deleted", None),
            "is_verified": getattr(user, "is_verified", None),
            "is_scam": getattr(user, "is_scam", None),
        }

    def _chat_members_filter_from_name(self, filter_name: str | enums.ChatMembersFilter | None) -> enums.ChatMembersFilter:
        if isinstance(filter_name, enums.ChatMembersFilter):
            return filter_name
        normalized = str(filter_name or "").strip().casefold()
        mapping = {
            "": enums.ChatMembersFilter.RECENT,
            "recent": enums.ChatMembersFilter.RECENT,
            "search": enums.ChatMembersFilter.SEARCH,
            "administrators": enums.ChatMembersFilter.ADMINISTRATORS,
            "admins": enums.ChatMembersFilter.ADMINISTRATORS,
            "banned": enums.ChatMembersFilter.BANNED,
            "restricted": enums.ChatMembersFilter.RESTRICTED,
            "bots": enums.ChatMembersFilter.BOTS,
        }
        return mapping.get(normalized, enums.ChatMembersFilter.RECENT)

    def _display_name_from_user(self, user: Any) -> str:
        first_name = str(getattr(user, "first_name", "") or "").strip()
        last_name = str(getattr(user, "last_name", "") or "").strip()
        full_name = " ".join(part for part in (first_name, last_name) if part)
        if full_name:
            return full_name
        username = str(getattr(user, "username", "") or "").strip()
        if username:
            return f"@{username}"
        user_id = getattr(user, "id", None)
        return f"user#{user_id}" if user_id is not None else "unknown user"

    def _serialize_user_brief(self, user: Any | None) -> dict[str, Any] | None:
        if user is None:
            return None
        return {
            "user_id": getattr(user, "id", None),
            "username": getattr(user, "username", None),
            "display_name": self._display_name_from_user(user),
        }

    def _serialize_chat_brief(self, chat: Any | None) -> dict[str, Any] | None:
        if chat is None:
            return None
        return {
            "id": getattr(chat, "id", None),
            "type": getattr(getattr(chat, "type", None), "value", getattr(chat, "type", None)),
            "title": getattr(chat, "title", None),
            "username": getattr(chat, "username", None),
        }

    def _serialize_message_brief(self, message: Any | None) -> dict[str, Any] | None:
        if message is None:
            return None
        chat = getattr(message, "chat", None)
        user = getattr(message, "from_user", None)
        return {
            "message_id": getattr(message, "id", None),
            "chat_id": getattr(chat, "id", None) if chat is not None else None,
            "chat_title": getattr(chat, "title", None) if chat is not None else None,
            "chat_username": getattr(chat, "username", None) if chat is not None else None,
            "author_id": getattr(user, "id", None) if user is not None else None,
            "author_username": getattr(user, "username", None) if user is not None else None,
            "author_name": self._display_name_from_user(user) if user is not None else None,
            "text": (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip(),
            "date": self._serialize_datetime(getattr(message, "date", None)),
            "reply_to_message_id": getattr(message, "reply_to_message_id", None),
            "outgoing": bool(getattr(message, "outgoing", False)),
        }

    def _serialize_chat_permissions(self, permissions: Any | None) -> dict[str, bool]:
        if permissions is None:
            return {}
        keys = (
            "can_send_messages",
            "can_send_media_messages",
            "can_send_other_messages",
            "can_send_polls",
            "can_add_web_page_previews",
            "can_change_info",
            "can_invite_users",
            "can_pin_messages",
        )
        return {key: True for key in keys if bool(getattr(permissions, key, False))}

    def _serialize_chat_privileges(self, privileges: Any | None) -> dict[str, bool]:
        if privileges is None:
            return {}
        keys = (
            "can_manage_chat",
            "can_delete_messages",
            "can_manage_video_chats",
            "can_restrict_members",
            "can_promote_members",
            "can_change_info",
            "can_post_messages",
            "can_edit_messages",
            "can_invite_users",
            "can_pin_messages",
            "is_anonymous",
        )
        return {key: True for key in keys if bool(getattr(privileges, key, False))}

    def _serialize_datetime(self, value: Any | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    def _serialize_chat_member(self, member: Any) -> dict[str, Any]:
        user = getattr(member, "user", None)
        chat = getattr(member, "chat", None)
        status = getattr(member, "status", None)
        status_value = getattr(status, "value", None) or str(status or "")
        return {
            "user_id": getattr(user, "id", None),
            "username": getattr(user, "username", None),
            "display_name": self._display_name_from_user(user) if user is not None else (getattr(chat, "title", None) or "unknown member"),
            "status": status_value,
            "custom_title": getattr(member, "custom_title", None),
            "can_be_edited": getattr(member, "can_be_edited", None),
            "is_member": getattr(member, "is_member", None),
            "joined_date": self._serialize_datetime(getattr(member, "joined_date", None)),
            "until_date": self._serialize_datetime(getattr(member, "until_date", None)),
            "invited_by": self._serialize_user_brief(getattr(member, "invited_by", None)),
            "promoted_by": self._serialize_user_brief(getattr(member, "promoted_by", None)),
            "restricted_by": self._serialize_user_brief(getattr(member, "restricted_by", None)),
            "permissions": self._serialize_chat_permissions(getattr(member, "permissions", None)),
            "privileges": self._serialize_chat_privileges(getattr(member, "privileges", None)),
            "chat_id": getattr(chat, "id", None) if chat is not None else None,
            "chat_title": getattr(chat, "title", None) if chat is not None else None,
        }

    async def get_chat_members(
        self,
        chat_lookup: str | int,
        *,
        query: str = "",
        limit: int = 20,
        filter_name: str | enums.ChatMembersFilter | None = None,
    ) -> list[dict[str, Any]]:
        members: list[dict[str, Any]] = []
        member_filter = self._chat_members_filter_from_name(filter_name)
        async for member in self._client.get_chat_members(chat_lookup, query=query, limit=limit, filter=member_filter):
            members.append(self._serialize_chat_member(member))
        return members

    async def get_chat_member(self, chat_lookup: str | int, user_lookup: str | int) -> dict[str, Any]:
        member = await self._client.get_chat_member(chat_lookup, user_lookup)
        return self._serialize_chat_member(member)

    async def block_user(self, user_id: int) -> Any:
        return await self._client.block_user(user_id)

    async def unblock_user(self, user_id: int) -> Any:
        return await self._client.unblock_user(user_id)

    async def join_chat(self, reference: str | int) -> Any:
        return await self._client.join_chat(reference)

    async def leave_chat(self, chat_id: int | str) -> Any:
        return await self._client.leave_chat(chat_id)

    async def export_chat_invite_link(self, chat_id: int | str) -> str:
        return await self._client.export_chat_invite_link(chat_id)

    async def create_chat_invite_link(
        self,
        chat_id: int | str,
        *,
        name: str | None = None,
        expire_date: datetime | None = None,
        member_limit: int | None = None,
        creates_join_request: bool | None = None,
    ) -> Any:
        return await self._client.create_chat_invite_link(
            chat_id,
            name=name,
            expire_date=expire_date,
            member_limit=member_limit,
            creates_join_request=creates_join_request,
        )

    async def edit_chat_invite_link(
        self,
        chat_id: int | str,
        invite_link: str,
        *,
        name: str | None = None,
        expire_date: datetime | None = None,
        member_limit: int | None = None,
        creates_join_request: bool | None = None,
    ) -> Any:
        return await self._client.edit_chat_invite_link(
            chat_id,
            invite_link,
            name=name,
            expire_date=expire_date,
            member_limit=member_limit,
            creates_join_request=creates_join_request,
        )

    async def revoke_chat_invite_link(self, chat_id: int | str, invite_link: str) -> Any:
        return await self._client.revoke_chat_invite_link(chat_id, invite_link)

    async def approve_chat_join_request(self, chat_id: int | str, user_id: int) -> bool:
        return await self._client.approve_chat_join_request(chat_id, user_id)

    async def decline_chat_join_request(self, chat_id: int | str, user_id: int) -> bool:
        return await self._client.decline_chat_join_request(chat_id, user_id)

    async def create_supergroup(self, title: str, *, description: str = "") -> Any:
        return await self._client.create_supergroup(title, description=description)

    async def create_channel(self, title: str, *, description: str = "") -> Any:
        return await self._client.create_channel(title, description=description)

    async def set_chat_username(self, chat_id: int | str, username: str | None) -> bool:
        return await self._client.set_chat_username(chat_id, username)

    async def ban_chat_member(self, chat_id: int | str, user_id: int) -> Any:
        return await self._client.ban_chat_member(chat_id, user_id)

    async def unban_chat_member(self, chat_id: int | str, user_id: int) -> Any:
        return await self._client.unban_chat_member(chat_id, user_id)

    def _coerce_chat_permissions(self, permissions: pyrogram_types.ChatPermissions | dict[str, bool] | None) -> pyrogram_types.ChatPermissions:
        if isinstance(permissions, pyrogram_types.ChatPermissions):
            return permissions
        if permissions is None:
            return pyrogram_types.ChatPermissions()
        allowed_keys = {
            "can_send_messages",
            "can_send_media_messages",
            "can_send_other_messages",
            "can_send_polls",
            "can_add_web_page_previews",
            "can_change_info",
            "can_invite_users",
            "can_pin_messages",
        }
        payload = {key: bool(value) for key, value in permissions.items() if key in allowed_keys}
        return pyrogram_types.ChatPermissions(**payload)

    def _full_chat_permissions(self) -> pyrogram_types.ChatPermissions:
        return pyrogram_types.ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_send_polls=True,
            can_add_web_page_previews=True,
            can_change_info=True,
            can_invite_users=True,
            can_pin_messages=True,
        )

    async def set_chat_permissions(
        self,
        chat_id: int | str,
        permissions: pyrogram_types.ChatPermissions | dict[str, bool] | None,
    ) -> Any:
        return await self._client.set_chat_permissions(chat_id, self._coerce_chat_permissions(permissions))

    async def restrict_chat_member(
        self,
        chat_id: int | str,
        user_id: int,
        permissions: pyrogram_types.ChatPermissions | dict[str, bool] | None,
    ) -> Any:
        return await self._client.restrict_chat_member(chat_id, user_id, self._coerce_chat_permissions(permissions))

    async def unrestrict_chat_member(self, chat_id: int | str, user_id: int) -> Any:
        return await self._client.restrict_chat_member(chat_id, user_id, self._full_chat_permissions())

    def _coerce_chat_privileges(self, privileges: pyrogram_types.ChatPrivileges | dict[str, bool] | None) -> pyrogram_types.ChatPrivileges:
        if isinstance(privileges, pyrogram_types.ChatPrivileges):
            return privileges
        if privileges is None:
            return pyrogram_types.ChatPrivileges()
        allowed_keys = {
            "can_manage_chat",
            "can_delete_messages",
            "can_manage_video_chats",
            "can_restrict_members",
            "can_promote_members",
            "can_change_info",
            "can_post_messages",
            "can_edit_messages",
            "can_invite_users",
            "can_pin_messages",
            "is_anonymous",
        }
        payload = {key: bool(value) for key, value in privileges.items() if key in allowed_keys}
        return pyrogram_types.ChatPrivileges(**payload)

    def _empty_chat_privileges(self) -> pyrogram_types.ChatPrivileges:
        return pyrogram_types.ChatPrivileges(
            can_manage_chat=False,
            can_delete_messages=False,
            can_manage_video_chats=False,
            can_restrict_members=False,
            can_promote_members=False,
            can_change_info=False,
            can_post_messages=False,
            can_edit_messages=False,
            can_invite_users=False,
            can_pin_messages=False,
            is_anonymous=False,
        )

    async def promote_chat_member(
        self,
        chat_id: int | str,
        user_id: int,
        privileges: pyrogram_types.ChatPrivileges | dict[str, bool] | None,
    ) -> Any:
        return await self._client.promote_chat_member(chat_id, user_id, self._coerce_chat_privileges(privileges))

    async def demote_chat_member(self, chat_id: int | str, user_id: int) -> Any:
        return await self._client.promote_chat_member(chat_id, user_id, self._empty_chat_privileges())

    async def set_administrator_title(self, chat_id: int | str, user_id: int, title: str) -> Any:
        return await self._client.set_administrator_title(chat_id, user_id, title)

    async def set_chat_title(self, chat_id: int | str, title: str) -> Any:
        return await self._client.set_chat_title(chat_id, title)

    async def set_chat_photo(
        self,
        chat_id: int | str,
        *,
        photo: str | None = None,
        video: str | None = None,
        video_start_ts: float | None = None,
    ) -> Any:
        return await self._client.set_chat_photo(
            chat_id,
            photo=photo,
            video=video,
            video_start_ts=video_start_ts,
        )

    async def delete_chat_photo(self, chat_id: int | str) -> Any:
        return await self._client.delete_chat_photo(chat_id)

    async def update_contact(self, user_id: int, *, first_name: str, last_name: str = "") -> Any:
        """Update a contact's name in the personal address book."""
        from pyrogram import raw
        peer = await self._client.resolve_peer(user_id)
        return await self._client.invoke(
            raw.functions.contacts.AddContact(
                id=peer,
                first_name=first_name,
                last_name=last_name,
                phone="",
                add_phone_privacy_exception=False,
            )
        )

    async def delete_contact(self, user_id: int) -> Any:
        """Remove a user from the personal address book."""
        from pyrogram import raw
        peer = await self._client.resolve_peer(user_id)
        return await self._client.invoke(
            raw.functions.contacts.DeleteContacts(id=[peer])
        )

    async def search_own_messages(
        self,
        query: str,
        *,
        chat_id: int | str | None = None,
        limit: int = 20,
        owner_user_id: int | None = None,
    ) -> list[dict]:
        """Search through owner's sent messages. Returns list of {chat, text, date, link}."""
        results: list[dict] = []
        try:
            if chat_id is not None:
                # Search in specific chat
                async for msg in self._client.search_messages(
                    chat_id=chat_id,
                    query=query,
                    filter=enums.MessagesFilter.EMPTY,
                    limit=limit,
                ):
                    if not msg.outgoing:
                        continue
                    results.append(self._format_search_hit(msg))
                    if len(results) >= limit:
                        break
            else:
                # Search globally across all chats
                async for msg in self._client.search_global(
                    query=query,
                    filter=enums.MessagesFilter.EMPTY,
                    limit=limit * 3,
                ):
                    if not msg.outgoing:
                        continue
                    results.append(self._format_search_hit(msg))
                    if len(results) >= limit:
                        break
        except Exception:
            pass
        return results

    def _format_search_hit(self, msg) -> dict:
        chat = getattr(msg, "chat", None)
        chat_id = getattr(chat, "id", None)
        chat_title = getattr(chat, "title", None) or getattr(chat, "first_name", None) or str(chat_id)
        chat_username = getattr(chat, "username", None)
        text = (msg.text or msg.caption or "").strip()
        date = getattr(msg, "date", None)
        date_str = date.strftime("%d.%m.%Y %H:%M") if date else ""
        link = f"https://t.me/{chat_username}/{msg.id}" if chat_username else f"tg://openmessage?chat_id={abs(chat_id or 0)}&message_id={msg.id}"
        return {
            "chat_title": chat_title,
            "chat_id": chat_id,
            "text": text[:300],
            "date": date_str,
            "link": link,
        }

    async def set_chat_description(self, chat_id: int | str, description: str) -> Any:
        return await self._client.set_chat_description(chat_id, description)

    async def find_best_chat_with_user(self, user_id: int) -> int | None:
        """Find the most recent active chat with a user. Returns chat_id or None."""
        import logging
        _log = logging.getLogger("assistant.tg_actions")

        # 1. Try private chat
        try:
            chat = await self._client.get_chat(user_id)
            if chat:
                return user_id
        except Exception as e:
            _log.debug("find_best_chat private failed user_id=%s err=%s", user_id, e)

        # 2. Try get_common_chats
        try:
            common = await self._client.get_common_chats(user_id)
            if common:
                _log.debug("find_best_chat common found user_id=%s chat_id=%s", user_id, common[0].id)
                return common[0].id
        except Exception as e:
            _log.debug("find_best_chat common_chats failed user_id=%s err=%s", user_id, e)

        # 3. Scan dialogs for recent message from this user
        try:
            async for dialog in self._client.get_dialogs(limit=50):
                chat = getattr(dialog, "chat", None)
                if chat is None:
                    continue
                chat_type = str(getattr(chat, "type", "")).lower()
                if "group" in chat_type or "supergroup" in chat_type:
                    # Check if user is in this group
                    top_msg = getattr(dialog, "top_message", None)
                    if top_msg:
                        sender = getattr(top_msg, "from_user", None)
                        if getattr(sender, "id", None) == user_id:
                            _log.debug("find_best_chat dialog scan found user_id=%s chat_id=%s", user_id, chat.id)
                            return chat.id
        except Exception as e:
            _log.debug("find_best_chat dialog scan failed user_id=%s err=%s", user_id, e)

        return None

    async def get_recent_chat_context(
        self,
        chat_id: int | str,
        *,
        limit: int = 20,
    ) -> list[dict]:
        """Get recent messages from chat as list of {text, outgoing, name, date}."""
        import logging
        _log = logging.getLogger("assistant.tg_actions")
        messages = []
        try:
            async for msg in self._client.get_chat_history(chat_id, limit=limit * 2):
                text = (msg.text or msg.caption or "").strip()
                if not text:
                    continue
                sender = getattr(msg, "from_user", None)
                name = getattr(sender, "first_name", None) or ("Ð¯" if msg.outgoing else "?")
                date = getattr(msg, "date", None)
                messages.append({
                    "text": text[:300],
                    "outgoing": msg.outgoing,
                    "name": name,
                    "date": date.strftime("%H:%M") if date else "",
                })
                if len(messages) >= limit:
                    break
        except Exception as e:
            _log.warning("get_recent_chat_context failed chat_id=%s err=%s", chat_id, e)
        _log.debug("get_recent_chat_context chat_id=%s found=%d", chat_id, len(messages))
        return list(reversed(messages))

    async def get_message_text(self, chat_id: int | str, message_id: int) -> str:
        message = await self._client.get_messages(chat_id, message_id)
        return (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()

    async def get_message(self, chat_id: int | str, message_id: int) -> Any:
        return await self._client.get_messages(chat_id, message_id)

    async def get_message_image_base64(self, message) -> tuple[str, str] | None:
        import base64

        photo = getattr(message, "photo", None)
        document = getattr(message, "document", None)
        sticker = getattr(message, "sticker", None)
        if photo is None and document is None and sticker is None:
            return None
        if document is not None:
            mime = getattr(document, "mime_type", "") or ""
            if not mime.startswith("image/"):
                return None
        try:
            media = await self._client.download_media(message, in_memory=True)
            if media is None:
                return None
            raw = bytes(media.getvalue()) if hasattr(media, "getvalue") else bytes(media)
            if not raw:
                return None
            mime_type = getattr(document, "mime_type", None) if document is not None else None
            payload = base64.b64encode(raw).decode("utf-8")
            return payload, (mime_type or "image/jpeg")
        except Exception:
            return None

    async def get_message_audio_bytes(self, message) -> tuple[bytes, str] | None:
        voice = getattr(message, "voice", None)
        audio = getattr(message, "audio", None)
        video_note = getattr(message, "video_note", None)
        if voice is None and audio is None and video_note is None:
            return None
        try:
            media = await self._client.download_media(message, in_memory=True)
            if media is None:
                return None
            raw = bytes(media.getvalue()) if hasattr(media, "getvalue") else bytes(media)
            if not raw:
                return None
            if voice is not None or video_note is not None:
                filename = "voice.ogg"
            else:
                filename = getattr(audio, "file_name", None) or "audio.mp3"
            return raw, filename
        except Exception:
            return None

    async def collect_recent_sticker_candidates(
        self,
        *,
        dialog_limit: int = 40,
        per_chat_limit: int = 30,
        max_candidates: int = 80,
    ) -> list[dict[str, Any]]:
        if self._is_sticker_cache_fresh(self._recent_sticker_cache, STICKER_DIALOG_CACHE_TTL_SECONDS):
            return list(self._recent_sticker_cache[1])
        candidates: list[dict[str, Any]] = []
        seen_unique_ids: set[str] = set()
        async for dialog in self._client.get_dialogs(limit=max(1, dialog_limit)):
            chat = getattr(dialog, "chat", None)
            chat_id = getattr(chat, "id", None)
            if chat is None or chat_id is None:
                continue
            async for message in self._client.get_chat_history(chat_id, limit=max(1, per_chat_limit)):
                sticker = getattr(message, "sticker", None)
                if sticker is None:
                    continue
                file_id = getattr(sticker, "file_id", None)
                unique_id = getattr(sticker, "file_unique_id", None) or file_id
                if not file_id or not unique_id or unique_id in seen_unique_ids:
                    continue
                seen_unique_ids.add(unique_id)
                candidates.append(
                    {
                        "file_id": file_id,
                        "file_unique_id": unique_id,
                        "emoji": (getattr(sticker, "emoji", None) or "").strip(),
                        "set_name": (getattr(sticker, "set_name", None) or "").strip(),
                        "is_animated": bool(getattr(sticker, "is_animated", False)),
                        "is_video": bool(getattr(sticker, "is_video", False)),
                        "chat_id": chat_id,
                        "message_id": getattr(message, "id", None),
                        "chat_label": getattr(chat, "title", None)
                        or getattr(chat, "first_name", None)
                        or str(chat_id),
                        "date": getattr(message, "date", None),
                        "source": "dialog_history",
                        "source_index": len(candidates),
                    }
                )
                if len(candidates) >= max_candidates:
                    self._recent_sticker_cache = (time.monotonic(), list(candidates))
                    return list(candidates)
        self._recent_sticker_cache = (time.monotonic(), list(candidates))
        return list(candidates)

    async def collect_account_sticker_candidates(
        self,
        *,
        max_candidates: int = 100,
    ) -> list[dict[str, Any]]:
        if self._is_sticker_cache_fresh(self._account_sticker_cache, STICKER_ACCOUNT_CACHE_TTL_SECONDS):
            return list(self._account_sticker_cache[1])

        candidates: list[dict[str, Any]] = []
        seen_unique_ids: set[str] = set()

        try:
            response = await self._client.invoke(raw.functions.messages.GetFavedStickers(hash=0))
            for index, document in enumerate(getattr(response, "stickers", []) or []):
                candidate = self._raw_sticker_document_to_candidate(
                    document,
                    source="favorites",
                    source_index=index,
                )
                if candidate is None:
                    continue
                unique_id = str(candidate.get("file_unique_id") or candidate.get("file_id") or "")
                if not unique_id or unique_id in seen_unique_ids:
                    continue
                seen_unique_ids.add(unique_id)
                candidates.append(candidate)
                if len(candidates) >= max_candidates:
                    break
        except Exception:
            pass

        if len(candidates) < max_candidates:
            try:
                response = await self._client.invoke(
                    raw.functions.messages.GetRecentStickers(hash=0, attached=False)
                )
                recent_dates = list(getattr(response, "dates", []) or [])
                for index, document in enumerate(getattr(response, "stickers", []) or []):
                    candidate = self._raw_sticker_document_to_candidate(
                        document,
                        source="recent",
                        source_index=index,
                        date=recent_dates[index] if index < len(recent_dates) else None,
                    )
                    if candidate is None:
                        continue
                    unique_id = str(candidate.get("file_unique_id") or candidate.get("file_id") or "")
                    if not unique_id or unique_id in seen_unique_ids:
                        continue
                    seen_unique_ids.add(unique_id)
                    candidates.append(candidate)
                    if len(candidates) >= max_candidates:
                        break
            except Exception:
                pass

        self._account_sticker_cache = (time.monotonic(), list(candidates))
        return list(candidates)

    async def collect_telegram_emoji_sticker_candidates(
        self,
        desired_emojis: set[str],
        *,
        per_emoji_limit: int = 30,
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen_unique_ids: set[str] = set()

        for emoji in sorted(desired_emojis):
            cache_entry = self._emoji_sticker_cache.get(emoji)
            if self._is_sticker_cache_fresh(cache_entry, STICKER_EMOJI_CACHE_TTL_SECONDS):
                emoji_candidates = list(cache_entry[1])
            else:
                emoji_candidates: list[dict[str, Any]] = []
                try:
                    response = await self._client.invoke(
                        raw.functions.messages.GetStickers(emoticon=emoji, hash=0)
                    )
                    for index, document in enumerate(getattr(response, "stickers", []) or []):
                        if index >= per_emoji_limit:
                            break
                        candidate = self._raw_sticker_document_to_candidate(
                            document,
                            source="telegram_emoji",
                            source_index=index,
                        )
                        if candidate is None:
                            continue
                        candidate["requested_emoji"] = emoji
                        emoji_candidates.append(candidate)
                except Exception:
                    emoji_candidates = []
                self._emoji_sticker_cache[emoji] = (time.monotonic(), list(emoji_candidates))

            for candidate in emoji_candidates:
                unique_id = str(candidate.get("file_unique_id") or candidate.get("file_id") or "")
                if not unique_id or unique_id in seen_unique_ids:
                    continue
                seen_unique_ids.add(unique_id)
                merged.append(candidate)

        return merged

    async def find_sticker_candidate(self, query: str) -> dict[str, Any] | None:
        profile = self._build_sticker_query_profile(query)
        account_candidates = await self.collect_account_sticker_candidates()
        emoji_candidates = (
            await self.collect_telegram_emoji_sticker_candidates(profile.desired_emojis)
            if profile.desired_emojis
            else []
        )
        recent_candidates = await self.collect_recent_sticker_candidates()
        candidates = self._merge_sticker_candidates(
            account_candidates,
            emoji_candidates,
            recent_candidates,
        )
        if not candidates:
            return None
        if not profile.normalized_query:
            return candidates[0]

        exact_matches = self._filter_candidates_by_emoji(candidates, profile.exact_emojis)
        if exact_matches:
            return self._pick_best_sticker_candidate(exact_matches, profile)
        if profile.exact_emojis:
            return None

        desired_matches = self._filter_candidates_by_emoji(candidates, profile.desired_emojis)
        if desired_matches:
            return self._pick_best_sticker_candidate(desired_matches, profile)
        if profile.desired_emojis and not profile.allow_loose:
            return None

        best_candidate = self._pick_best_sticker_candidate(candidates, profile)
        if best_candidate is None:
            return None
        if profile.query_tokens and not profile.allow_loose:
            set_name = str(best_candidate.get("set_name") or "").casefold()
            if not any(token in set_name for token in profile.query_tokens):
                return None
        if profile.wants_generic_any:
            return best_candidate
        if profile.desired_emojis:
            return None
        return best_candidate

    async def send_sticker_by_query(
        self,
        chat_lookup: str | int,
        query: str,
        *,
        reply_to_message_id: int | None = None,
    ) -> tuple[Any, dict[str, Any]] | tuple[None, None]:
        candidate = await self.find_sticker_candidate(query)
        if candidate is None:
            return None, None
        sent = await self.send_sticker(
            chat_lookup,
            str(candidate["file_id"]),
            reply_to_message_id=reply_to_message_id,
        )
        return sent, candidate

    async def clear_history(
        self,
        chat_id: int | str,
        *,
        limit: int = 30,
        exclude_message_ids: set[int] | None = None,
        filter_user_id: int | None = None,
    ) -> int:
        delete_ids: list[int] = []
        excluded = exclude_message_ids or set()
        scan_limit = max(limit, 50) if filter_user_id else limit
        async for message in self._client.get_chat_history(chat_id, limit=max(1, min(scan_limit, 200))):
            if getattr(message, "id", None) in excluded:
                continue
            if filter_user_id is not None:
                msg_from = getattr(message, "from_user", None)
                msg_user_id = getattr(msg_from, "id", None)
                if msg_user_id != filter_user_id:
                    continue
            delete_ids.append(message.id)
            if len(delete_ids) >= limit:
                break
        if not delete_ids:
            return 0
        await self._client.delete_messages(chat_id, delete_ids)
        return len(delete_ids)

    async def delete_dialog(self, chat_id: int | str) -> dict[str, Any]:
        peer = await self._client.resolve_peer(chat_id)
        if isinstance(peer, raw.types.InputPeerChannel):
            await self._client.leave_chat(chat_id)
            return {"mode": "leave_channel"}
        if isinstance(peer, raw.types.InputPeerChat):
            await self._client.leave_chat(chat_id, delete=True)
            return {"mode": "leave_chat_delete"}
        await self._client.invoke(
            raw.functions.messages.DeleteHistory(
                peer=peer,
                max_id=0,
                revoke=False,
            )
        )
        return {"mode": "delete_history"}

    async def safe_chat_display(self, reference: str | int) -> str:
        try:
            resolved = await self.resolve_chat(reference)
        except Exception:
            return str(reference)
        return resolved.label

    def _desired_sticker_emojis(self, normalized_query: str) -> set[str]:
        desired: set[str] = set()
        for candidate in self._extract_emoji_like_fragments(normalized_query):
            desired.add(candidate)
        for token in STICKER_QUERY_TOKEN_RE.findall(normalized_query):
            if token in STICKER_GENERIC_QUERY_TOKENS:
                continue
            mapped = STICKER_EMOJI_ALIASES.get(token)
            if mapped:
                desired.update(mapped)
                continue
            for alias, emojis in STICKER_EMOJI_ALIASES.items():
                if alias in token:
                    desired.update(emojis)
        return desired

    def _build_sticker_query_profile(self, query: str) -> StickerQueryProfile:
        normalized = " ".join((query or "").strip().casefold().split())
        query_tokens = [
            token
            for token in STICKER_QUERY_TOKEN_RE.findall(normalized)
            if token not in STICKER_GENERIC_QUERY_TOKENS
        ]
        exact_emojis = self._extract_emoji_like_fragments(query or "")
        desired_emojis = self._desired_sticker_emojis(normalized)
        allow_loose = any(marker in normalized for marker in STICKER_LOOSE_QUERY_MARKERS)
        wants_generic_any = allow_loose and not query_tokens and not desired_emojis
        return StickerQueryProfile(
            normalized_query=normalized,
            query_tokens=query_tokens,
            exact_emojis=exact_emojis,
            desired_emojis=desired_emojis,
            allow_loose=allow_loose,
            wants_generic_any=wants_generic_any,
        )

    def _filter_candidates_by_emoji(
        self,
        candidates: list[dict[str, Any]],
        emojis: set[str],
    ) -> list[dict[str, Any]]:
        if not emojis:
            return []
        return [
            candidate
            for candidate in candidates
            if str(candidate.get("emoji") or "").strip() in emojis
        ]

    def _pick_best_sticker_candidate(
        self,
        candidates: list[dict[str, Any]],
        profile: StickerQueryProfile,
    ) -> dict[str, Any] | None:
        best_candidate: dict[str, Any] | None = None
        best_score = -1
        for candidate in candidates:
            score = self._score_sticker_candidate(candidate, profile)
            if score > best_score:
                best_score = score
                best_candidate = candidate
        if best_score <= 0:
            return None
        return best_candidate

    def _score_sticker_candidate(
        self,
        candidate: dict[str, Any],
        profile: StickerQueryProfile,
    ) -> int:
        emoji = str(candidate.get("emoji") or "").strip()
        set_name = str(candidate.get("set_name") or "").casefold()
        source = str(candidate.get("source") or "")
        source_index = int(candidate.get("source_index") or 0)

        score = STICKER_SOURCE_WEIGHTS.get(source, 0)
        if emoji and emoji in profile.exact_emojis:
            score += 240
        elif emoji and emoji in profile.desired_emojis:
            score += 170
        if set_name and profile.query_tokens:
            score += sum(30 for token in profile.query_tokens if token in set_name)
        if profile.allow_loose and emoji:
            score += 5
        score += max(0, 10 - min(source_index, 10))
        return score

    def _merge_sticker_candidates(
        self,
        *candidate_groups: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for group in candidate_groups:
            for candidate in group:
                unique_id = str(candidate.get("file_unique_id") or candidate.get("file_id") or "")
                if not unique_id:
                    continue
                existing = merged.get(unique_id)
                if existing is None:
                    merged[unique_id] = dict(candidate)
                    continue
                current_weight = STICKER_SOURCE_WEIGHTS.get(str(candidate.get("source") or ""), 0)
                existing_weight = STICKER_SOURCE_WEIGHTS.get(str(existing.get("source") or ""), 0)
                if current_weight > existing_weight:
                    merged[unique_id] = dict(candidate)
        return list(merged.values())

    def _raw_sticker_document_to_candidate(
        self,
        document: Any,
        *,
        source: str,
        source_index: int,
        date: Any = None,
    ) -> dict[str, Any] | None:
        media_id = getattr(document, "id", None)
        access_hash = getattr(document, "access_hash", None)
        dc_id = getattr(document, "dc_id", None)
        if media_id is None or access_hash is None or dc_id is None:
            return None

        emoji = ""
        set_name = ""
        for attribute in getattr(document, "attributes", []) or []:
            if isinstance(attribute, raw.types.DocumentAttributeSticker):
                emoji = (getattr(attribute, "alt", None) or "").strip()
                sticker_set = getattr(attribute, "stickerset", None)
                if isinstance(sticker_set, raw.types.InputStickerSetShortName):
                    set_name = (getattr(sticker_set, "short_name", None) or "").strip()
                break

        try:
            file_id = FileId(
                file_type=FileType.STICKER,
                dc_id=dc_id,
                media_id=media_id,
                access_hash=access_hash,
                file_reference=getattr(document, "file_reference", b"") or b"",
            ).encode()
        except Exception:
            return None

        return {
            "file_id": file_id,
            "file_unique_id": str(media_id),
            "emoji": emoji,
            "set_name": set_name,
            "is_animated": getattr(document, "mime_type", "") == "application/x-tgsticker",
            "is_video": getattr(document, "mime_type", "") == "video/webm",
            "date": date if date is not None else getattr(document, "date", None),
            "source": source,
            "source_index": source_index,
        }

    def _is_sticker_cache_fresh(
        self,
        cache_entry: tuple[float, list[dict[str, Any]]] | None,
        ttl_seconds: float,
    ) -> bool:
        if cache_entry is None:
            return False
        return (time.monotonic() - cache_entry[0]) < ttl_seconds

    def _extract_emoji_like_fragments(self, text: str) -> set[str]:
        fragments: set[str] = set()
        current = ""
        for char in text or "":
            if ord(char) >= 0x2600 and not char.isalnum():
                current += char
                continue
            if current:
                fragments.add(current)
                current = ""
        if current:
            fragments.add(current)
        return fragments

    async def _try_get_chat(self, reference: str):
        try:
            return await self._client.get_chat(reference)
        except Exception:
            return None

    async def _collect_dialogs(self, *, limit: int) -> list[ResolvedReference]:
        results: list[ResolvedReference] = []
        async for dialog in self._client.get_dialogs(limit=limit):
            chat = getattr(dialog, "chat", None)
            if chat is None:
                continue
            results.append(self._chat_to_reference(chat, lookup=getattr(chat, "id", None)))
        return results

    def _dialog_matches_exact(self, dialog: ResolvedReference, normalized: str) -> bool:
        tokens = {dialog.label.casefold()}
        if dialog.username:
            tokens.add(dialog.username.casefold())
            tokens.add(f"@{dialog.username.casefold()}")
        return normalized in tokens

    def _dialog_matches_partial(self, dialog: ResolvedReference, normalized: str) -> bool:
        if normalized in dialog.label.casefold():
            return True
        if dialog.username and normalized in dialog.username.casefold():
            return True
        return False

    def _chat_to_reference(self, chat: Any, *, lookup: str | int, label_override: str | None = None) -> ResolvedReference:
        chat_type = getattr(chat, "type", None)
        title = getattr(chat, "title", None)
        username = getattr(chat, "username", None)
        first_name = getattr(chat, "first_name", None)
        last_name = getattr(chat, "last_name", None)
        display = label_override or title or " ".join(part for part in [first_name, last_name] if part) or f"chat_id {getattr(chat, 'id', lookup)}"
        kind = "user" if chat_type == enums.ChatType.PRIVATE else "chat"
        return ResolvedReference(
            kind=kind,
            lookup=lookup,
            label=display,
            chat_id=getattr(chat, "id", None),
            user_id=getattr(chat, "id", None) if kind == "user" else None,
            username=username,
        )

    def _user_to_reference(self, user: Any, *, lookup: str | int) -> ResolvedReference:
        display = " ".join(part for part in [getattr(user, "first_name", None), getattr(user, "last_name", None)] if part).strip()
        if not display:
            display = f"@{user.username}" if getattr(user, "username", None) else f"user_id {user.id}"
        return ResolvedReference(
            kind="user",
            lookup=lookup,
            label=display,
            chat_id=getattr(user, "id", None),
            user_id=getattr(user, "id", None),
            username=getattr(user, "username", None),
        )

