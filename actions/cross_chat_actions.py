from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from dataclasses import dataclass, replace
from typing import Any

from infra.telegram_compat import prepare_pyrogram_runtime

prepare_pyrogram_runtime()

from pyrogram import Client, enums

from chat.chat_config import ChatConfigStore
from config.settings import AppConfig
from chat.context_reader import ContextReader
from ai.groq_client import GroqClient
from infra.language_tools import detect_language, tr
from .tg_actions import TelegramActionService
from ai.validator import TRIGGER_PREFIX_RE, sanitize_ai_output, strip_ai_prefix


PUBLIC_LINK_RE = re.compile(
    r"^(?:https?://)?(?:t\.me|telegram\.me)/(?P<path>.+)$", re.IGNORECASE
)
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
CHAT_REFERENCE_RE = re.compile(
    r"(?:https?://(?:t\.me|telegram\.me)/\S+|@[A-Za-z][A-Za-z0-9_]{4,31}|-?\d{6,}|(?<!\w)me(?!\w)|Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½(?:Ð¾Ðµ|Ð¾Ð³Ð¾|Ð¾Ð¼)|saved(?:\s+messages)?)",
    re.IGNORECASE,
)
HOURS_RE = re.compile(r"(\d{1,3})\s*(?:h|hour|hours|Ñ‡|Ñ‡Ð°Ñ|Ñ‡Ð°ÑÐ°|Ñ‡Ð°ÑÐ¾Ð²)", re.IGNORECASE)
MESSAGES_RE = re.compile(
    r"(\d{1,4})\s*(?:msg|msgs|messages|message|ÑÐ¾Ð¾|ÑÐ¾Ð¾Ð±Ñ‰(?:\.|ÐµÐ½Ð¸Ðµ|ÐµÐ½Ð¸Ñ|ÐµÐ½Ð¸Ð¹|ÐµÐ½Ð¸ÑÐ¼|ÐµÐ½Ð¸ÑÑ…)?)",
    re.IGNORECASE,
)

SUMMARIZE_KEYWORDS = ("summary", "summar", "ÑÑƒÐ¼Ð¼", "ÐºÑ€Ð°Ñ‚ÐºÐ¾", "Ð¸Ñ‚Ð¾Ð³", "Ð¾ Ñ‡ÐµÐ¼")
FIND_KEYWORDS = ("find", "search", "Ð½Ð°Ð¹Ð´", "Ð¿Ð¾Ð¸ÑÐº")
EXTRACT_KEYWORDS = ("extract", "Ð¸Ð·Ð²Ð»ÐµÐº", "Ð²Ñ‹Ñ‚Ð°Ñ‰", "Ð´Ð¾ÑÑ‚Ð°Ð½")
REWRITE_KEYWORDS = ("rewrite", "Ð¿ÐµÑ€ÐµÐ¿Ð¸Ñˆ", "Ð¿ÐµÑ€ÐµÑ„Ð¾Ñ€Ð¼ÑƒÐ»", "Ð¾Ñ‚Ñ€ÐµÐ´Ð°ÐºÑ‚")
DOCUMENT_KEYWORDS = (
    "documentation",
    "document",
    "info about",
    "information about",
    "profile of",
    "profile",
    "Ð´Ð¾ÐºÑƒÐ¼ÐµÐ½Ñ‚",
    "Ð¸Ð½Ñ„Ð¾",
    "Ð¸Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†",
    "Ð¾Ð¿Ð¸ÑÐ°Ð½",
    "Ð¾ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»",
)
SEND_KEYWORDS = ("send", "Ð¾Ñ‚Ð¿Ñ€Ð°Ð²", "Ð¿ÐµÑ€ÐµÑˆÐ»Ð¸", "ÑÐºÐ¸Ð½ÑŒ", "ÑÐºÐ¸Ð½ÑƒÐ»", "Ð·Ð°ÐºÐ¸Ð½ÑŒ")
WRITE_KEYWORDS = ("write", "Ð½Ð°Ð¿Ð¸ÑˆÐ¸", "Ð½Ð°Ð¿Ð¸ÑˆÐ¸-ÐºÐ°", "ÑÐºÐ°Ð¶Ð¸")
DIRECT_SEND_TEXT_MARKERS = (
    "Ñ„Ñ€Ð°Ð·",
    "Ñ‚ÐµÐºÑÑ‚",
    "ÑÐ¾Ð¾",
    "ÑÐ¾Ð¾Ð±Ñ‰",
    "phrase",
    "text",
    "message",
)
SAVE_KEYWORDS = (
    "save",
    "saved messages",
    "ÑÐ¾Ñ…Ñ€Ð°Ð½",
    "Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½Ð¾Ðµ",
    "Ð¼Ð¾Ðµ Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½Ð¾Ðµ",
    "Ð¼Ð¾Ñ‘ Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½Ð¾Ðµ",
    "Ð² Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½Ð¾Ðµ",
    "Ð² ÑÐ¾Ñ…Ñ€Ð°Ð½",
)
CHANNEL_LINK_KEYWORDS = (
    "channel link",
    "link to channel",
    "telegram channel",
    "tg channel",
    "tgk",
    "Ñ‚Ð³Ðº",
    "Ñ‚Ð³ ÐºÐ°Ð½Ð°Ð»",
    "ÐºÐ°Ð½Ð°Ð»",
    "ÑÑÑ‹Ð»Ðº",
    "t.me",
)
FORWARD_LAST_KEYWORDS = (
    "forward last",
    "send last",
    "latest message",
    "last message",
    "latest messages",
    "last messages",
    "Ð¿ÐµÑ€ÐµÐºÐ¸Ð½ÑŒ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½ÐµÐµ",
    "Ð¿ÐµÑ€ÐµÐºÐ¸Ð½ÑŒ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ðµ",
    "Ð¿ÐµÑ€ÐµÑˆÐ»Ð¸ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½ÐµÐµ",
    "Ð¿ÐµÑ€ÐµÑˆÐ»Ð¸ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ðµ",
    "Ð¾Ñ‚Ð¿Ñ€Ð°Ð²ÑŒ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½ÐµÐµ",
    "Ð¾Ñ‚Ð¿Ñ€Ð°Ð²ÑŒ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ðµ",
    "ÑÐºÐ¸Ð½ÑŒ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ðµ",
    "Ð¿Ð¾ÑÐ»ÐµÐ´Ð½ÐµÐµ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ",
    "Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ðµ ÑÐ¾Ð¾",
    "Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ðµ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ",
)
FAVORITES_ALIASES = {
    "me",
    "saved",
    "saved messages",
    "saved_messages",
    "Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½Ð¾Ðµ",
    "ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð½Ñ‹Ðµ",
    "ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½ÐºÐ¸",
}
CHAT_ACTION_HINTS = (
    "Ñ‡Ð°Ñ‚",
    "ÐºÐ°Ð½Ð°Ð»",
    "Ð¿ÐµÑ€ÐµÐ¿Ð¸Ñ",
    "ÑÐ¾Ð¾Ð±Ñ‰",
    "Ð¸ÑÑ‚Ð¾Ñ€",
    "Ð¾Ð±ÑÑƒÐ¶Ð´",
    "Ð´Ð¸Ð°Ð»Ð¾Ð³",
    "Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½",
    "saved",
    "history",
    "messages",
    "chat",
)
MEDIA_TYPE_MARKERS = {
    "photo": (
        "photo",
        "photos",
        "image",
        "images",
        "picture",
        "pictures",
        "\u0444\u043e\u0442\u043e",
        "\u0444\u043e\u0442\u043a",
        "\u043a\u0430\u0440\u0442\u0438\u043d",
        "\u0438\u0437\u043e\u0431\u0440\u0430\u0436",
    ),
    "voice": (
        "voice",
        "voice message",
        "voice note",
        "audio",
        "\u0433\u043e\u043b\u043e\u0441\u043e\u0432",
        "\u0430\u0443\u0434\u0438\u043e",
        "\u043a\u0440\u0443\u0436\u043e\u043a",
    ),
    "sticker": (
        "sticker",
        "stickers",
        "\u0441\u0442\u0438\u043a\u0435\u0440",
        "\u0441\u0442\u0438\u043a\u0435\u0440\u044b",
    ),
    "text": (
        "message",
        "messages",
        "text",
        "\u0441\u043e\u043e\u0431\u0449\u0435\u043d",
        "\u0442\u0435\u043a\u0441\u0442",
    ),
}
PHOTO_OR_VOICE_MARKERS = (
    "photo or voice",
    "voice or photo",
    "\u0444\u043e\u0442\u043e \u0438\u043b\u0438 \u0433\u043e\u043b\u043e\u0441\u043e\u0432",
    "\u0433\u043e\u043b\u043e\u0441\u043e\u0432 \u0438\u043b\u0438 \u0444\u043e\u0442\u043e",
)
TODAY_MARKERS = ("today", "\u0441\u0435\u0433\u043e\u0434\u043d\u044f")
ALL_MARKERS = ("all", "\u0432\u0441\u0435", "\u0432\u0441\u0451")
AROUND_TIME_MARKERS = ("around", "about", "near", "\u043e\u043a\u043e\u043b\u043e", "\u043f\u0440\u0438\u043c\u0435\u0440\u043d\u043e")
CLOCK_TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
SEMANTIC_LINK_MARKERS = (
    "where",
    "about",
    "with",
    "\u0433\u0434\u0435",
    "\u043f\u0440\u043e",
    "\u043e\u0431",
    "\u0441",
    "\u043f\u043e \u0441\u043c\u044b\u0441\u043b\u0443",
)
QUERY_TOKEN_RE = re.compile(r"[a-z0-9\u0400-\u04ff]{2,}", re.IGNORECASE)
WEAK_QUERY_MARKERS = {
    "this",
    "that",
    "it",
    "here",
    "\u044d\u0442\u043e",
    "\u0442\u0430\u043c",
    "\u0442\u0443\u0442",
    "\u043e\u0431 \u044d\u0442\u043e\u043c",
    "\u043f\u0440\u043e \u044d\u0442\u043e",
}
STICKER_QUERY_MARKERS = (
    "emoji",
    "emoticon",
    "similar sticker",
    "matching sticker",
    "\u044d\u043c\u043e\u0434\u0437\u0438",
    "\u0441\u043c\u0430\u0439\u043b",
    "\u043f\u043e\u0445\u043e\u0436\u0438\u0439 \u0441\u0442\u0438\u043a\u0435\u0440",
    "\u0441\u0442\u0438\u043a\u0435\u0440 \u0441",
)
REPLY_SEMANTIC_REFERENCE_MARKERS = (
    "about this",
    "about that",
    "about it",
    "with this",
    "with that",
    "with it",
    "where this",
    "where that",
    "where it",
    "this was discussed",
    "that was discussed",
    "it was discussed",
    "this one",
    "that one",
    "like this",
    "like that",
    "\u043f\u0440\u043e \u044d\u0442\u043e",
    "\u043e\u0431 \u044d\u0442\u043e\u043c",
    "\u0433\u0434\u0435 \u044d\u0442\u043e",
    "\u044d\u0442\u043e \u043e\u0431\u0441\u0443\u0436\u0434\u0430\u043b\u0438",
    "\u0433\u0434\u0435 \u043e\u0431\u0441\u0443\u0436\u0434\u0430\u043b\u0438",
    "\u043f\u043e \u0441\u043c\u044b\u0441\u043b\u0443 \u044d\u0442\u043e\u0433\u043e",
    "\u043f\u043e\u0445\u043e\u0436\u0435\u0435",
    "\u043f\u043e\u0445\u043e\u0436\u0438\u0439",
    "\u0442\u0430\u043a\u043e\u0435",
)
REPLY_SEMANTIC_EXCLUDE_MARKERS = (
    "this chat",
    "current chat",
    "from this chat",
    "in this chat",
    "to this chat",
    "this channel",
    "from this channel",
    "\u044d\u0442\u043e\u0442 \u0447\u0430\u0442",
    "\u0432 \u044d\u0442\u043e\u0442 \u0447\u0430\u0442",
    "\u0438\u0437 \u044d\u0442\u043e\u0433\u043e \u0447\u0430\u0442\u0430",
    "\u0442\u0435\u043a\u0443\u0449\u0438\u0439 \u0447\u0430\u0442",
)
SEMANTIC_MEDIA_SCAN_LIMIT = 8


@dataclass(slots=True)
class ActionRequest:
    action: str
    source_reference: str | int
    target_reference: str | int | None
    query: str
    message_limit: int
    within_hours: int | None
    prefix_text: str | None = None
    message_kind: str = "any"
    clock_time: str | None = None
    today_only: bool = False


@dataclass(slots=True)
class ResolvedChat:
    lookup: str | int
    chat_id: int
    label: str


class CrossChatActionService:
    def __init__(
        self,
        client: Client,
        config: AppConfig,
        groq_client: GroqClient,
        context_reader: ContextReader,
        chat_config_store: ChatConfigStore,
        tg_actions: TelegramActionService | None = None,
    ) -> None:
        self._client = client
        self._config = config
        self._groq_client = groq_client
        self._context_reader = context_reader
        self._chat_config_store = chat_config_store
        self._tg_actions = tg_actions
        self._recent_chat_references: dict[int, str | int] = {}
        self._message_transcript_cache: dict[tuple[int, int], str | None] = {}
        self._message_visual_cache: dict[tuple[int, int], str | None] = {}

    def parse_request(
        self, *, prompt: str, current_chat_id: int
    ) -> ActionRequest | None:
        return self._parse_request(prompt, current_chat_id)

    def describe_request(self, request: ActionRequest) -> str:
        source = str(request.source_reference)
        target = (
            str(request.target_reference)
            if request.target_reference is not None
            else "current chat"
        )
        if request.action == "direct_send":
            return f"Send prepared text to {target}."
        if request.action == "send_sticker_by_query":
            return f'Send a matching sticker to {target} using query "{request.query}".'
        if request.action == "forward_last":
            kind = request.message_kind.replace("_", " ")
            if request.query:
                return f'Copy up to {request.message_limit} {kind} message(s) from {source} to {target} matching "{request.query}".'
            return f"Copy up to {request.message_limit} {kind} message(s) from {source} to {target}."
        if request.action == "summarize":
            return f"Summarize recent messages from {source}."
        if request.action == "find":
            return f'Find messages in {source} matching "{request.query}".'
        if request.action == "extract":
            return f'Extract information from {source} using query "{request.query}".'
        if request.action == "rewrite":
            return f'Rewrite content from {source} using query "{request.query}".'
        if request.action == "inspect_chat":
            return f"Inspect chat or channel {source}."
        if request.action == "find_related_channel_link":
            return f"Find a related Telegram channel link for the current chat using {source}."
        return f"Execute cross-chat action {request.action}."

    async def maybe_execute(
        self,
        *,
        prompt: str,
        current_chat_id: int,
        excluded_message_ids: set[int] | None = None,
        reply_message: Any | None = None,
        style_instruction: str,
        response_mode: str = "ai_prefixed",
        response_style_mode: str = "NORMAL",
        bypass_summary_check: bool = False,
    ) -> str | None:
        request = self._parse_request(prompt, current_chat_id)
        if request is None:
            return None
        language = detect_language(prompt)
        request = self._apply_recent_reference_fallback(
            request, prompt, current_chat_id
        )
        request = await self._apply_reply_semantic_hint(
            request,
            prompt=prompt,
            reply_message=reply_message,
        )

        current_chat_config = await self._chat_config_store.resolve_chat(
            current_chat_id,
            config=self._config,
            state_settings=None,
        )
        if request.action == "find_related_channel_link":
            return await self._execute_find_related_channel_link(
                request,
                prompt=prompt,
                current_chat_id=current_chat_id,
                language=language,
                response_mode=response_mode,
            )
        if request.action == "direct_send":
            if request.target_reference is None or not request.query:
                return sanitize_ai_output(
                    tr("parse_chat_error", language),
                    user_query=prompt,
                    response_mode=response_mode,
                )
            try:
                target_chat = await self._resolve_chat(
                    request.target_reference, language
                )
            except ValueError as exc:
                return sanitize_ai_output(
                    str(exc), user_query=prompt, response_mode=response_mode
                )
            await self._client.send_message(
                target_chat.lookup, request.query, disable_web_page_preview=True
            )
            self._remember_recent_reference(current_chat_id, request.target_reference)
            return sanitize_ai_output(
                tr("sent_result_to_chat", language, chat=target_chat.label),
                user_query=prompt,
                response_mode=response_mode,
            )
        if (
            request.source_reference != current_chat_id
            or request.target_reference is not None
        ) and not current_chat_config.cross_chat_allowed:
            return sanitize_ai_output(
                tr("cross_chat_disabled", language),
                user_query=prompt,
                response_mode=response_mode,
            )

        if request.action == "send_sticker_by_query":
            delivery_reference = (
                request.target_reference
                if request.target_reference is not None
                else current_chat_id
            )
            try:
                target_chat = await self._resolve_chat(delivery_reference, language)
            except ValueError as exc:
                return sanitize_ai_output(
                    str(exc), user_query=prompt, response_mode=response_mode
                )
            self._remember_recent_reference(current_chat_id, delivery_reference)
            return await self._execute_send_sticker_by_query(
                request,
                target_chat=target_chat,
                language=language,
                response_mode=response_mode,
            )

        try:
            source_chat = await self._resolve_chat(request.source_reference, language)
        except ValueError as exc:
            return sanitize_ai_output(
                str(exc), user_query=prompt, response_mode=response_mode
            )
        self._remember_recent_reference(current_chat_id, request.source_reference)

        source_chat_config = await self._chat_config_store.resolve_chat(
            source_chat.chat_id,
            config=self._config,
            state_settings=None,
        )
        if request.action == "inspect_chat":
            return await self._execute_chat_documentation(
                source_chat,
                language=language,
                response_mode=response_mode,
            )
        if (
            request.action == "summarize"
            and not source_chat_config.summary_enabled
            and not bypass_summary_check
        ):
            return sanitize_ai_output(
                tr("summary_disabled", language),
                user_query=prompt,
                response_mode=response_mode,
            )

        target_chat: ResolvedChat | None = None
        if request.target_reference is not None:
            try:
                target_chat = await self._resolve_chat(
                    request.target_reference, language
                )
            except ValueError as exc:
                return sanitize_ai_output(
                    str(exc), user_query=prompt, response_mode=response_mode
                )

        if request.action == "forward_last":
            delivery_chat = target_chat or ResolvedChat(
                lookup=current_chat_id,
                chat_id=current_chat_id,
                label=f"chat_id {current_chat_id}",
            )
            return await self._execute_forward_last(
                request,
                source_chat,
                delivery_chat,
                current_chat_id=current_chat_id,
                excluded_message_ids=excluded_message_ids,
                language=language,
                response_mode=response_mode,
            )
        if request.action == "find":
            result_text = await self._execute_find(
                request, source_chat, language, response_mode=response_mode
            )
        else:
            result_text = await self._execute_generative(
                request,
                source_chat,
                style_instruction,
                prompt,
                response_mode=response_mode,
                response_style_mode=response_style_mode,
            )

        final_result_text = sanitize_ai_output(
            result_text, user_query=prompt, response_mode=response_mode
        )

        if target_chat is None:
            return final_result_text

        await self._client.send_message(target_chat.lookup, final_result_text)
        return sanitize_ai_output(
            tr("sent_result_to_chat", language, chat=target_chat.label),
            user_query=prompt,
            response_mode=response_mode,
        )

    def _parse_request(self, prompt: str, current_chat_id: int) -> ActionRequest | None:
        lowered = prompt.casefold()
        references = [match.group(0) for match in CHAT_REFERENCE_RE.finditer(prompt)]
        direct_send_request = self._parse_direct_send_request(prompt, current_chat_id)
        if direct_send_request is not None:
            return direct_send_request
        if not self._is_explicit_chat_action(lowered, references):
            return None

        action = self._detect_action(lowered)
        if action is None:
            return None

        delivery_requested = any(
            keyword in lowered for keyword in SEND_KEYWORDS + SAVE_KEYWORDS
        ) or self._targets_saved_messages(lowered)
        source_reference: str | int = current_chat_id
        target_reference: str | int | None = None

        if action != "find_related_channel_link":
            inferred_source, inferred_target = self._extract_named_references(
                prompt, current_chat_id
            )
            if references:
                source_reference = references[0]
            if inferred_source is not None:
                source_reference = inferred_source
            if inferred_target is not None:
                target_reference = inferred_target
            explicit_target = self._extract_explicit_target_reference(prompt)
            if explicit_target is not None:
                target_reference = explicit_target
        if delivery_requested and action != "find_related_channel_link":
            if any(
                keyword in lowered for keyword in SAVE_KEYWORDS
            ) or self._targets_saved_messages(lowered):
                target_reference = "me"
            elif len(references) >= 2:
                source_reference = references[0]
                target_reference = references[-1]
            elif len(references) == 1 and action == "summarize":
                source_reference = current_chat_id
                target_reference = references[0]
            elif target_reference is None:
                target_reference = current_chat_id
        if action == "send_sticker_by_query":
            source_reference = current_chat_id

        message_kind = self._parse_message_kind(prompt)
        message_limit = self._parse_message_limit(prompt, message_kind=message_kind)
        if (
            action == "forward_last"
            and MESSAGES_RE.search(prompt) is None
            and message_limit == self._config.default_summary_message_limit
        ):
            message_limit = 1
        if action == "send_sticker_by_query":
            message_limit = 1
        if any(marker in lowered for marker in ALL_MARKERS):
            message_limit = max(message_limit, 20)
        within_hours = self._parse_hours(prompt)
        clock_time = self._parse_clock_time(prompt)
        today_only = self._mentions_today(prompt)
        query_references = list(references)
        if isinstance(source_reference, str):
            query_references.append(source_reference)
        if isinstance(target_reference, str):
            query_references.append(target_reference)
        query = self._extract_query(prompt, query_references, message_kind=message_kind)
        prefix_text = self._extract_prefix_text(prompt)

        if action in {"extract", "rewrite"} and not query:
            query = "Ð³Ð»Ð°Ð²Ð½Ð¾Ðµ"

        return ActionRequest(
            action=action,
            source_reference=source_reference,
            target_reference=target_reference,
            query=query,
            message_limit=message_limit,
            within_hours=within_hours,
            prefix_text=prefix_text,
            message_kind=message_kind,
            clock_time=clock_time,
            today_only=today_only,
        )

    def _is_explicit_chat_action(
        self, lowered_prompt: str, references: list[str]
    ) -> bool:
        if references:
            return True
        return any(hint in lowered_prompt for hint in CHAT_ACTION_HINTS)

    def _parse_direct_send_request(
        self, prompt: str, current_chat_id: int
    ) -> ActionRequest | None:
        text = " ".join((prompt or "").split()).strip()
        if not text:
            return None
        lowered = text.casefold()
        if not any(keyword in lowered for keyword in WRITE_KEYWORDS + SEND_KEYWORDS):
            return None

        explicit_target = self._extract_direct_send_target(
            text
        ) or self._extract_explicit_target_reference(text)
        if explicit_target is not None:
            message_text = self._extract_direct_send_payload(text)
            if message_text:
                return ActionRequest(
                    action="direct_send",
                    source_reference=current_chat_id,
                    target_reference=explicit_target,
                    query=message_text,
                    message_limit=0,
                    within_hours=None,
                    prefix_text=None,
                )

        patterns = (
            re.compile(
                r"(?iu)^(?:Ð½Ð°Ð¿Ð¸ÑˆÐ¸|Ð¾Ñ‚Ð¿Ñ€Ð°Ð²ÑŒ|ÑÐºÐ¸Ð½ÑŒ|Ð·Ð°ÐºÐ¸Ð½ÑŒ|write|send|tell)\s+(?:Ð²\s+)?(?:Ð»Ð¸Ñ‡Ð½Ñ‹Ðµ\s+ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ|Ð»Ð¸Ñ‡ÐºÑƒ|Ð»Ñ|pm|dm|chat\s+with|to)\s+(.+?)\s+(?:Ñ‡Ñ‚Ð¾|text|message)\s+(.+)$"
            ),
            re.compile(
                r"(?iu)^(?:Ð½Ð°Ð¿Ð¸ÑˆÐ¸|Ð¾Ñ‚Ð¿Ñ€Ð°Ð²ÑŒ|ÑÐºÐ¸Ð½ÑŒ|Ð·Ð°ÐºÐ¸Ð½ÑŒ|write|send|tell)\s+(.+?)\s+(?:Ñ‡Ñ‚Ð¾|text|message)\s+(.+)$"
            ),
        )
        for pattern in patterns:
            match = pattern.search(text)
            if match is None:
                continue
            target_reference = self._cleanup_named_reference(match.group(1))
            message_text = self._cleanup_direct_send_text(match.group(2))
            if not target_reference or not message_text:
                continue
            if not self._looks_like_direct_send_target(target_reference):
                continue
            return ActionRequest(
                action="direct_send",
                source_reference=current_chat_id,
                target_reference=target_reference,
                query=message_text,
                message_limit=0,
                within_hours=None,
                prefix_text=None,
            )
        return None

    async def _apply_reply_semantic_hint(
        self,
        request: ActionRequest,
        *,
        prompt: str,
        reply_message: Any | None,
    ) -> ActionRequest:
        if reply_message is None:
            return request
        if request.action not in {"forward_last", "find", "send_sticker_by_query"}:
            return request
        if not self._should_use_reply_semantic_hint(prompt, request):
            return request
        semantic_hint = await self._build_reply_semantic_hint(
            reply_message,
            message_kind=request.message_kind,
        )
        if not semantic_hint:
            return request
        return replace(request, query=semantic_hint)

    def _should_use_reply_semantic_hint(
        self,
        prompt: str,
        request: ActionRequest,
    ) -> bool:
        normalized = " ".join((prompt or "").casefold().split())
        if not normalized:
            return False
        for marker in REPLY_SEMANTIC_EXCLUDE_MARKERS:
            normalized = normalized.replace(marker, " ")
        normalized = " ".join(normalized.split())
        if request.action == "send_sticker_by_query":
            return not (request.query or "").strip()
        if request.query is None:
            return any(marker in normalized for marker in REPLY_SEMANTIC_REFERENCE_MARKERS)
        return any(marker in normalized for marker in REPLY_SEMANTIC_REFERENCE_MARKERS)

    async def _build_reply_semantic_hint(
        self,
        message,
        *,
        message_kind: str,
    ) -> str | None:
        parts: list[str] = []
        text = (
            getattr(message, "text", None)
            or getattr(message, "caption", None)
            or ""
        ).strip()
        if text:
            parts.append(text)
        if self._message_is_voice_like(message):
            transcript = await self._get_transcript_for_message(message)
            if transcript:
                parts.append(transcript.strip())
        if self._message_is_photo_like(message):
            vision = await self._get_visual_summary_for_message(message)
            if vision:
                parts.append(vision.strip())
        sticker = getattr(message, "sticker", None)
        if sticker is not None:
            emoji = (getattr(sticker, "emoji", None) or "").strip()
            set_name = (getattr(sticker, "set_name", None) or "").strip()
            if emoji:
                parts.append(emoji)
            if set_name:
                parts.append(set_name.replace("_", " "))
        unique_parts: list[str] = []
        seen: set[str] = set()
        for part in parts:
            cleaned = " ".join((part or "").split()).strip(" ,.-")
            if not cleaned:
                continue
            lowered = cleaned.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            unique_parts.append(cleaned)
        if not unique_parts:
            return None
        if message_kind == "sticker":
            preferred = unique_parts[:2]
        else:
            preferred = unique_parts[:3]
        semantic_hint = ". ".join(preferred).strip()
        if len(semantic_hint) > 280:
            semantic_hint = semantic_hint[:277].rstrip(" ,.-") + "..."
        return semantic_hint or None

    def _detect_action(self, lowered_prompt: str) -> str | None:
        normalized_prompt = (lowered_prompt or "").casefold()
        if self._looks_like_sticker_emoji_request(normalized_prompt):
            return "send_sticker_by_query"
        if any(keyword in normalized_prompt for keyword in SEND_KEYWORDS + SAVE_KEYWORDS) and self._looks_like_semantic_delivery_request(normalized_prompt):
            return "forward_last"
        if self._looks_like_channel_link_search(normalized_prompt):
            return "find_related_channel_link"
        if any(keyword in normalized_prompt for keyword in DOCUMENT_KEYWORDS):
            return "inspect_chat"
        if any(keyword in lowered_prompt for keyword in SEND_KEYWORDS) and any(
            marker in lowered_prompt
            for marker in ("Ð¿Ð¾ÑÐ»ÐµÐ´", "ÑÐ¾Ð¾", "ÑÐ¾Ð¾Ð±Ñ‰", "last", "latest")
        ):
            return "forward_last"
        if any(
            keyword in normalized_prompt
            for keyword in ("ÑÐºÐ¸Ð½ÑŒ", "Ð·Ð°ÐºÐ¸Ð½ÑŒ", "Ð¿ÐµÑ€ÐµÑˆÐ»Ð¸", "Ð¾Ñ‚Ð¿Ñ€Ð°Ð²ÑŒ", "send", "forward")
        ) and any(
            keyword in normalized_prompt
            for keyword in ("Ð¿Ð¾ÑÐ»ÐµÐ´Ð½", "last message", "latest message")
        ):
            return "forward_last"
        if any(
            keyword in normalized_prompt
            for keyword in ("Ð¿ÐµÑ€ÐµÑ„Ð¾Ñ€Ð¼ÑƒÐ»", "Ð¿ÐµÑ€ÐµÐ¿Ð¸Ñˆ", "rewrite")
        ):
            return "rewrite"
        if any(
            keyword in normalized_prompt
            for keyword in ("ÑÑƒÐ¼Ð¼", "ÐºÑ€Ð°Ñ‚ÐºÐ¾", "Ð¸Ñ‚Ð¾Ð³", "summary", "summar")
        ):
            return "summarize"
        if any(
            keyword in normalized_prompt
            for keyword in ("Ð¸Ð·Ð²Ð»ÐµÐº", "Ð²Ñ‹Ñ‚Ð°Ñ‰", "Ð´Ð¾ÑÑ‚Ð°Ð½", "extract")
        ):
            return "extract"
        if any(
            keyword in normalized_prompt
            for keyword in ("Ð½Ð°Ð¹Ð´", "Ð¿Ð¾Ð¸ÑÐº", "find", "search")
        ):
            return "find"
        if any(keyword in lowered_prompt for keyword in FORWARD_LAST_KEYWORDS):
            return "forward_last"
        if any(keyword in lowered_prompt for keyword in FIND_KEYWORDS):
            return "find"
        if any(keyword in lowered_prompt for keyword in EXTRACT_KEYWORDS):
            return "extract"
        if any(keyword in lowered_prompt for keyword in REWRITE_KEYWORDS):
            return "rewrite"
        if any(keyword in lowered_prompt for keyword in SUMMARIZE_KEYWORDS):
            return "summarize"
        return None

    def _extract_direct_send_payload(self, text: str) -> str:
        prompt = text or ""
        marker_pattern = "|".join(
            re.escape(marker) for marker in DIRECT_SEND_TEXT_MARKERS
        )
        quoted_match = re.search(
            rf'(?iu)(?:{marker_pattern})\s+["\'](.+?)["\']',
            prompt,
        )
        if quoted_match:
            return self._cleanup_direct_send_text(quoted_match.group(1))
        plain_match = re.search(
            rf"(?iu)(?:{marker_pattern})\s+(.+?)(?=(?:\s+Ð²\s+(?:Ñ‡Ð°Ñ‚|ÐºÐ°Ð½Ð°Ð»)\b|\s+to\s+(?:chat|channel)\b|$))",
            prompt,
        )
        if plain_match:
            return self._cleanup_direct_send_text(plain_match.group(1))
        fallback_match = re.search(
            r'(?iu)^(?:Ð½Ð°Ð¿Ð¸ÑˆÐ¸(?:-ÐºÐ°)?|ÑÐºÐ°Ð¶Ð¸|write|send|tell)\s+["\'](.+?)["\']',
            prompt,
        )
        if fallback_match:
            return self._cleanup_direct_send_text(fallback_match.group(1))
        lowered_prompt = prompt.casefold()
        if any(marker in lowered_prompt for marker in DIRECT_SEND_TEXT_MARKERS):
            any_quote_match = re.search(r'["\'](.+?)["\']', prompt)
            if any_quote_match:
                return self._cleanup_direct_send_text(any_quote_match.group(1))
        return ""

    def _extract_direct_send_target(self, text: str) -> str | None:
        prompt = " ".join((text or "").split()).strip()
        if not prompt:
            return None
        patterns = (
            re.compile(
                r"(?iu)\b(?:Ð²|to|into)\s+(?:Ñ‡Ð°Ñ‚(?:\s+Ñ(?:\s+Ð½Ð°Ð·Ð²Ð°Ð½Ð¸ÐµÐ¼)?)?|ÐºÐ°Ð½Ð°Ð»(?:\s+Ñ(?:\s+Ð½Ð°Ð·Ð²Ð°Ð½Ð¸ÐµÐ¼)?)?|chat(?:\s+with)?|channel(?:\s+with)?)\s+(.+?)(?=(?:\s+(?:Ñ„Ñ€Ð°Ð·|Ñ‚ÐµÐºÑÑ‚|ÑÐ¾Ð¾|ÑÐ¾Ð¾Ð±Ñ‰|phrase|text|message)\b|$))"
            ),
            re.compile(
                r"(?iu)\b(?:Ð²|to|into)\s+(@[A-Za-z][A-Za-z0-9_]{4,31}|-?\d{6,}|me)\b"
            ),
        )
        for pattern in patterns:
            match = pattern.search(prompt)
            if match is None:
                continue
            cleaned = self._cleanup_named_reference(match.group(1))
            if cleaned:
                return cleaned
        return None

    def _looks_like_channel_link_search(self, lowered_prompt: str) -> bool:
        if not lowered_prompt:
            return False
        asks_to_find = any(keyword in lowered_prompt for keyword in FIND_KEYWORDS)
        asks_for_channel = any(
            keyword in lowered_prompt for keyword in CHANNEL_LINK_KEYWORDS
        )
        asks_for_related_name = any(
            keyword in lowered_prompt
            for keyword in (
                "ÑÐ²ÑÐ·Ð°Ð½",
                "ÑÐ²ÑÐ·Ð°Ð½Ð½",
                "Ð¸Ð¼ÐµÐ½ÐµÐ¼",
                "Ð¸Ð¼Ñ ÑÑ‚Ð¾Ð³Ð¾ Ñ‡Ð°Ñ‚Ð°",
                "Ð¸Ð¼ÐµÐ½Ð¸ ÑÑ‚Ð¾Ð³Ð¾ Ñ‡Ð°Ñ‚Ð°",
                "ÑÑ‚Ð¾Ð³Ð¾ Ñ‡Ð°Ñ‚Ð°",
                "ÑÑ‚Ð¸Ð¼ Ñ‡Ð°Ñ‚",
                "Ð¿Ð¾Ñ…Ð¾Ð¶",
                "Ð¿Ð¾Ñ…Ð¾Ð¶Ðµ",
                "Ð¿Ð¾Ñ…Ð¾Ð¶ÐµÐµ Ð¸Ð¼Ñ",
                "Ð¿Ð¾Ñ…Ð¾Ð¶ÐµÐµ Ð½Ð° Ð¸Ð¼Ñ",
                "Ð¿Ð¾Ñ…Ð¾Ð¶ Ð½Ð° Ð¸Ð¼Ñ",
                "related",
                "same name",
                "same title",
                "similar name",
                "matching name",
                "this chat",
                "current chat",
            )
        )
        asks_for_link = any(
            keyword in lowered_prompt for keyword in ("ÑÑÑ‹Ð»Ðº", "link", "url", "t.me")
        )
        asks_for_global_search = any(
            keyword in lowered_prompt
            for keyword in (
                "Ð¾Ð±Ñ‰ÐµÐ¼ Ð¿Ð¾Ð¸ÑÐºÐµ",
                "Ð¾Ð±Ñ‰Ð¸Ð¹ Ð¿Ð¾Ð¸ÑÐº",
                "Ð¿Ð¾Ð¸ÑÐºÐµ Ñ‚Ð³",
                "Ð¿Ð¾Ð¸ÑÐº Ñ‚Ð³",
                "global search",
                "telegram search",
                "search telegram",
            )
        )
        return (
            asks_to_find
            and asks_for_channel
            and (asks_for_related_name or asks_for_link or asks_for_global_search)
        )

    def _apply_recent_reference_fallback(
        self, request: ActionRequest, prompt: str, current_chat_id: int
    ) -> ActionRequest:
        lowered = " ".join((prompt or "").strip().casefold().split())
        if request.source_reference != current_chat_id:
            return request
        if not any(
            marker in lowered
            for marker in (
                "Ñ ÑÑ‚Ð¾Ð³Ð¾ ÐºÐ°Ð½Ð°Ð»Ð°",
                "Ñ ÑÑ‚Ð¾Ð³Ð¾ Ñ‡Ð°Ñ‚Ð°",
                "from this channel",
                "from that channel",
                "from this chat",
            )
        ):
            return request
        recent_reference = self._recent_chat_references.get(current_chat_id)
        if recent_reference is None:
            return request
        return ActionRequest(
            action=request.action,
            source_reference=recent_reference,
            target_reference=request.target_reference,
            query=request.query,
            message_limit=request.message_limit,
            within_hours=request.within_hours,
            prefix_text=request.prefix_text,
            message_kind=request.message_kind,
            clock_time=request.clock_time,
            today_only=request.today_only,
        )

    def _remember_recent_reference(
        self, current_chat_id: int, reference: str | int | None
    ) -> None:
        if reference is None:
            return
        self._recent_chat_references[current_chat_id] = reference

    def _parse_message_kind(self, prompt: str) -> str:
        lowered = " ".join((prompt or "").casefold().split())
        if any(marker in lowered for marker in PHOTO_OR_VOICE_MARKERS):
            return "photo_or_voice"
        if any(marker in lowered for marker in MEDIA_TYPE_MARKERS["sticker"]):
            return "sticker"
        if any(marker in lowered for marker in MEDIA_TYPE_MARKERS["voice"]):
            return "voice"
        if any(marker in lowered for marker in MEDIA_TYPE_MARKERS["photo"]):
            return "photo"
        if any(marker in lowered for marker in MEDIA_TYPE_MARKERS["text"]):
            return "text"
        return "any"

    def _parse_clock_time(self, prompt: str) -> str | None:
        match = CLOCK_TIME_RE.search(prompt or "")
        if not match:
            return None
        return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"

    def _mentions_today(self, prompt: str) -> bool:
        lowered = " ".join((prompt or "").casefold().split())
        return any(marker in lowered for marker in TODAY_MARKERS)

    def _looks_like_semantic_delivery_request(self, lowered_prompt: str) -> bool:
        normalized = " ".join((lowered_prompt or "").split())
        if any(marker in normalized for marker in FORWARD_LAST_KEYWORDS):
            return True
        if any(marker in normalized for marker in PHOTO_OR_VOICE_MARKERS):
            return True
        if any(marker in normalized for marker in TODAY_MARKERS + AROUND_TIME_MARKERS):
            return True
        if CLOCK_TIME_RE.search(normalized):
            return True
        for markers in MEDIA_TYPE_MARKERS.values():
            if any(marker in normalized for marker in markers):
                return True
        return False

    def _looks_like_sticker_emoji_request(self, lowered_prompt: str) -> bool:
        normalized = " ".join((lowered_prompt or "").split())
        if not any(keyword in normalized for keyword in SEND_KEYWORDS + SAVE_KEYWORDS):
            return False
        if not any(marker in normalized for marker in MEDIA_TYPE_MARKERS["sticker"]):
            return False
        if any(marker in normalized for marker in STICKER_QUERY_MARKERS):
            return True
        return any(
            marker in normalized
            for marker in (
                "sticker with",
                "sticker by",
                "sticker for",
                "\u0441\u0442\u0438\u043a\u0435\u0440 \u0441",
                "\u0441\u0442\u0438\u043a\u0435\u0440 \u043f\u043e",
                "\u0441\u0442\u0438\u043a\u0435\u0440 \u0441",
                "\u0441\u0442\u0438\u043a\u0435\u0440 \u0434\u043b\u044f",
            )
        )

    def _parse_message_limit(self, prompt: str, *, message_kind: str = "any") -> int:
        match = MESSAGES_RE.search(prompt)
        if match:
            return max(1, min(80, int(match.group(1))))
        if message_kind != "any":
            media_match = re.search(
                r"(?iu)\b(\d{1,3})\s+(?:photos?|images?|pictures?|voice(?:\s+messages?)?|voice\s+notes?|audio|stickers?|messages?|"
                r"\u0444\u043e\u0442\u043e|\u0433\u043e\u043b\u043e\u0441\u043e\u0432\w*|\u0441\u0442\u0438\u043a\u0435\u0440\w*|\u0441\u043e\u043e\u0431\u0449\u0435\u043d\w*)\b",
                prompt,
            )
            if media_match:
                return max(1, min(80, int(media_match.group(1))))
        return self._config.default_summary_message_limit

    def _parse_hours(self, prompt: str) -> int | None:
        match = HOURS_RE.search(prompt)
        if not match:
            return None
        return max(1, min(72, int(match.group(1))))

    def _extract_query(self, prompt: str, references: list[str], *, message_kind: str = "any") -> str:
        cleaned = prompt
        for reference in references:
            reference_text = str(reference or "").strip()
            if not reference_text:
                continue
            if len(reference_text) <= 3 and reference_text.isalnum():
                cleaned = re.sub(
                    rf"(?iu)\b{re.escape(reference_text)}\b", " ", cleaned
                )
            else:
                cleaned = re.sub(re.escape(reference_text), " ", cleaned, flags=re.IGNORECASE)
        cleaned = HOURS_RE.sub(" ", cleaned)
        cleaned = MESSAGES_RE.sub(" ", cleaned)
        cleaned = CLOCK_TIME_RE.sub(" ", cleaned)
        cleaned = re.sub(r"(?iu)Ð²\s+Ð½Ð°Ñ‡Ð°Ð»Ð¾\s+Ð´Ð¾Ð±Ð°Ð²[^\"]+\"[^\"]+\"", " ", cleaned)
        cleaned = re.sub(r"(?iu)at\s+the\s+start\s+add[^\"]+\"[^\"]+\"", " ", cleaned)

        for keyword in (
            SUMMARIZE_KEYWORDS
            + FIND_KEYWORDS
            + EXTRACT_KEYWORDS
            + REWRITE_KEYWORDS
            + SEND_KEYWORDS
            + SAVE_KEYWORDS
            + PHOTO_OR_VOICE_MARKERS
            + TODAY_MARKERS
            + AROUND_TIME_MARKERS
        ):
            pattern = rf"(?iu)\b{re.escape(keyword)}\b"
            cleaned = re.sub(pattern, " ", cleaned)
        for markers in MEDIA_TYPE_MARKERS.values():
            for keyword in markers:
                pattern = rf"(?iu)\b{re.escape(keyword)}\b"
                cleaned = re.sub(pattern, " ", cleaned)

        cleaned = re.sub(
            r"\b(?:in|from|into|to|chat|please|and|where|about|with|latest|last|near|around|any|similar|matching)\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\b(?:this|current|today|all|closest)\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\b(?:Ð²|Ð¸Ð·|Ð´Ð»Ñ|Ñ‡Ð°Ñ‚|Ñ‡Ð°Ñ‚Ð°|Ñ‡Ð°Ñ‚Ðµ|Ð¸|Ð¿Ð¾|Ð¿Ñ€Ð¾)\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.-")
        cleaned = re.sub(r"(?iu)^\d+\b", "", cleaned).strip()
        cleaned = re.sub(
            r"(?iu)^(?:Ñ\s+)?(?:Ð½Ð°Ð·Ð²Ð°Ð½Ð¸ÐµÐ¼|Ð¸Ð¼ÐµÐ½ÐµÐ¼|named|called)\s+",
            "",
            cleaned,
        ).strip()
        if message_kind == "sticker" and cleaned:
            return cleaned
        lowered = cleaned.casefold()
        if not cleaned or lowered in WEAK_QUERY_MARKERS:
            return None
        return cleaned or None

    def _extract_explicit_target_reference(self, prompt: str) -> str | int | None:
        text = " ".join((prompt or "").split()).strip()
        lowered = text.casefold()
        if self._targets_saved_messages(lowered):
            return "me"
        username_match = re.search(
            r"(?iu)\b(?:Ð²|to|into)\s+(@[A-Za-z][A-Za-z0-9_]{4,31})\b", text
        )
        if username_match:
            return username_match.group(1)
        named_match = re.search(
            r"(?iu)\b(?:Ð²|to|into)\s+(?:Ñ‡Ð°Ñ‚(?:\s+Ñ)?|ÐºÐ°Ð½Ð°Ð»(?:\s+Ñ)?|chat\s+with|channel\s+with)\s+(.+?)(?=(?:,\s*|\s+Ñ\s+Ð¿Ð¾Ð´Ð¿Ð¸ÑÑŒÑŽ\b|\s+with\s+caption\b|$))",
            text,
        )
        if named_match:
            return self._cleanup_named_reference(named_match.group(1))
        return None

    def _targets_saved_messages(self, lowered_prompt: str) -> bool:
        return any(
            marker in (lowered_prompt or "")
            for marker in (
                "Ð² Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½Ð¾Ðµ",
                "Ð² Ð¼Ð¾Ðµ Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½Ð¾Ðµ",
                "Ð² Ð¼Ð¾Ñ‘ Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½Ð¾Ðµ",
                "to saved messages",
                "into saved messages",
            )
        )

    def _extract_named_references(
        self, prompt: str, current_chat_id: int
    ) -> tuple[str | int | None, str | int | None]:
        text = " ".join((prompt or "").split()).strip()
        if not text:
            return None, None
        source_reference: str | int | None = None
        target_reference: str | int | None = None

        lowered = text.casefold()
        if (
            "Ð¸Ð· ÑÑ‚Ð¾Ð³Ð¾ Ñ‡Ð°Ñ‚Ð°" in lowered
            or "from this chat" in lowered
            or "Ð¸Ð· Ñ‚ÐµÐºÑƒÑ‰ÐµÐ³Ð¾ Ñ‡Ð°Ñ‚Ð°" in lowered
        ):
            source_reference = current_chat_id
        elif (
            "Ð¸Ð· Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½Ð¾Ð³Ð¾" in lowered
            or "from saved messages" in lowered
            or "from saved" in lowered
        ):
            source_reference = "me"

        source_match = re.search(
            r"(?iu)\b(?:Ð¸Ð·|from)\s+(.+?)(?=(?:,\s*|\s+\b(?:Ð¸|and)\b\s+|\s+\b(?:Ð²|to|into)\b\s+|$))",
            text,
        )
        if source_match:
            source_reference = self._cleanup_named_reference(source_match.group(1))
            if isinstance(source_reference, str):
                source_reference = re.sub(
                    r"(?iu)\s+(?:around|near|about|today|latest|last)\b.*$",
                    "",
                    source_reference,
                ).strip()
                source_reference = re.sub(
                    r"(?iu)\s+(?:where|with|about|\u0433\u0434\u0435|\u0441|\u043f\u0440\u043e)\b.*$",
                    "",
                    source_reference,
                ).strip()
                source_reference = re.sub(
                    r"(?iu)\s+\d{1,2}:\d{2}\b.*$",
                    "",
                    source_reference,
                ).strip()
            if isinstance(source_reference, str) and source_reference.casefold() in {
                "ÑÑ‚Ð¾Ð³Ð¾ Ñ‡Ð°Ñ‚Ð°",
                "this chat",
                "current chat",
            }:
                source_reference = current_chat_id

        target_match = re.search(
            r"(?iu)\b(?:Ð²|to|into)\s+(?:Ñ‡Ð°Ñ‚(?:\s+Ñ)?|ÐºÐ°Ð½Ð°Ð»(?:\s+Ñ)?|Ð±Ð¾Ñ‚(?:\s+Ñ)?|dialog\s+with|chat\s+with|channel\s+with)?\s*(.+?)(?=(?:,\s*|\s+\b(?:Ð¿Ð¾ÑÐ»ÐµÐ´Ð½|latest|last|Ð¸|and)\b|$))",
            text,
        )
        if target_match:
            target_reference = self._cleanup_named_reference(target_match.group(1))
        else:
            chat_with_match = re.search(
                r"(?iu)\b(?:Ñ‡Ð°Ñ‚\s+Ñ|ÐºÐ°Ð½Ð°Ð»\s+Ñ|Ð±Ð¾Ñ‚\s+Ñ|chat\s+with|channel\s+with)\s+(.+?)(?=(?:,\s*|\s+\b(?:Ð¿Ð¾ÑÐ»ÐµÐ´Ð½|latest|last|Ð¸|and)\b|$))",
                text,
            )
            if chat_with_match:
                target_reference = self._cleanup_named_reference(
                    chat_with_match.group(1)
                )
        return source_reference, target_reference

    def _looks_like_direct_send_target(self, target_reference: str | None) -> bool:
        cleaned = " ".join((target_reference or "").strip().split())
        if not cleaned:
            return False
        lowered = cleaned.casefold()
        if lowered in {"Ð²ÑÑ‘", "Ð²ÑÐµ", "everything", "all", "Ñ‡Ñ‚Ð¾", "text", "message"}:
            return False
        if CHAT_REFERENCE_RE.fullmatch(cleaned) is not None:
            return True
        if any(
            marker in lowered
            for marker in ("Ñ‡Ð°Ñ‚", "ÐºÐ°Ð½Ð°Ð»", "Ð»Ð¸Ñ‡", "Ð»Ñ", "chat", "channel", "pm", "dm")
        ):
            return True
        if len(cleaned.split()) >= 2:
            return True
        return False

    def _cleanup_named_reference(self, value: str | None) -> str | None:
        cleaned = " ".join((value or "").strip(" ,.-").split())
        if not cleaned:
            return None
        cleaned = re.sub(
            r"(?iu)^(?:Ñ‡Ð°Ñ‚|Ñ‡Ð°Ñ‚Ð°|Ñ‡Ð°Ñ‚Ðµ|ÐºÐ°Ð½Ð°Ð»|ÐºÐ°Ð½Ð°Ð»Ð°|ÐºÐ°Ð½Ð°Ð»Ðµ|Ð±ÐµÑÐµÐ´Ð°|Ð´Ð¸Ð°Ð»Ð¾Ð³|Ð±Ð¾Ñ‚|Ð±Ð¾Ñ‚Ð°)\s+",
            "",
            cleaned,
        ).strip()
        cleaned = re.sub(
            r"(?iu)^(?:Ñ|Ð¿Ð¾Ð´)\s+(?:Ð¸Ð¼ÐµÐ½ÐµÐ¼|Ð½Ð°Ð·Ð²Ð°Ð½Ð¸ÐµÐ¼|Ð½Ð°Ð·Ð²Ð°Ð½Ð¸Ðµ)\s+", "", cleaned
        ).strip()
        cleaned = re.sub(r"(?iu)^Ñ\s+", "", cleaned).strip()
        if not cleaned:
            return None
        return cleaned

    def _extract_prefix_text(self, prompt: str) -> str | None:
        caption_match = re.search(
            r'(?iu)(?:Ñ\s+Ð¿Ð¾Ð´Ð¿Ð¸ÑÑŒÑŽ|with\s+caption|with\s+text)\s+["\'](.+?)["\']',
            prompt or "",
        )
        if caption_match:
            value = " ".join(caption_match.group(1).split()).strip()
            return value or None
        plain_caption_match = re.search(
            r"(?iu)(?:Ñ\s+Ð¿Ð¾Ð´Ð¿Ð¸ÑÑŒÑŽ|with\s+caption|with\s+text)\s+(.+?)(?:$|,\s*|\s+\b(?:and|Ð¸)\b)",
            prompt or "",
        )
        if plain_caption_match:
            value = " ".join(plain_caption_match.group(1).strip(" ,.-").split()).strip(
                "'\""
            )
            return value or None
        match = re.search(
            r'(?iu)(?:Ð²\s+Ð½Ð°Ñ‡Ð°Ð»Ð¾\s+Ð´Ð¾Ð±Ð°Ð²[^\"]*|at\s+the\s+start\s+add[^\"]*)["â€œ](.+?)["â€]',
            prompt or "",
        )
        if not match:
            plain_match = re.search(
                r"(?iu)(?:Ð²\s+Ð½Ð°Ñ‡Ð°Ð»Ð¾\s+Ð´Ð¾Ð±Ð°Ð²(?:ÑŒ|Ð¸Ñ‚ÑŒ)?\s+Ñ‚ÐµÐºÑÑ‚|at\s+the\s+start\s+add\s+text)\s+(.+?)(?:$|,\s*|\s+\b(?:Ð¸|and)\b)",
                prompt or "",
            )
            if not plain_match:
                return None
            value = " ".join(plain_match.group(1).strip(" ,.-").split()).strip("'\"â€œâ€")
            return value or None
        value = " ".join(match.group(1).split()).strip()
        return value or None

    def _cleanup_direct_send_text(self, value: str | None) -> str:
        cleaned = " ".join((value or "").strip().split()).strip()
        if not cleaned:
            return ""
        if (cleaned.startswith('"') and cleaned.endswith('"')) or (
            cleaned.startswith("'") and cleaned.endswith("'")
        ):
            cleaned = cleaned[1:-1].strip()
        return cleaned

    async def _execute_send_sticker_by_query(
        self,
        request: ActionRequest,
        *,
        target_chat: ResolvedChat,
        language: str,
        response_mode: str = "ai_prefixed",
    ) -> str:
        if self._tg_actions is None:
            return sanitize_ai_output(
                "Sticker lookup is unavailable in this build.",
                user_query=request.query,
                response_mode=response_mode,
            )
        sent, candidate = await self._tg_actions.send_sticker_by_query(
            target_chat.lookup,
            request.query,
        )
        if sent is None or candidate is None:
            if language == "en":
                text = f'I could not find a suitable sticker for "{request.query}".'
            else:
                text = f'\u042f \u043d\u0435 \u043d\u0430\u0448\u0451\u043b \u043f\u043e\u0434\u0445\u043e\u0434\u044f\u0449\u0438\u0439 \u0441\u0442\u0438\u043a\u0435\u0440 \u0434\u043b\u044f "{request.query}".'
            return sanitize_ai_output(
                text,
                user_query=request.query,
                response_mode=response_mode,
            )
        return sanitize_ai_output(
            tr("sent_result_to_chat", language, chat=target_chat.label),
            user_query=request.query,
            response_mode=response_mode,
        )

    async def _select_matching_messages(
        self,
        request: ActionRequest,
        *,
        source_chat: ResolvedChat,
        current_chat_id: int,
        excluded_message_ids: set[int] | None,
    ) -> list[Any]:
        candidates: list[Any] = []
        scan_limit = self._select_scan_limit(request)
        async for message in self._client.get_chat_history(
            source_chat.lookup, limit=scan_limit
        ):
            if self._should_skip_forward_candidate(
                message,
                source_chat_id=source_chat.chat_id,
                current_chat_id=current_chat_id,
                excluded_message_ids=excluded_message_ids,
            ):
                continue
            if not self._message_matches_request(message, request):
                continue
            candidates.append(message)
            if (
                not request.query
                and request.clock_time is None
                and len(candidates) >= max(1, request.message_limit)
            ):
                break

        if not candidates:
            return []
        if not request.query:
            if request.clock_time is not None:
                candidates.sort(
                    key=lambda message: (
                        self._clock_time_distance(
                            self._message_datetime(message),
                            request.clock_time or "00:00",
                        ),
                        -self._message_datetime(message).timestamp(),
                    )
                )
            return candidates[: max(1, request.message_limit)]

        scored: list[tuple[int, float, Any]] = []
        for message in candidates[: max(SEMANTIC_MEDIA_SCAN_LIMIT, request.message_limit * 2)]:
            summary = await self._build_message_search_summary(message, request)
            if not summary:
                continue
            score = await self._score_message_match(
                request.query,
                summary,
                message_kind=request.message_kind,
            )
            if score <= 0:
                continue
            scored.append((score, self._message_datetime(message).timestamp(), message))

        if not scored:
            return []
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored[: max(1, request.message_limit)]]

    def _select_scan_limit(self, request: ActionRequest) -> int:
        limit = max(30, self._config.default_context_scan_limit)
        limit = max(limit, request.message_limit * 10)
        if request.query:
            limit = max(limit, 120)
        if request.clock_time or request.today_only:
            limit = max(limit, 180)
        return min(limit, 320)

    def _message_matches_request(self, message, request: ActionRequest) -> bool:
        if not self._message_matches_kind(message, request.message_kind):
            return False
        if not self._message_has_supported_content(message, request.message_kind):
            return False
        message_dt = self._message_datetime(message)
        if request.within_hours is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=request.within_hours)
            if message_dt < cutoff:
                return False
        if request.today_only:
            local_now = datetime.now().astimezone()
            local_message = message_dt.astimezone(local_now.tzinfo)
            if local_message.date() != local_now.date():
                return False
        if request.clock_time and not self._message_matches_clock_time(message_dt, request.clock_time):
            return False
        return True

    def _message_matches_kind(self, message, message_kind: str) -> bool:
        if message_kind == "photo":
            return self._message_is_photo_like(message)
        if message_kind == "voice":
            return self._message_is_voice_like(message)
        if message_kind == "sticker":
            return bool(getattr(message, "sticker", None))
        if message_kind == "text":
            return self._message_is_text_only(message)
        if message_kind == "photo_or_voice":
            return self._message_is_photo_like(message) or self._message_is_voice_like(message)
        return self._message_has_supported_content(message, message_kind)

    def _message_has_supported_content(self, message, message_kind: str = "any") -> bool:
        if message_kind == "text":
            return self._message_is_text_only(message)
        if self._message_is_text_only(message):
            return True
        if self._message_is_photo_like(message):
            return True
        if self._message_is_voice_like(message):
            return True
        if getattr(message, "sticker", None) is not None:
            return True
        return False

    def _message_is_text_only(self, message) -> bool:
        text = (
            getattr(message, "text", None)
            or getattr(message, "caption", None)
            or ""
        ).strip()
        if not text:
            return False
        return not any(
            (
                getattr(message, "photo", None),
                getattr(message, "video", None),
                getattr(message, "document", None),
                getattr(message, "audio", None),
                getattr(message, "voice", None),
                getattr(message, "animation", None),
                getattr(message, "video_note", None),
                getattr(message, "sticker", None),
            )
        )

    def _message_is_photo_like(self, message) -> bool:
        if getattr(message, "photo", None) is not None:
            return True
        document = getattr(message, "document", None)
        mime = getattr(document, "mime_type", "") or ""
        return bool(document is not None and mime.startswith("image/"))

    def _message_is_voice_like(self, message) -> bool:
        return any(
            (
                getattr(message, "voice", None),
                getattr(message, "audio", None),
                getattr(message, "video_note", None),
            )
        )

    def _message_matches_clock_time(self, message_dt: datetime, clock_time: str) -> bool:
        return self._clock_time_distance(message_dt, clock_time) <= 90

    def _clock_time_distance(self, message_dt: datetime, clock_time: str) -> int:
        try:
            hours, minutes = [int(part) for part in clock_time.split(":", 1)]
        except ValueError:
            return 0
        local_dt = message_dt.astimezone(datetime.now().astimezone().tzinfo)
        target_minutes = hours * 60 + minutes
        current_minutes = local_dt.hour * 60 + local_dt.minute
        return abs(current_minutes - target_minutes)

    def _message_datetime(self, message) -> datetime:
        date = getattr(message, "date", None)
        if isinstance(date, datetime):
            if date.tzinfo is None:
                return date.replace(tzinfo=timezone.utc)
            return date
        return datetime.now(timezone.utc)

    async def _build_message_search_summary(
        self,
        message,
        request: ActionRequest,
    ) -> str:
        parts: list[str] = []
        text = (
            getattr(message, "text", None)
            or getattr(message, "caption", None)
            or ""
        ).strip()
        if text:
            parts.append(f"text: {text}")
        if self._message_is_voice_like(message):
            transcript = await self._get_transcript_for_message(message)
            if transcript:
                parts.append(f"audio transcript: {transcript}")
        if self._message_is_photo_like(message):
            vision = await self._get_visual_summary_for_message(message)
            if vision:
                parts.append(f"image description: {vision}")
        sticker = getattr(message, "sticker", None)
        if sticker is not None:
            emoji = (getattr(sticker, "emoji", None) or "").strip()
            set_name = (getattr(sticker, "set_name", None) or "").strip()
            sticker_bits = []
            if emoji:
                sticker_bits.append(f"emoji {emoji}")
            if set_name:
                sticker_bits.append(f"set {set_name}")
            if sticker_bits:
                parts.append("sticker metadata: " + ", ".join(sticker_bits))
        return "\n".join(part for part in parts if part).strip()

    async def _get_transcript_for_message(self, message) -> str | None:
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        message_id = getattr(message, "id", None)
        if chat_id is None or message_id is None:
            return None
        cache_key = (chat_id, message_id)
        if cache_key in self._message_transcript_cache:
            return self._message_transcript_cache[cache_key]
        if self._tg_actions is None:
            self._message_transcript_cache[cache_key] = None
            return None
        audio_data = await self._tg_actions.get_message_audio_bytes(message)
        if audio_data is None:
            self._message_transcript_cache[cache_key] = None
            return None
        raw_audio, filename = audio_data
        transcript = await self._groq_client.transcribe_audio(raw_audio, filename)
        self._message_transcript_cache[cache_key] = transcript
        return transcript

    async def _get_visual_summary_for_message(self, message) -> str | None:
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        message_id = getattr(message, "id", None)
        if chat_id is None or message_id is None:
            return None
        cache_key = (chat_id, message_id)
        if cache_key in self._message_visual_cache:
            return self._message_visual_cache[cache_key]
        if self._tg_actions is None:
            self._message_visual_cache[cache_key] = None
            return None
        image_data = await self._tg_actions.get_message_image_base64(message)
        if image_data is None:
            self._message_visual_cache[cache_key] = None
            return None
        image_b64, image_mime = image_data
        try:
            result = await self._groq_client.generate_vision_reply(
                "Describe the main visible content of this Telegram image or sticker in one concise sentence for semantic search.",
                image_b64,
                image_mime,
                user_query="semantic media search",
                response_mode="human_like_owner",
            )
            summary = " ".join((result.text or "").split()).strip() or None
        except Exception:
            summary = None
        self._message_visual_cache[cache_key] = summary
        return summary

    async def _score_message_match(
        self,
        query: str,
        summary: str,
        *,
        message_kind: str,
    ) -> int:
        lexical_score = self._lexical_score(query, summary)
        if not summary:
            return lexical_score
        model_score = await self._score_summary_with_model(query, summary, message_kind)
        return max(lexical_score, model_score)

    def _lexical_score(self, query: str, summary: str) -> int:
        query_tokens = {token for token in QUERY_TOKEN_RE.findall((query or "").casefold()) if token not in WEAK_QUERY_MARKERS}
        summary_tokens = set(QUERY_TOKEN_RE.findall((summary or "").casefold()))
        if not query_tokens or not summary_tokens:
            return 0
        overlap = len(query_tokens & summary_tokens)
        return min(100, overlap * 22)

    async def _score_summary_with_model(
        self,
        query: str,
        summary: str,
        message_kind: str,
    ) -> int:
        prompt = (
            "You score how well a Telegram message matches a search request.\n"
            "Return only one integer from 0 to 100.\n\n"
            f"Search request: {query}\n"
            f"Message type: {message_kind}\n"
            f"Candidate summary:\n{summary}\n\n"
            "Score:"
        )
        try:
            result = await self._groq_client.generate_reply(
                prompt,
                user_query=query,
                style_instruction="",
                reply_mode="command",
                response_mode="human_like_owner",
            )
        except Exception:
            return 0
        match = re.search(r"(-?\d{1,3})", result.text or "")
        if not match:
            return 0
        try:
            return max(0, min(100, int(match.group(1))))
        except ValueError:
            return 0

    async def _format_found_message(self, message) -> str:
        timestamp = self._message_datetime(message).astimezone(timezone.utc).strftime("%H:%M")
        author = self._message_author_label(message)
        kind = self._message_type_label(message)
        summary = await self._build_message_search_summary(
            message,
            ActionRequest(
                action="find",
                source_reference=getattr(getattr(message, "chat", None), "id", None) or 0,
                target_reference=None,
                query="",
                message_limit=1,
                within_hours=None,
            ),
        )
        compact = " ".join((summary or "").split())[:220]
        return f"[{timestamp}] {author} [{kind}] {compact or 'message'}"

    def _message_author_label(self, message) -> str:
        sender_chat = getattr(message, "sender_chat", None)
        if sender_chat is not None:
            return getattr(sender_chat, "title", None) or "Chat"
        user = getattr(message, "from_user", None)
        if user is None:
            return "Unknown"
        username = getattr(user, "username", None)
        if username:
            return f"@{username}"
        full_name = " ".join(
            part
            for part in [getattr(user, "first_name", None), getattr(user, "last_name", None)]
            if part
        ).strip()
        return full_name or f"user_{getattr(user, 'id', 'unknown')}"

    def _message_type_label(self, message) -> str:
        if getattr(message, "sticker", None) is not None:
            return "sticker"
        if self._message_is_voice_like(message):
            return "voice"
        if self._message_is_photo_like(message):
            return "photo"
        return "message"

    def _build_not_found_text(self, request: ActionRequest, chat_label: str, language: str) -> str:
        kind_map_en = {
            "photo": "photo",
            "voice": "voice message",
            "sticker": "sticker",
            "text": "message",
            "photo_or_voice": "photo or voice message",
            "any": "message",
        }
        kind_map_ru = {
            "photo": "\u0444\u043e\u0442\u043e",
            "voice": "\u0433\u043e\u043b\u043e\u0441\u043e\u0432\u043e\u0435",
            "sticker": "\u0441\u0442\u0438\u043a\u0435\u0440",
            "text": "\u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435",
            "photo_or_voice": "\u0444\u043e\u0442\u043e \u0438\u043b\u0438 \u0433\u043e\u043b\u043e\u0441\u043e\u0432\u043e\u0435",
            "any": "\u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435",
        }
        if language == "en":
            label = kind_map_en.get(request.message_kind, "message")
            if request.query:
                return f'I could not find a {label} in {chat_label} that matches "{request.query}".'
            if request.clock_time:
                return f"I could not find a {label} in {chat_label} near {request.clock_time}."
            return f"I could not find a matching {label} in {chat_label}."
        label = kind_map_ru.get(request.message_kind, "\u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435")
        if request.query:
            return f'\u042f \u043d\u0435 \u043d\u0430\u0448\u0451\u043b {label} \u0432 {chat_label}, \u043a\u043e\u0442\u043e\u0440\u043e\u0435 \u043f\u043e\u0434\u0445\u043e\u0434\u0438\u0442 \u043f\u043e \u0437\u0430\u043f\u0440\u043e\u0441\u0443 "{request.query}".'
        if request.clock_time:
            return f'\u042f \u043d\u0435 \u043d\u0430\u0448\u0451\u043b {label} \u0432 {chat_label} \u043e\u043a\u043e\u043b\u043e {request.clock_time}.'
        return f'\u042f \u043d\u0435 \u043d\u0430\u0448\u0451\u043b \u043f\u043e\u0434\u0445\u043e\u0434\u044f\u0449\u0435\u0435 {label} \u0432 {chat_label}.'

    async def _execute_forward_last(
        self,
        request: ActionRequest,
        source_chat: ResolvedChat,
        target_chat: ResolvedChat,
        *,
        current_chat_id: int,
        excluded_message_ids: set[int] | None,
        language: str,
        response_mode: str = "ai_prefixed",
    ) -> str:
        matches = await self._select_matching_messages(
            request,
            source_chat=source_chat,
            current_chat_id=current_chat_id,
            excluded_message_ids=excluded_message_ids,
        )
        if matches:
            if request.prefix_text:
                await self._client.send_message(
                    target_chat.lookup,
                    request.prefix_text,
                    disable_web_page_preview=True,
                )
            for message in reversed(matches):
                await self._client.copy_message(
                    chat_id=target_chat.lookup,
                    from_chat_id=source_chat.lookup,
                    message_id=message.id,
                )
            return sanitize_ai_output(
                tr("sent_result_to_chat", language, chat=target_chat.label),
                user_query=request.query or source_chat.label,
                response_mode=response_mode,
            )
        return sanitize_ai_output(
            self._build_not_found_text(request, source_chat.label, language),
            user_query=request.query or source_chat.label,
            response_mode=response_mode,
        )

    def _should_skip_forward_candidate(
        self,
        message,
        *,
        source_chat_id: int,
        current_chat_id: int,
        excluded_message_ids: set[int] | None,
    ) -> bool:
        if (
            source_chat_id == current_chat_id
            and excluded_message_ids
            and message.id in excluded_message_ids
        ):
            return True
        text = (
            getattr(message, "text", None) or getattr(message, "caption", None) or ""
        ).strip()
        if not text:
            return False
        if TRIGGER_PREFIX_RE.match(text):
            return True
        if text == (self._config.placeholder_text or "").strip():
            return True
        if text == (self._config.response_sent_text or "").strip():
            return True
        return False

    async def _execute_find(
        self,
        request: ActionRequest,
        source_chat: ResolvedChat,
        language: str,
        response_mode: str = "ai_prefixed",
    ) -> str:
        matches = await self._select_matching_messages(
            request,
            source_chat=source_chat,
            current_chat_id=source_chat.chat_id,
            excluded_message_ids=None,
        )
        if not matches:
            return sanitize_ai_output(
                self._build_not_found_text(request, source_chat.label, language),
                response_mode=response_mode,
            )

        lines = [tr("found_in_chat", language, chat=source_chat.label)]
        for message in matches[: min(8, max(1, request.message_limit))]:
            lines.append(f"- {await self._format_found_message(message)}")
        return sanitize_ai_output("\n".join(lines), response_mode=response_mode)

    async def _execute_find_related_channel_link(
        self,
        request: ActionRequest,
        *,
        prompt: str,
        current_chat_id: int,
        language: str,
        response_mode: str = "ai_prefixed",
    ) -> str:
        try:
            current_chat = await self._client.get_chat(current_chat_id)
        except Exception:
            return sanitize_ai_output(
                tr("open_chat_error", language, reference=current_chat_id),
                user_query=request.query or str(current_chat_id),
                response_mode=response_mode,
            )

        candidate = await self._find_related_channel_for_chat(current_chat)
        if candidate is None and self._wants_global_telegram_search(prompt):
            candidate = await self._find_related_channel_via_global_search(current_chat)
        if candidate is None:
            candidate = await self._find_related_channel_via_global_search(current_chat)
        if candidate is None:
            if language == "en":
                text = "I couldn't find a channel in this account whose name clearly matches this chat."
            elif language == "it":
                text = "Non sono riuscito a trovare in questo account un canale il cui nome corrisponda chiaramente a questa chat."
            elif language == "es":
                text = "No pude encontrar en esta cuenta un canal cuyo nombre coincida claramente con este chat."
            elif language == "fr":
                text = "Je n'ai pas trouve dans ce compte de canal dont le nom corresponde clairement a ce chat."
            elif language == "de":
                text = "Ich konnte in diesem Account keinen Kanal finden, dessen Name eindeutig zu diesem Chat passt."
            else:
                text = "Ð¯ Ð½Ðµ ÑÐ¼Ð¾Ð³ Ð½Ð°Ð¹Ñ‚Ð¸ Ð² ÑÑ‚Ð¾Ð¼ Ð°ÐºÐºÐ°ÑƒÐ½Ñ‚Ðµ ÐºÐ°Ð½Ð°Ð», Ñ‡ÑŒÑ‘ Ð¸Ð¼Ñ ÑÐ²Ð½Ð¾ ÑÐ²ÑÐ·Ð°Ð½Ð¾ Ñ Ð½Ð°Ð·Ð²Ð°Ð½Ð¸ÐµÐ¼ ÑÑ‚Ð¾Ð³Ð¾ Ñ‡Ð°Ñ‚Ð°."
            return sanitize_ai_output(
                text, user_query=request.query or "", response_mode=response_mode
            )

        username = getattr(candidate, "username", None)
        title = (
            getattr(candidate, "title", None)
            or " ".join(
                part
                for part in [
                    getattr(candidate, "first_name", None),
                    getattr(candidate, "last_name", None),
                ]
                if part
            ).strip()
            or "channel"
        )
        if username:
            text = f"{title}: https://t.me/{username}"
            self._remember_recent_reference(current_chat_id, f"@{username}")
        else:
            if language == "en":
                text = f'I found the matching channel "{title}", but it has no public @username link.'
            elif language == "it":
                text = f'Ho trovato il canale corrispondente "{title}", ma non ha un link pubblico con @username.'
            elif language == "es":
                text = f'Encontre el canal correspondiente "{title}", pero no tiene un enlace publico con @username.'
            elif language == "fr":
                text = f"J'ai trouve le canal correspondant \"{title}\", mais il n'a pas de lien public avec @username."
            elif language == "de":
                text = f'Ich habe den passenden Kanal "{title}" gefunden, aber er hat keinen oeffentlichen @username-Link.'
            else:
                text = f'ÐÐ°ÑˆÑ‘Ð» Ð¿Ð¾Ð´Ñ…Ð¾Ð´ÑÑ‰Ð¸Ð¹ ÐºÐ°Ð½Ð°Ð» "{title}", Ð½Ð¾ Ñƒ Ð½ÐµÐ³Ð¾ Ð½ÐµÑ‚ Ð¿ÑƒÐ±Ð»Ð¸Ñ‡Ð½Ð¾Ð¹ ÑÑÑ‹Ð»ÐºÐ¸ Ñ @username.'
        if not username:
            candidate_id = getattr(candidate, "id", None)
            if candidate_id is not None:
                self._remember_recent_reference(current_chat_id, candidate_id)
        return sanitize_ai_output(
            text, user_query=request.query or title, response_mode=response_mode
        )

    async def _execute_chat_documentation(
        self,
        source_chat: ResolvedChat,
        *,
        language: str,
        response_mode: str = "ai_prefixed",
    ) -> str:
        try:
            chat = await self._client.get_chat(source_chat.lookup)
        except Exception:
            return sanitize_ai_output(
                tr("open_chat_error", language, reference=source_chat.label),
                user_query=source_chat.label,
                response_mode=response_mode,
            )

        title = (
            getattr(chat, "title", None)
            or " ".join(
                part
                for part in [
                    getattr(chat, "first_name", None),
                    getattr(chat, "last_name", None),
                ]
                if part
            ).strip()
            or source_chat.label
        )
        username = getattr(chat, "username", None)
        description = (
            getattr(chat, "description", None)
            or getattr(chat, "bio", None)
            or getattr(chat, "about", None)
            or ""
        )
        members_count = getattr(chat, "members_count", None)
        chat_type = str(getattr(chat, "type", "")).split(".")[-1].lower() or "chat"

        last_post_text = ""
        async for message in self._client.get_chat_history(source_chat.lookup, limit=5):
            text = (
                getattr(message, "text", None)
                or getattr(message, "caption", None)
                or ""
            ).strip()
            if not text:
                continue
            last_post_text = " ".join(text.split())[:500]
            break

        lines: list[str] = []
        if language == "en":
            lines.append(f"Channel documentation: {title}")
            lines.append(f"Type: {chat_type}")
            if username:
                lines.append(f"Link: https://t.me/{username}")
            if members_count:
                lines.append(f"Members: {members_count}")
            if description:
                lines.append(f"Description: {description}")
            if last_post_text:
                lines.append(f"Latest post: {last_post_text}")
        else:
            lines.append(f"Ð”Ð¾ÐºÑƒÐ¼ÐµÐ½Ñ‚Ð°Ñ†Ð¸Ñ Ð¿Ð¾ ÐºÐ°Ð½Ð°Ð»Ñƒ: {title}")
            lines.append(f"Ð¢Ð¸Ð¿: {chat_type}")
            if username:
                lines.append(f"Ð¡ÑÑ‹Ð»ÐºÐ°: https://t.me/{username}")
            if members_count:
                lines.append(f"Ð£Ñ‡Ð°ÑÑ‚Ð½Ð¸ÐºÐ¸: {members_count}")
            if description:
                lines.append(f"ÐžÐ¿Ð¸ÑÐ°Ð½Ð¸Ðµ: {description}")
            if last_post_text:
                lines.append(f"ÐŸÐ¾ÑÐ»ÐµÐ´Ð½Ð¸Ð¹ Ð¿Ð¾ÑÑ‚: {last_post_text}")
        return sanitize_ai_output(
            "\n".join(lines), user_query=title, response_mode=response_mode
        )

    async def _execute_generative(
        self,
        request: ActionRequest,
        source_chat: ResolvedChat,
        style_instruction: str,
        user_query: str,
        response_mode: str = "ai_prefixed",
        response_style_mode: str = "NORMAL",
    ) -> str:
        context_lines = await self._context_reader.collect_chat_context(
            source_chat.lookup,
            limit=request.message_limit,
            within_hours=request.within_hours,
            scan_limit=self._config.default_context_scan_limit,
        )
        if not context_lines:
            return sanitize_ai_output(
                tr(
                    "chat_no_context",
                    detect_language(user_query),
                    chat=source_chat.label,
                ),
                response_mode=response_mode,
            )

        context_block = self._context_reader.format_context(context_lines)
        prompt = self._build_prompt(request, source_chat, context_block)
        result = await self._groq_client.generate_reply(
            prompt,
            user_query=user_query,
            style_instruction=style_instruction,
            reply_mode="command",
            response_mode=response_mode,
            response_style_mode=response_style_mode,
        )
        return result.text

    def _build_prompt(
        self, request: ActionRequest, source_chat: ResolvedChat, context_block: str
    ) -> str:
        if request.action == "summarize":
            instruction = (
                "Summarize the recent chat discussion in the same language as the owner's request. "
                "Mention main topics, key points, and participants only if it helps. "
                "Keep it concise and structured."
            )
        elif request.action == "extract":
            instruction = (
                "Extract only the information requested by the owner from the chat context below. "
                "Return a concise answer in the same language as the owner's request."
            )
        else:
            instruction = (
                "Rewrite the relevant content from the chat context below according to the owner's request. "
                "Return one clean final answer in the same language as the owner's request."
            )

        request_line = request.query or "Ð³Ð»Ð°Ð²Ð½Ð¾Ðµ Ð¸ ÑÑƒÑ‚ÑŒ Ð´Ð¸ÑÐºÑƒÑÑÐ¸Ð¸"
        prefix_rule = (
            f'\nAdd this exact text at the very beginning of the final answer: "{request.prefix_text}".\n'
            if request.prefix_text
            else "\n"
        )
        return (
            f"{instruction}\n\n"
            f"Source chat: {source_chat.label}\n"
            f"ProjectOwner request: {request_line}\n\n"
            f"{prefix_rule}"
            "Recent chat context:\n"
            f"{context_block}"
        )

    async def _resolve_chat(self, reference: str | int, language: str) -> ResolvedChat:
        lookup = self._normalize_chat_lookup(reference)
        if lookup is None:
            raise ValueError(tr("parse_chat_error", language))

        try:
            chat = await self._client.get_chat(lookup)
        except Exception as exc:
            if (
                isinstance(lookup, str)
                and not lookup.startswith("@")
                and lookup != "me"
            ):
                dialog_chat = await self._find_dialog_chat(lookup)
                if dialog_chat is None:
                    raise ValueError(
                        tr("open_chat_error", language, reference=reference)
                    ) from exc
                chat = dialog_chat
                lookup = chat.id
            else:
                raise ValueError(
                    tr("open_chat_error", language, reference=reference)
                ) from exc

        title = (
            getattr(chat, "title", None)
            or " ".join(
                part
                for part in [
                    getattr(chat, "first_name", None),
                    getattr(chat, "last_name", None),
                ]
                if part
            ).strip()
        )
        username = getattr(chat, "username", None)
        if lookup == "me":
            label = tr("saved_messages_label", language)
        elif username:
            label = f"@{username}"
        elif title:
            label = title
        else:
            label = f"chat_id {chat.id}"

        return ResolvedChat(lookup=lookup, chat_id=chat.id, label=label)

    def _normalize_chat_lookup(self, reference: str | int) -> str | int | None:
        if isinstance(reference, int):
            return reference

        cleaned = str(reference).strip().strip(",;")
        if not cleaned:
            return None
        if (cleaned.startswith('"') and cleaned.endswith('"')) or (
            cleaned.startswith("'") and cleaned.endswith("'")
        ):
            cleaned = cleaned[1:-1].strip()
            if not cleaned:
                return None

        owner_aliases = {
            str(alias).strip().lstrip("@").casefold()
            for alias in (self._config.owner_reference_aliases or [])
            if str(alias).strip()
        }
        if cleaned.casefold().lstrip("@") in owner_aliases:
            return "me"

        lowered = cleaned.casefold()
        if lowered in FAVORITES_ALIASES:
            return "me"
        if lowered.startswith("Ð¸Ð·Ð±Ñ€Ð°Ð½Ð½") or lowered.startswith("saved"):
            return "me"
        if re.fullmatch(r"-?\d+", cleaned):
            return int(cleaned)
        if cleaned.startswith("@"):
            username = cleaned[1:]
            return cleaned if USERNAME_RE.fullmatch(username) else None

        link_match = PUBLIC_LINK_RE.match(cleaned)
        if link_match:
            path = link_match.group("path").split("?", 1)[0].strip("/")
            parts = [part for part in path.split("/") if part]
            if not parts:
                return None
            if parts[0] == "c" and len(parts) >= 2 and parts[1].isdigit():
                return int(f"-100{parts[1]}")
            if parts[0] == "joinchat" or parts[0].startswith("+"):
                return cleaned
            return f"@{parts[0]}"

        if USERNAME_RE.fullmatch(cleaned):
            return f"@{cleaned}"
        return cleaned if len(cleaned) >= 2 else None

    async def _find_dialog_chat(self, query: str):
        normalized_query = self._normalize_dialog_query(query)
        if not normalized_query:
            return None

        exact_match = None
        partial_match = None
        async for dialog in self._client.get_dialogs(limit=300):
            chat = getattr(dialog, "chat", None)
            if chat is None:
                continue
            labels = self._dialog_labels(chat)
            if not labels:
                continue
            if any(label == normalized_query for label in labels):
                exact_match = chat
                break
            if partial_match is None and any(
                normalized_query in label for label in labels
            ):
                partial_match = chat
        return exact_match or partial_match

    def _dialog_labels(self, chat) -> set[str]:
        labels: set[str] = set()
        title = getattr(chat, "title", None)
        if title:
            labels.add(self._normalize_dialog_query(title))
        username = getattr(chat, "username", None)
        if username:
            labels.add(self._normalize_dialog_query(username))
            labels.add(self._normalize_dialog_query(f"@{username}"))
        first_name = getattr(chat, "first_name", None)
        last_name = getattr(chat, "last_name", None)
        full_name = " ".join(part for part in [first_name, last_name] if part).strip()
        if full_name:
            labels.add(self._normalize_dialog_query(full_name))
        return {label for label in labels if label}

    async def _find_related_channel_for_chat(self, current_chat):
        current_id = getattr(current_chat, "id", None)
        query_tokens = self._related_name_tokens(current_chat)
        if not query_tokens:
            return None

        best_chat = None
        best_score = 0
        async for dialog in self._client.get_dialogs(limit=300):
            chat = getattr(dialog, "chat", None)
            if chat is None:
                continue
            if getattr(chat, "id", None) == current_id:
                continue
            if getattr(chat, "type", None) != enums.ChatType.CHANNEL:
                continue
            score = self._score_related_channel_candidate(
                current_chat, chat, query_tokens
            )
            if score > best_score:
                best_score = score
                best_chat = chat
        return best_chat if best_score >= 3 else None

    async def _find_related_channel_via_global_search(self, current_chat):
        query_tokens = sorted(
            self._related_name_tokens(current_chat), key=len, reverse=True
        )
        if not query_tokens:
            return None

        current_id = getattr(current_chat, "id", None)
        best_chat = None
        best_score = 0
        seen_chat_ids: set[int] = set()

        for query in query_tokens[:4]:
            try:
                async for message in self._client.search_global(
                    query=query,
                    filter=enums.MessagesFilter.EMPTY,
                    limit=30,
                ):
                    chat = getattr(message, "chat", None)
                    if chat is None:
                        continue
                    chat_id = getattr(chat, "id", None)
                    if (
                        chat_id is None
                        or chat_id == current_id
                        or chat_id in seen_chat_ids
                    ):
                        continue
                    seen_chat_ids.add(chat_id)
                    if getattr(chat, "type", None) != enums.ChatType.CHANNEL:
                        continue
                    score = self._score_related_channel_candidate(
                        current_chat, chat, set(query_tokens)
                    )
                    if score > best_score:
                        best_score = score
                        best_chat = chat
            except Exception:
                continue

        return best_chat if best_score >= 3 else None

    def _related_name_tokens(self, chat) -> set[str]:
        tokens: set[str] = set()
        for label in self._dialog_labels(chat):
            for token in re.findall(r"[a-z0-9Ð€-Ó¿]{3,}", label, flags=re.IGNORECASE):
                cleaned = token.casefold().lstrip("@")
                if cleaned in {"chat", "channel", "group", "telegram"}:
                    continue
                tokens.add(cleaned)
        return tokens

    def _score_related_channel_candidate(
        self, current_chat, candidate_chat, query_tokens: set[str]
    ) -> int:
        candidate_labels = self._dialog_labels(candidate_chat)
        if not candidate_labels:
            return 0

        current_title = self._normalize_dialog_query(
            getattr(current_chat, "title", None)
        )
        best_score = 0
        for label in candidate_labels:
            label_tokens = {
                token.casefold().lstrip("@")
                for token in re.findall(r"[a-z0-9Ð€-Ó¿]{3,}", label, flags=re.IGNORECASE)
            }
            overlap = len(query_tokens & label_tokens)
            score = overlap * 2
            if current_title and current_title == label:
                score = max(score, 5)
            elif current_title and current_title in label:
                score = max(score, 4)
            username = getattr(candidate_chat, "username", None)
            if username and any(token in username.casefold() for token in query_tokens):
                score += 1
            best_score = max(best_score, score)
        return best_score

    def _normalize_dialog_query(self, value: str | None) -> str:
        cleaned = " ".join(str(value or "").strip().split()).casefold()
        cleaned = cleaned.lstrip("@")
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        return cleaned

    def _wants_global_telegram_search(self, prompt: str) -> bool:
        lowered = " ".join((prompt or "").casefold().split())
        return any(
            marker in lowered
            for marker in (
                "Ð¾Ð±Ñ‰ÐµÐ¼ Ð¿Ð¾Ð¸ÑÐºÐµ",
                "Ð¾Ð±Ñ‰Ð¸Ð¹ Ð¿Ð¾Ð¸ÑÐº",
                "Ð¿Ð¾Ð¸ÑÐºÐµ Ñ‚Ð³",
                "Ð¿Ð¾Ð¸ÑÐº Ñ‚Ð³",
                "telegram search",
                "global search",
                "search telegram",
            )
        )

    async def _execute_chat_documentation(
        self,
        source_chat: ResolvedChat,
        *,
        language: str,
        response_mode: str = "ai_prefixed",
    ) -> str:
        try:
            chat = await self._client.get_chat(source_chat.lookup)
        except Exception:
            return sanitize_ai_output(
                tr("open_chat_error", language, reference=source_chat.label),
                user_query=source_chat.label,
                response_mode=response_mode,
            )

        title = (
            getattr(chat, "title", None)
            or " ".join(
                part
                for part in [
                    getattr(chat, "first_name", None),
                    getattr(chat, "last_name", None),
                ]
                if part
            ).strip()
            or source_chat.label
        )
        username = getattr(chat, "username", None)
        description = (
            getattr(chat, "description", None)
            or getattr(chat, "bio", None)
            or getattr(chat, "about", None)
            or ""
        )
        members_count = getattr(chat, "members_count", None)
        chat_id = getattr(chat, "id", None)
        chat_type = str(getattr(chat, "type", "")).split(".")[-1].lower() or "chat"
        is_user_like = chat_type in {"private", "bot"}
        linked_telegram = await self._extract_linked_telegram_reference(
            description, username=username
        )
        last_text = await self._find_recent_documentation_text(
            source_chat.lookup, chat_type=chat_type
        )

        lines: list[str] = []
        entity_label = (
            "User profile"
            if language == "en" and is_user_like
            else "Channel documentation"
            if language == "en"
            else "ÐŸÑ€Ð¾Ñ„Ð¸Ð»ÑŒ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ"
            if is_user_like
            else "Ð”Ð¾ÐºÑƒÐ¼ÐµÐ½Ñ‚Ð°Ñ†Ð¸Ñ"
        )
        lines.append(f"{entity_label}: {title}")
        if chat_id is not None:
            lines.append(f"{'ID' if language == 'en' else 'ÐÐ¹Ð´Ð¸'}: {chat_id}")
        lines.append(f"{'Type' if language == 'en' else 'Ð¢Ð¸Ð¿'}: {chat_type}")
        if username:
            lines.append(
                f"{'Username' if language == 'en' else 'Ð®Ð·ÐµÑ€Ð½ÐµÐ¹Ð¼'}: @{username}"
            )
            lines.append(
                f"{'Link' if language == 'en' else 'Ð¡ÑÑ‹Ð»ÐºÐ°'}: https://t.me/{username}"
            )
        if members_count and not is_user_like:
            lines.append(
                f"{'Members' if language == 'en' else 'Ð£Ñ‡Ð°ÑÑ‚Ð½Ð¸ÐºÐ¸'}: {members_count}"
            )
        if description:
            description_label = (
                "Bio"
                if language == "en" and is_user_like
                else "Description"
                if language == "en"
                else "Ð‘Ð¸Ð¾"
                if is_user_like
                else "ÐžÐ¿Ð¸ÑÐ°Ð½Ð¸Ðµ"
            )
            lines.append(f"{description_label}: {description}")
        if linked_telegram is not None:
            link_title = (
                linked_telegram.get("title")
                or linked_telegram.get("username")
                or linked_telegram.get("reference")
            )
            link_username = linked_telegram.get("username")
            link_id = linked_telegram.get("id")
            link_type = linked_telegram.get("type")
            if language == "en":
                lines.append(f"Linked Telegram: {link_title}")
                if link_id is not None:
                    lines.append(f"Linked Telegram ID: {link_id}")
                if link_type:
                    lines.append(f"Linked Telegram type: {link_type}")
                if link_username:
                    lines.append(f"Linked Telegram link: https://t.me/{link_username}")
            else:
                lines.append(f"Ð¡Ð²ÑÐ·Ð°Ð½Ð½Ñ‹Ð¹ Telegram: {link_title}")
                if link_id is not None:
                    lines.append(f"ÐÐ¹Ð´Ð¸ ÑÐ²ÑÐ·Ð°Ð½Ð½Ð¾Ð³Ð¾ Telegram: {link_id}")
                if link_type:
                    lines.append(f"Ð¢Ð¸Ð¿ ÑÐ²ÑÐ·Ð°Ð½Ð½Ð¾Ð³Ð¾ Telegram: {link_type}")
                if link_username:
                    lines.append(
                        f"Ð¡ÑÑ‹Ð»ÐºÐ° Ð½Ð° ÑÐ²ÑÐ·Ð°Ð½Ð½Ñ‹Ð¹ Telegram: https://t.me/{link_username}"
                    )
        if last_text:
            if language == "en":
                last_label = (
                    "Latest post"
                    if chat_type == "channel"
                    else "Latest message in dialog"
                    if is_user_like
                    else "Latest message"
                )
            else:
                last_label = (
                    "ÐŸÐ¾ÑÐ»ÐµÐ´Ð½Ð¸Ð¹ Ð¿Ð¾ÑÑ‚"
                    if chat_type == "channel"
                    else "ÐŸÐ¾ÑÐ»ÐµÐ´Ð½ÐµÐµ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ Ð² Ð´Ð¸Ð°Ð»Ð¾Ð³Ðµ"
                    if is_user_like
                    else "ÐŸÐ¾ÑÐ»ÐµÐ´Ð½ÐµÐµ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ"
                )
            lines.append(f"{last_label}: {last_text}")
        return sanitize_ai_output(
            "\n".join(lines), user_query=title, response_mode=response_mode
        )

    async def _find_recent_documentation_text(
        self, chat_lookup: str | int, *, chat_type: str
    ) -> str:
        async for message in self._client.get_chat_history(chat_lookup, limit=12):
            text = (
                getattr(message, "text", None)
                or getattr(message, "caption", None)
                or ""
            ).strip()
            if not text:
                continue
            if TRIGGER_PREFIX_RE.match(text):
                continue
            if text == (self._config.placeholder_text or "").strip():
                continue
            if text == (self._config.response_sent_text or "").strip():
                continue
            if chat_type in {"private", "bot"}:
                author = getattr(message, "from_user", None)
                if getattr(author, "id", None) == self._config.owner_user_id:
                    continue
            clean = strip_ai_prefix(text).strip()
            if clean:
                return " ".join(clean.split())[:500]
        return ""

    async def _extract_linked_telegram_reference(
        self, text: str, *, username: str | None = None
    ) -> dict[str, object] | None:
        source = (text or "").strip()
        if not source:
            return None
        candidates: list[str] = []
        for match in re.finditer(r"(?iu)@([A-Za-z][A-Za-z0-9_]{4,31})", source):
            value = match.group(1).strip()
            if value and value.casefold() != (username or "").casefold():
                candidates.append(f"@{value}")
        for match in re.finditer(
            r"(?iu)https?://t\\.me/([A-Za-z][A-Za-z0-9_]{4,31})", source
        ):
            value = match.group(1).strip()
            if value and value.casefold() != (username or "").casefold():
                candidates.append(f"@{value}")
        seen: set[str] = set()
        for candidate in candidates:
            lowered = candidate.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            try:
                linked_chat = await self._client.get_chat(candidate)
            except Exception:
                continue
            linked_type = (
                str(getattr(linked_chat, "type", "")).split(".")[-1].lower() or "chat"
            )
            linked_username = getattr(linked_chat, "username", None)
            linked_title = (
                getattr(linked_chat, "title", None)
                or " ".join(
                    part
                    for part in [
                        getattr(linked_chat, "first_name", None),
                        getattr(linked_chat, "last_name", None),
                    ]
                    if part
                ).strip()
                or candidate
            )
            return {
                "reference": candidate,
                "id": getattr(linked_chat, "id", None),
                "type": linked_type,
                "title": linked_title,
                "username": linked_username,
            }
        return None

