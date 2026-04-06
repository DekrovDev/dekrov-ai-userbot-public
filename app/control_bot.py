from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from infra.telegram_compat import prepare_pyrogram_runtime

prepare_pyrogram_runtime()

from pyrogram import Client, enums, filters
from pyrogram.errors import MessageNotModified, RPCError
from pyrogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config.settings import AppConfig
from ai.groq_client import GroqClient
from ai.model_pool import (
    MODEL_BY_NAME,
    MODEL_CATALOG,
    model_stage_label,
    preferred_generator_order,
)
from state.state import PersistentState, RateLimitState, StateStore
from memory.style_profile import StyleProfileStore
from memory.user_memory import CloseContactPatch, SpecialTargetPatch, UserMemoryStore
from memory.entity_memory import EntityMemoryStore
from memory.owner_directives import OwnerDirectiveStore
from infra.health import get_health_checker


LOGGER = logging.getLogger("assistant.control")
CHAT_TOKEN_RE = re.compile(r"[\s,]+")
PUBLIC_LINK_RE = re.compile(
    r"^(?:https?://)?(?:t\.me|telegram\.me)/(?P<path>.+)$", re.IGNORECASE
)
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
MODEL_ACTIVE_PREFIX = "control_model_active_"
MODEL_JUDGE_PREFIX = "control_model_judge_"
MODEL_TOGGLE_PREFIX = "control_model_toggle_"
SPECIAL_TARGET_PREFIX = "control_special_target_"
SPECIAL_TARGET_TOGGLE_PREFIX = "control_special_toggle_"
SPECIAL_TARGET_PAGE_PREFIX = "control_special_page_"
SPECIAL_TARGET_FLAG_CODES = {
    "enabled": "en",
    "human_like": "hm",
    "bypass_delay": "bd",
    "bypass_probability": "bp",
    "bypass_cooldown": "bc",
    "reply_only_questions": "rq",
    "require_owner_mention_or_context": "om",
    "all_chats": "ac",
    "auto_transcribe": "at",
}
SPECIAL_TARGET_FLAG_NAMES = {
    value: key for key, value in SPECIAL_TARGET_FLAG_CODES.items()
}
REPLY_AUDIENCE_MODES = ["ALL", "FRIENDS", "KNOWN", "STRANGERS", "BUSINESS"]
CLOSE_CONTACT_PREFIX = "control_close_"
CLOSE_CONTACT_PAGE_PREFIX = "control_close_page_"
CLOSE_CONTACT_ROLE_PREFIX = "control_close_role_"
CLOSE_CONTACT_COMMENT_PREFIX = "control_close_comment_"
CLOSE_CONTACT_DELETE_PREFIX = "control_close_delete_"
LIST_PAGE_SIZE = 5

USER_PANEL_PREFIX = "control_user_"
USER_PANEL_PAGE_PREFIX = "control_user_page_"
USER_BLOCK_PREFIX = "control_user_block_"
USER_UNBLOCK_PREFIX = "control_user_unblock_"


@dataclass(slots=True)
class PendingChatInput:
    action: str
    panel_chat_id: int
    panel_message_id: int


@dataclass(slots=True)
class PendingCloseCommentEdit:
    user_id: int
    panel_chat_id: int
    panel_message_id: int


@dataclass(slots=True)
class ResolvedChat:
    chat_id: int
    label: str


class ControlBotService:
    def __init__(
        self,
        config: AppConfig,
        state: StateStore,
        groq_client: GroqClient,
        style_store: StyleProfileStore,
        user_memory_store: UserMemoryStore,
        entity_memory_store: EntityMemoryStore | None = None,
        owner_directives_store: OwnerDirectiveStore | None = None,
    ) -> None:
        self._config = config
        self._state = state
        self._groq_client = groq_client
        self._style_store = style_store
        self._user_memory_store = user_memory_store
        self._entity_memory_store = entity_memory_store
        self._owner_directives_store = owner_directives_store
        self._client = Client(
            name=config.control_bot_session,
            api_id=config.api_id,
            api_hash=config.api_hash,
            bot_token=config.control_bot_token,
            workdir=str(config.base_dir / "data"),
        )
        self._started = False
        self._pending_chat_inputs: dict[int, PendingChatInput] = {}
        self._pending_close_comment_edits: dict[int, PendingCloseCommentEdit] = {}
        self._register_handlers()

    async def start(self) -> None:
        await self._client.start()
        await self._client.set_bot_commands(
            [
                BotCommand("start", "ÐžÑ‚ÐºÑ€Ñ‹Ñ‚ÑŒ Ð¿Ð°Ð½ÐµÐ»ÑŒ ÑƒÐ¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ñ"),
                BotCommand("health", "ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ ÑÑ‚Ð°Ñ‚ÑƒÑ Ð±Ð¾Ñ‚Ð°"),
            ]
        )
        self._started = True
        LOGGER.info("control_bot_started owner_user_id=%s", self._config.owner_user_id)

    async def stop(self) -> None:
        if not self._started:
            return
        self._pending_chat_inputs.clear()
        await self._client.stop()
        self._started = False
        LOGGER.info("control_bot_stopped")

    def _register_handlers(self) -> None:
        @self._client.on_message(filters.command(["start"]))
        async def handle_start(_: Client, message: Message) -> None:
            await self._handle_start(message)

        @self._client.on_message(filters.command(["health"]))
        async def handle_health(_: Client, message: Message) -> None:
            await self._handle_health(message)

        @self._client.on_message(filters.text)
        async def handle_text(_: Client, message: Message) -> None:
            await self._handle_owner_text(message)

        @self._client.on_callback_query()
        async def handle_callback(_: Client, callback_query: CallbackQuery) -> None:
            await self._handle_callback(callback_query)

    async def _handle_start(self, message: Message) -> None:
        if not self._is_owner(message.from_user.id if message.from_user else None):
            return

        self._pending_chat_inputs.pop(message.chat.id, None)
        snapshot = await self._state.get_snapshot()
        await self._upsert_panel_message(
            chat_id=message.chat.id,
            message_id=None,
            text=self._render_main_panel(snapshot),
            reply_markup=self._build_main_markup(snapshot),
        )
        LOGGER.info("control_panel_opened chat_id=%s", message.chat.id)

    async def _handle_health(self, message: Message) -> None:
        """ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚Ð°Ñ‚ÑŒ ÐºÐ¾Ð¼Ð°Ð½Ð´Ñƒ /health.

        Ð’Ð¾Ð·Ð²Ñ€Ð°Ñ‰Ð°ÐµÑ‚ ÑÑ‚Ð°Ñ‚ÑƒÑ Ð±Ð¾Ñ‚Ð° Ñ uptime Ð¸ Ð¿Ñ€Ð¾Ð²ÐµÑ€ÐºÐ°Ð¼Ð¸.
        """
        if not self._is_owner(message.from_user.id if message.from_user else None):
            await message.reply("âŒ ÐÐµÑ‚ Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð°")
            return

        health_checker = get_health_checker()
        status = health_checker.get_status()

        # Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ð´Ð¾Ð¿Ð¾Ð»Ð½Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ñ‹Ðµ Ð¿Ñ€Ð¾Ð²ÐµÑ€ÐºÐ¸
        status.checks["control_bot"] = self._started
        status.checks["owner_verified"] = self._config.owner_user_id > 0

        # Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ð¼ÐµÑ‚Ñ€Ð¸ÐºÐ¸
        status.metrics["models_enabled"] = sum(
            1 for v in (await self._state.get_snapshot()).enabled_models.values() if v
        )

        await message.reply(
            status.to_text(),
            parse_mode=enums.ParseMode.MARKDOWN,
        )
        LOGGER.info("health_check_requested status=%s", status.status)

    async def _handle_owner_text(self, message: Message) -> None:
        if not self._is_owner(message.from_user.id if message.from_user else None):
            return

        text = (message.text or "").strip()
        if not text or text.startswith("/"):
            return

        pending = self._pending_chat_inputs.get(message.chat.id)
        if pending is None:
            return

        LOGGER.info(
            "control_pending_input action=%s chat_id=%s",
            pending.action,
            message.chat.id,
        )
        try:
            should_clear, panel_text = await self._apply_pending_input(
                pending.action, text
            )
        except Exception:
            LOGGER.exception("control_pending_input_failed action=%s", pending.action)
            should_clear = False
            panel_text = self._render_chat_input_prompt(
                pending.action,
                errors=["ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚Ð°Ñ‚ÑŒ Ð²Ð²Ð¾Ð´. ÐŸÐ¾Ð¿Ñ€Ð¾Ð±ÑƒÐ¹ ÐµÑ‰Ñ‘ Ñ€Ð°Ð·."],
            )

        if should_clear:
            self._pending_chat_inputs.pop(message.chat.id, None)
            reply_markup = self._reply_markup_for_pending_action(pending.action)
        else:
            reply_markup = self._build_chat_input_markup()

        panel_chat_id, panel_message_id = await self._upsert_panel_message(
            chat_id=pending.panel_chat_id,
            message_id=pending.panel_message_id,
            text=panel_text,
            reply_markup=reply_markup,
        )

        if not should_clear:
            self._pending_chat_inputs[message.chat.id] = PendingChatInput(
                action=pending.action,
                panel_chat_id=panel_chat_id,
                panel_message_id=panel_message_id,
            )

    async def _handle_callback(self, callback_query: CallbackQuery) -> None:
        if not self._is_owner(
            callback_query.from_user.id if callback_query.from_user else None
        ):
            await callback_query.answer("ÐÐµÑ‚ Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð°", show_alert=True)
            return
        if callback_query.message is None:
            await callback_query.answer()
            return

        data = callback_query.data or ""
        panel_chat_id = callback_query.message.chat.id
        panel_message_id = callback_query.message.id

        if data not in {"control_chat_add", "control_chat_remove"}:
            self._pending_chat_inputs.pop(panel_chat_id, None)

        LOGGER.info("control_callback data=%s", data)

        if data == "control_status":
            snapshot = await self._state.get_snapshot()
            await self._show_main_panel(panel_chat_id, panel_message_id, snapshot)
            await callback_query.answer("ÐŸÐ°Ð½ÐµÐ»ÑŒ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð°")
            return

        if data == "control_refresh":
            refreshed = await self._refresh_models()
            snapshot = await self._state.get_snapshot()
            await self._show_main_panel(panel_chat_id, panel_message_id, snapshot)
            await callback_query.answer(
                "ÐŸÑƒÐ» Ð¼Ð¾Ð´ÐµÐ»ÐµÐ¹ Ð¾Ð±Ð½Ð¾Ð²Ð»Ñ‘Ð½" if refreshed else "ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¾Ð±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ Ð¼Ð¾Ð´ÐµÐ»Ð¸"
            )
            return

        if data == "control_style":
            style_snapshot = await self._style_store.get_snapshot()
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=self._render_style_panel(style_snapshot),
                reply_markup=self._build_back_markup("control_back_main"),
            )
            await callback_query.answer()
            return

        if data == "control_fallback_toggle":
            snapshot = await self._state.get_snapshot()
            updated = await self._state.set_fallback_enabled(
                not snapshot.fallback_enabled
            )
            await self._show_main_panel(panel_chat_id, panel_message_id, updated)
            await callback_query.answer("Ð ÐµÐ·ÐµÑ€Ð² Ð¿ÐµÑ€ÐµÐºÐ»ÑŽÑ‡Ñ‘Ð½")
            return

        if data == "control_ai_mode_toggle":
            snapshot = await self._state.get_snapshot()
            updated = await self._state.set_ai_mode_enabled(
                not snapshot.ai_mode_enabled
            )
            await self._show_main_panel(panel_chat_id, panel_message_id, updated)
            await callback_query.answer("Ð ÐµÐ¶Ð¸Ð¼ AI Ð¿ÐµÑ€ÐµÐºÐ»ÑŽÑ‡Ñ‘Ð½")
            return

        if data == "control_response_style_cycle":
            snapshot = await self._state.get_snapshot()
            updated = await self._state.set_response_style_mode(
                self._next_response_style_mode(snapshot.response_style_mode)
            )
            await self._show_main_panel(panel_chat_id, panel_message_id, updated)
            await callback_query.answer("Ð ÐµÐ¶Ð¸Ð¼ Ð¾Ñ‚Ð²ÐµÑ‚Ð° Ð¿ÐµÑ€ÐµÐºÐ»ÑŽÑ‡Ñ‘Ð½")
            return

        if data == "control_command_toggle":
            snapshot = await self._state.get_snapshot()
            updated = await self._state.set_command_mode_enabled(
                not snapshot.command_mode_enabled
            )
            await self._show_main_panel(panel_chat_id, panel_message_id, updated)
            await callback_query.answer("ÐšÐ¾Ð¼Ð°Ð½Ð´Ð½Ñ‹Ð¹ Ñ€ÐµÐ¶Ð¸Ð¼ Ð¿ÐµÑ€ÐµÐºÐ»ÑŽÑ‡Ñ‘Ð½")
            return

        if data == "control_autoreply_toggle":
            snapshot = await self._state.get_snapshot()
            updated = await self._state.set_auto_reply_enabled(
                not snapshot.auto_reply_enabled
            )
            await self._show_main_panel(panel_chat_id, panel_message_id, updated)
            await callback_query.answer("ÐÐ²Ñ‚Ð¾Ð¾Ñ‚Ð²ÐµÑ‚ Ð¿ÐµÑ€ÐµÐºÐ»ÑŽÑ‡Ñ‘Ð½")
            return

        if data == "control_audience_panel":
            snapshot = await self._state.get_snapshot()
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text="<b>ÐÑƒÐ´Ð¸Ñ‚Ð¾Ñ€Ð¸Ñ Ð¾Ñ‚Ð²ÐµÑ‚Ð¾Ð²</b>\n\nÐ’Ñ‹Ð±ÐµÑ€Ð¸ ÐºÐ¾Ð¼Ñƒ Ð±Ð¾Ñ‚ Ð±ÑƒÐ´ÐµÑ‚ Ð¾Ñ‚Ð²ÐµÑ‡Ð°Ñ‚ÑŒ. ÐÐ°Ð¶Ð¼Ð¸ Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð¿ÐµÑ€ÐµÐºÐ»ÑŽÑ‡Ð¸Ñ‚ÑŒ.",
                reply_markup=self._build_audience_markup(snapshot.reply_audience_flags),
            )
            await callback_query.answer()
            return

        if data.startswith("control_audience_toggle_"):
            category = data[len("control_audience_toggle_") :]
            updated = await self._state.toggle_audience_flag(category)
            flags = updated.reply_audience_flags
            enabled = flags.get(category, True)
            labels = {
                "STRANGERS": "ÐÐµÐ·Ð½Ð°ÐºÐ¾Ð¼Ñ†Ñ‹",
                "KNOWN": "Ð—Ð½Ð°ÐºÐ¾Ð¼Ñ‹Ðµ",
                "FRIENDS": "Ð”Ñ€ÑƒÐ·ÑŒÑ",
                "BUSINESS": "ÐŸÐ¾ Ð´ÐµÐ»Ñƒ",
            }
            label = labels.get(category, category)
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text="<b>ÐÑƒÐ´Ð¸Ñ‚Ð¾Ñ€Ð¸Ñ Ð¾Ñ‚Ð²ÐµÑ‚Ð¾Ð²</b>\n\nÐ’Ñ‹Ð±ÐµÑ€Ð¸ ÐºÐ¾Ð¼Ñƒ Ð±Ð¾Ñ‚ Ð±ÑƒÐ´ÐµÑ‚ Ð¾Ñ‚Ð²ÐµÑ‡Ð°Ñ‚ÑŒ. ÐÐ°Ð¶Ð¼Ð¸ Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð¿ÐµÑ€ÐµÐºÐ»ÑŽÑ‡Ð¸Ñ‚ÑŒ.",
                reply_markup=self._build_audience_markup(flags),
            )
            await callback_query.answer(
                f"{label}: {'Ð¾Ñ‚Ð²ÐµÑ‡Ð°Ñ‚ÑŒ' if enabled else 'Ð¼Ð¾Ð»Ñ‡Ð°Ñ‚ÑŒ'}"
            )
            return

        if data == "control_reply_only_questions_toggle":
            snapshot = await self._state.get_snapshot()
            updated = await self._state.set_reply_only_questions(
                not snapshot.reply_only_questions
            )
            await self._show_main_panel(panel_chat_id, panel_message_id, updated)
            await callback_query.answer("Ð¤Ð¸Ð»ÑŒÑ‚Ñ€ Ð²Ð¾Ð¿Ñ€Ð¾ÑÐ¾Ð² Ð¿ÐµÑ€ÐµÐºÐ»ÑŽÑ‡Ñ‘Ð½")
            return

        if data == "control_owner_context_toggle":
            snapshot = await self._state.get_snapshot()
            updated = await self._state.set_require_owner_mention_or_context(
                not snapshot.require_owner_mention_or_context
            )
            await self._show_main_panel(panel_chat_id, panel_message_id, updated)
            await callback_query.answer("Ð¤Ð¸Ð»ÑŒÑ‚Ñ€ Ð¾Ð±Ñ€Ð°Ñ‰ÐµÐ½Ð¸Ñ Ðº Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ñƒ Ð¿ÐµÑ€ÐµÐºÐ»ÑŽÑ‡Ñ‘Ð½")
            return

        if data == "control_models":
            snapshot = await self._state.get_snapshot()
            await self._show_models_panel(panel_chat_id, panel_message_id, snapshot)
            await callback_query.answer()
            return

        if data == "control_models_select_active":
            snapshot = await self._state.get_snapshot()
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=self._render_model_selection_panel(snapshot, "active"),
                reply_markup=self._build_model_selection_markup(snapshot, "active"),
            )
            await callback_query.answer()
            return

        if data == "control_models_select_judge":
            snapshot = await self._state.get_snapshot()
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=self._render_model_selection_panel(snapshot, "judge"),
                reply_markup=self._build_model_selection_markup(snapshot, "judge"),
            )
            await callback_query.answer()
            return

        if data == "control_models_toggle_panel":
            snapshot = await self._state.get_snapshot()
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=self._render_model_selection_panel(snapshot, "toggle"),
                reply_markup=self._build_model_selection_markup(snapshot, "toggle"),
            )
            await callback_query.answer()
            return

        if data.startswith(MODEL_ACTIVE_PREFIX):
            snapshot = await self._state.get_snapshot()
            model_name = self._model_name_from_callback(
                data, snapshot, MODEL_ACTIVE_PREFIX
            )
            if model_name is None:
                await callback_query.answer("ÐœÐ¾Ð´ÐµÐ»ÑŒ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð°", show_alert=True)
                return
            updated = await self._state.set_active_model(model_name)
            await self._show_models_panel(panel_chat_id, panel_message_id, updated)
            await callback_query.answer("Ð“ÐµÐ½ÐµÑ€Ð°Ñ‚Ð¾Ñ€ Ð¾Ð±Ð½Ð¾Ð²Ð»Ñ‘Ð½")
            return

        if data.startswith(MODEL_JUDGE_PREFIX):
            snapshot = await self._state.get_snapshot()
            model_name = self._model_name_from_callback(
                data, snapshot, MODEL_JUDGE_PREFIX
            )
            if model_name is None:
                await callback_query.answer("ÐœÐ¾Ð´ÐµÐ»ÑŒ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð°", show_alert=True)
                return
            updated = await self._state.set_judge_model(model_name)
            await self._show_models_panel(panel_chat_id, panel_message_id, updated)
            await callback_query.answer("ÐœÐ¾Ð´ÐµÐ»ÑŒ-ÑÑƒÐ´ÑŒÑ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð°")
            return

        if data.startswith(MODEL_TOGGLE_PREFIX):
            snapshot = await self._state.get_snapshot()
            model_name = self._model_name_from_callback(
                data, snapshot, MODEL_TOGGLE_PREFIX
            )
            if model_name is None:
                await callback_query.answer("ÐœÐ¾Ð´ÐµÐ»ÑŒ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð°", show_alert=True)
                return
            updated, changed = await self._state.set_model_enabled(
                model_name,
                not snapshot.enabled_models.get(model_name, True),
            )
            await self._show_models_panel(panel_chat_id, panel_message_id, updated)
            await callback_query.answer(
                "ÐœÐ¾Ð´ÐµÐ»ÑŒ Ð¿ÐµÑ€ÐµÐºÐ»ÑŽÑ‡ÐµÐ½Ð°" if changed else "ÐÐµÐ»ÑŒÐ·Ñ Ð²Ñ‹ÐºÐ»ÑŽÑ‡Ð¸Ñ‚ÑŒ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½ÑŽÑŽ Ð¼Ð¾Ð´ÐµÐ»ÑŒ"
            )
            return

        if data == "control_chat_panel":
            snapshot = await self._state.get_snapshot()
            pending = self._pending_chat_inputs.get(panel_chat_id)
            if pending is not None and pending.action.startswith("special_"):
                text = await self._render_special_targets_panel(page=0)
                reply_markup = await self._build_special_targets_markup(page=0)
            elif pending is not None and pending.action.startswith("close_"):
                text = await self._render_close_contacts_panel(page=0)
                reply_markup = await self._build_close_contacts_markup(page=0)
            else:
                text = self._render_chat_panel(snapshot)
                reply_markup = self._build_chat_panel_markup()
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=text,
                reply_markup=reply_markup,
            )
            await callback_query.answer()
            return

        if data == "control_chat_show":
            snapshot = await self._state.get_snapshot()
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=self._render_allowed_chats_panel(snapshot),
                reply_markup=self._build_chat_panel_markup(),
            )
            await callback_query.answer()
            return

        if data == "control_chat_add":
            self._pending_chat_inputs[panel_chat_id] = PendingChatInput(
                action="add",
                panel_chat_id=panel_chat_id,
                panel_message_id=panel_message_id,
            )
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=self._render_chat_input_prompt("add"),
                reply_markup=self._build_chat_input_markup(),
            )
            await callback_query.answer()
            return

        if data == "control_chat_remove":
            self._pending_chat_inputs[panel_chat_id] = PendingChatInput(
                action="remove",
                panel_chat_id=panel_chat_id,
                panel_message_id=panel_message_id,
            )
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=self._render_chat_input_prompt("remove"),
                reply_markup=self._build_chat_input_markup(),
            )
            await callback_query.answer()
            return

        if data == "control_special_panel":
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=await self._render_special_targets_panel(page=0),
                reply_markup=await self._build_special_targets_markup(page=0),
            )
            await callback_query.answer()
            return

        if data == "control_special_show":
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=await self._render_special_targets_panel(page=0),
                reply_markup=await self._build_special_targets_markup(page=0),
            )
            await callback_query.answer()
            return

        if data == "control_user_panel":
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=await self._render_user_panel(page=0),
                reply_markup=await self._build_user_panel_markup(page=0),
            )
            await callback_query.answer()
            return

        if data.startswith(USER_PANEL_PAGE_PREFIX):
            page = self._page_from_callback(data, USER_PANEL_PAGE_PREFIX)
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=await self._render_user_panel(page=page),
                reply_markup=await self._build_user_panel_markup(page=page),
            )
            await callback_query.answer()
            return

        if (
            data.startswith(USER_PANEL_PREFIX)
            and not data.startswith(USER_BLOCK_PREFIX)
            and not data.startswith(USER_UNBLOCK_PREFIX)
        ):
            user_id_text = data.removeprefix(USER_PANEL_PREFIX)
            if user_id_text.lstrip("-").isdigit():
                user_id = int(user_id_text)
                await self._upsert_panel_message(
                    chat_id=panel_chat_id,
                    message_id=panel_message_id,
                    text=await self._render_user_detail(user_id),
                    reply_markup=self._build_user_detail_markup(user_id),
                )
                await callback_query.answer()
                return

        if data.startswith(USER_BLOCK_PREFIX):
            user_id_text = data.removeprefix(USER_BLOCK_PREFIX)
            if user_id_text.lstrip("-").isdigit():
                user_id = int(user_id_text)
                if self._owner_directives_store is not None:
                    await self._owner_directives_store.set_target_reply_enabled(
                        user_id=user_id, enabled=False
                    )
                await self._upsert_panel_message(
                    chat_id=panel_chat_id,
                    message_id=panel_message_id,
                    text=await self._render_user_detail(user_id),
                    reply_markup=self._build_user_detail_markup(user_id),
                )
                await callback_query.answer("ÐžÑ‚Ð²ÐµÑ‚Ñ‹ Ð¾Ñ‚ÐºÐ»ÑŽÑ‡ÐµÐ½Ñ‹")
                return

        if data.startswith(USER_UNBLOCK_PREFIX):
            user_id_text = data.removeprefix(USER_UNBLOCK_PREFIX)
            if user_id_text.lstrip("-").isdigit():
                user_id = int(user_id_text)
                if self._owner_directives_store is not None:
                    await self._owner_directives_store.set_target_reply_enabled(
                        user_id=user_id, enabled=True
                    )
                await self._upsert_panel_message(
                    chat_id=panel_chat_id,
                    message_id=panel_message_id,
                    text=await self._render_user_detail(user_id),
                    reply_markup=self._build_user_detail_markup(user_id),
                )
                await callback_query.answer("ÐžÑ‚Ð²ÐµÑ‚Ñ‹ Ð²ÐºÐ»ÑŽÑ‡ÐµÐ½Ñ‹")
                return

        if data == "control_close_panel":
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=await self._render_close_contacts_panel(page=0),
                reply_markup=await self._build_close_contacts_markup(page=0),
            )
            await callback_query.answer()
            return

        if data == "control_close_show":
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=await self._render_close_contacts_panel(page=0),
                reply_markup=await self._build_close_contacts_markup(page=0),
            )
            await callback_query.answer()
            return

        if data == "control_close_add":
            self._pending_chat_inputs[panel_chat_id] = PendingChatInput(
                action="close_add",
                panel_chat_id=panel_chat_id,
                panel_message_id=panel_message_id,
            )
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=self._render_close_contact_input_prompt("close_add"),
                reply_markup=self._build_chat_input_markup(),
            )
            await callback_query.answer()
            return

        if data == "control_close_remove":
            self._pending_chat_inputs[panel_chat_id] = PendingChatInput(
                action="close_remove",
                panel_chat_id=panel_chat_id,
                panel_message_id=panel_message_id,
            )
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=self._render_close_contact_input_prompt("close_remove"),
                reply_markup=self._build_chat_input_markup(),
            )
            await callback_query.answer()
            return

        if data == "control_special_add":
            self._pending_chat_inputs[panel_chat_id] = PendingChatInput(
                action="special_add",
                panel_chat_id=panel_chat_id,
                panel_message_id=panel_message_id,
            )
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=self._render_special_target_input_prompt("special_add"),
                reply_markup=self._build_chat_input_markup(),
            )
            await callback_query.answer()
            return

        if data == "control_special_remove":
            self._pending_chat_inputs[panel_chat_id] = PendingChatInput(
                action="special_remove",
                panel_chat_id=panel_chat_id,
                panel_message_id=panel_message_id,
            )
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=self._render_special_target_input_prompt("special_remove"),
                reply_markup=self._build_chat_input_markup(),
            )
            await callback_query.answer()
            return

        if data.startswith(SPECIAL_TARGET_PAGE_PREFIX):
            page = self._page_from_callback(data, SPECIAL_TARGET_PAGE_PREFIX)
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=await self._render_special_targets_panel(page=page),
                reply_markup=await self._build_special_targets_markup(page=page),
            )
            await callback_query.answer()
            return

        if data.startswith(CLOSE_CONTACT_PAGE_PREFIX):
            page = self._page_from_callback(data, CLOSE_CONTACT_PAGE_PREFIX)
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=await self._render_close_contacts_panel(page=page),
                reply_markup=await self._build_close_contacts_markup(page=page),
            )
            await callback_query.answer()
            return

        if data.startswith(SPECIAL_TARGET_PREFIX):
            user_id = self._special_target_user_id_from_callback(
                data, SPECIAL_TARGET_PREFIX
            )
            if user_id is None:
                await callback_query.answer("Ð¦ÐµÐ»ÑŒ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð°", show_alert=True)
                return
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=await self._render_special_target_detail(user_id),
                reply_markup=await self._build_special_target_detail_markup(user_id),
            )
            await callback_query.answer()
            return

        if (
            data.startswith(CLOSE_CONTACT_PREFIX)
            and data[len(CLOSE_CONTACT_PREFIX) :].isdigit()
        ):
            user_id = self._special_target_user_id_from_callback(
                data, CLOSE_CONTACT_PREFIX
            )
            if user_id is None:
                await callback_query.answer("ÐšÐ¾Ð½Ñ‚Ð°ÐºÑ‚ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½", show_alert=True)
                return
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=await self._render_close_contact_detail(user_id),
                reply_markup=await self._build_close_contact_detail_markup(user_id),
            )
            await callback_query.answer()
            return

        if data.startswith(SPECIAL_TARGET_TOGGLE_PREFIX):
            suffix = data.removeprefix(SPECIAL_TARGET_TOGGLE_PREFIX)
            flag_name, _, user_id_text = suffix.rpartition("_")
            if not user_id_text.isdigit():
                await callback_query.answer("Ð¦ÐµÐ»ÑŒ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð°", show_alert=True)
                return
            flag_name = SPECIAL_TARGET_FLAG_NAMES.get(flag_name, flag_name)
            user_id = int(user_id_text)
            target = await self._user_memory_store.get_special_target(user_id)
            if target is None:
                await callback_query.answer("Ð¦ÐµÐ»ÑŒ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð°", show_alert=True)
                return
            patch = SpecialTargetPatch()
            if flag_name == "enabled":
                patch.enabled = not target.enabled
            elif flag_name == "human_like":
                patch.human_like = not target.human_like
            elif flag_name == "bypass_delay":
                patch.bypass_delay = not target.bypass_delay
            elif flag_name == "bypass_probability":
                patch.bypass_probability = not target.bypass_probability
            elif flag_name == "bypass_cooldown":
                patch.bypass_cooldown = not target.bypass_cooldown
            elif flag_name == "reply_only_questions":
                patch.reply_only_questions = not target.reply_only_questions
            elif flag_name == "require_owner_mention_or_context":
                patch.require_owner_mention_or_context = (
                    not target.require_owner_mention_or_context
                )
            elif flag_name == "all_chats":
                patch.allowed_chat_ids = []
            else:
                await callback_query.answer()
                return
            await self._user_memory_store.upsert_special_target(user_id, patch)
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=await self._render_special_target_detail(user_id),
                reply_markup=await self._build_special_target_detail_markup(user_id),
            )
            await callback_query.answer("ÐÐ°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ñ‹")
            return

        if data.startswith("control_special_chats_"):
            user_id_text = data.removeprefix("control_special_chats_")
            if not user_id_text.isdigit():
                await callback_query.answer("Ð¦ÐµÐ»ÑŒ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð°", show_alert=True)
                return
            user_id = int(user_id_text)
            self._pending_chat_inputs[panel_chat_id] = PendingChatInput(
                action=f"special_chats_{user_id}",
                panel_chat_id=panel_chat_id,
                panel_message_id=panel_message_id,
            )
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=self._render_special_target_input_prompt(
                    f"special_chats_{user_id}"
                ),
                reply_markup=self._build_chat_input_markup(),
            )
            await callback_query.answer()
            return

        if data.startswith("control_special_perchat_"):
            user_id_text = data.removeprefix("control_special_perchat_")
            if not user_id_text.isdigit():
                await callback_query.answer("Ð¦ÐµÐ»ÑŒ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð°", show_alert=True)
                return
            user_id = int(user_id_text)
            self._pending_chat_inputs[panel_chat_id] = PendingChatInput(
                action=f"special_perchat_{user_id}",
                panel_chat_id=panel_chat_id,
                panel_message_id=panel_message_id,
            )
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=self._render_perchat_input_prompt(user_id),
                reply_markup=self._build_chat_input_markup(),
            )
            await callback_query.answer()
            return

        if data.startswith(CLOSE_CONTACT_ROLE_PREFIX):
            user_id = self._special_target_user_id_from_callback(
                data, CLOSE_CONTACT_ROLE_PREFIX
            )
            if user_id is None:
                await callback_query.answer("ÐšÐ¾Ð½Ñ‚Ð°ÐºÑ‚ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½", show_alert=True)
                return
            contact = await self._user_memory_store.get_close_contact(user_id)
            if contact is None:
                await callback_query.answer("ÐšÐ¾Ð½Ñ‚Ð°ÐºÑ‚ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½", show_alert=True)
                return
            await self._user_memory_store.upsert_close_contact(
                user_id,
                CloseContactPatch(
                    relation_type=self._next_close_contact_relation(
                        contact.relation_type
                    ),
                    updated_at=self._now_text(),
                ),
            )
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=await self._render_close_contact_detail(user_id),
                reply_markup=await self._build_close_contact_detail_markup(user_id),
            )
            await callback_query.answer("Ð Ð¾Ð»ÑŒ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð°")
            return

        if data.startswith(CLOSE_CONTACT_COMMENT_PREFIX):
            user_id = self._special_target_user_id_from_callback(
                data, CLOSE_CONTACT_COMMENT_PREFIX
            )
            if user_id is None:
                await callback_query.answer("ÐšÐ¾Ð½Ñ‚Ð°ÐºÑ‚ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½", show_alert=True)
                return
            self._pending_chat_inputs[panel_chat_id] = PendingChatInput(
                action=f"close_comment_{user_id}",
                panel_chat_id=panel_chat_id,
                panel_message_id=panel_message_id,
            )
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=self._render_close_contact_input_prompt(
                    f"close_comment_{user_id}"
                ),
                reply_markup=self._build_chat_input_markup(),
            )
            await callback_query.answer()
            return

        if data.startswith(CLOSE_CONTACT_DELETE_PREFIX):
            user_id = self._special_target_user_id_from_callback(
                data, CLOSE_CONTACT_DELETE_PREFIX
            )
            if user_id is None:
                await callback_query.answer("ÐšÐ¾Ð½Ñ‚Ð°ÐºÑ‚ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½", show_alert=True)
                return
            removed = await self._user_memory_store.remove_close_contact(user_id)
            notice = "ÐšÐ¾Ð½Ñ‚Ð°ÐºÑ‚ ÑƒÐ´Ð°Ð»Ñ‘Ð½." if removed else "ÐšÐ¾Ð½Ñ‚Ð°ÐºÑ‚ ÑƒÐ¶Ðµ Ð¾Ñ‚ÑÑƒÑ‚ÑÑ‚Ð²ÑƒÐµÑ‚."
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=await self._render_close_contacts_panel(
                    page=0, extra_notice=notice
                ),
                reply_markup=await self._build_close_contacts_markup(page=0),
            )
            await callback_query.answer()
            return

        if data == "control_cancel_input":
            snapshot = await self._state.get_snapshot()
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=self._render_chat_panel(snapshot),
                reply_markup=self._build_chat_panel_markup(),
            )
            await callback_query.answer("ÐžÑ‚Ð¼ÐµÐ½ÐµÐ½Ð¾")
            return

        if data.startswith("control_back_"):
            target = data.removeprefix("control_back_")
            snapshot = await self._state.get_snapshot()
            if target == "chat":
                text = self._render_chat_panel(snapshot)
                reply_markup = self._build_chat_panel_markup()
            elif target == "special":
                text = await self._render_special_targets_panel(page=0)
                reply_markup = await self._build_special_targets_markup(page=0)
            elif target == "close":
                text = await self._render_close_contacts_panel(page=0)
                reply_markup = await self._build_close_contacts_markup(page=0)
            elif target == "models":
                text = self._render_models_panel(snapshot)
                reply_markup = self._build_models_markup(snapshot)
            else:
                text = self._render_main_panel(snapshot)
                reply_markup = self._build_main_markup(snapshot)
            await self._upsert_panel_message(
                chat_id=panel_chat_id,
                message_id=panel_message_id,
                text=text,
                reply_markup=reply_markup,
            )
            await callback_query.answer()
            return

        await callback_query.answer()

    async def _show_main_panel(
        self, chat_id: int, message_id: int, snapshot: PersistentState
    ) -> None:
        await self._upsert_panel_message(
            chat_id=chat_id,
            message_id=message_id,
            text=self._render_main_panel(snapshot),
            reply_markup=self._build_main_markup(snapshot),
        )

    async def _show_models_panel(
        self, chat_id: int, message_id: int, snapshot: PersistentState
    ) -> None:
        await self._upsert_panel_message(
            chat_id=chat_id,
            message_id=message_id,
            text=self._render_models_panel(snapshot),
            reply_markup=self._build_models_markup(snapshot),
        )

    async def _apply_pending_input(
        self, action: str, raw_text: str
    ) -> tuple[bool, str]:
        if action.startswith("special_"):
            return await self._apply_special_target_input(action, raw_text)
        if action.startswith("close_"):
            return await self._apply_close_contact_input(action, raw_text)
        return await self._apply_chat_input(action, raw_text)

    def _reply_markup_for_pending_action(self, action: str) -> InlineKeyboardMarkup:
        if action.startswith("special_"):
            return InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Ð¡Ð¿Ð¸ÑÐ¾Ðº Ñ†ÐµÐ»ÐµÐ¹", callback_data="control_special_show"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "ÐÐ°Ð·Ð°Ð´", callback_data="control_back_special"
                        )
                    ],
                ]
            )
        if action.startswith("close_"):
            return InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Ð¡Ð¿Ð¸ÑÐ¾Ðº Ð±Ð»Ð¸Ð·ÐºÐ¸Ñ…", callback_data="control_close_show"
                        )
                    ],
                    [InlineKeyboardButton("ÐÐ°Ð·Ð°Ð´", callback_data="control_back_close")],
                ]
            )
        return self._build_chat_panel_markup()

    def _render_pending_input_error(self, action: str) -> str:
        if action.startswith("special_"):
            return self._render_special_target_input_prompt(
                action, errors=["ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚Ð°Ñ‚ÑŒ Ð²Ð²Ð¾Ð´. ÐŸÐ¾Ð¿Ñ€Ð¾Ð±ÑƒÐ¹ ÐµÑ‰Ñ‘ Ñ€Ð°Ð·."]
            )
        if action.startswith("close_"):
            return self._render_close_contact_input_prompt(
                action, errors=["ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚Ð°Ñ‚ÑŒ Ð²Ð²Ð¾Ð´. ÐŸÐ¾Ð¿Ñ€Ð¾Ð±ÑƒÐ¹ ÐµÑ‰Ñ‘ Ñ€Ð°Ð·."]
            )
        return self._render_chat_input_prompt(
            action, errors=["ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚Ð°Ñ‚ÑŒ Ð²Ð²Ð¾Ð´. ÐŸÐ¾Ð¿Ñ€Ð¾Ð±ÑƒÐ¹ ÐµÑ‰Ñ‘ Ñ€Ð°Ð·."]
        )

    async def _apply_chat_input(self, action: str, raw_text: str) -> tuple[bool, str]:
        tokens = self._extract_chat_tokens(raw_text)
        if not tokens:
            return False, self._render_chat_input_prompt(
                action, errors=["ÐÐµ Ð½Ð°ÑˆÑ‘Ð» Ð½Ð¸ Ð¾Ð´Ð½Ð¾Ð¹ ÑÑÑ‹Ð»ÐºÐ¸, username Ð¸Ð»Ð¸ chat_id."]
            )

        snapshot_before = await self._state.get_snapshot()
        resolved, errors = await self._resolve_chat_tokens(tokens)
        if not resolved:
            return False, self._render_chat_input_prompt(
                action, errors=errors or ["ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ñ€Ð°ÑÐ¿Ð¾Ð·Ð½Ð°Ñ‚ÑŒ Ñ‡Ð°Ñ‚Ñ‹."]
            )

        before_allowed = set(snapshot_before.allowed_chat_ids)
        changed: list[ResolvedChat] = []
        skipped: list[ResolvedChat] = []

        if action == "add":
            for item in resolved:
                if item.chat_id in before_allowed:
                    skipped.append(item)
                    continue
                await self._state.allow_chat(item.chat_id)
                before_allowed.add(item.chat_id)
                changed.append(item)
        else:
            for item in resolved:
                if item.chat_id not in before_allowed:
                    skipped.append(item)
                    continue
                await self._state.remove_allowed_chat(item.chat_id)
                before_allowed.remove(item.chat_id)
                changed.append(item)

        snapshot_after = await self._state.get_snapshot()
        return True, self._render_chat_action_result(
            action, changed, skipped, errors, snapshot_after
        )

    async def _apply_special_target_input(
        self, action: str, raw_text: str
    ) -> tuple[bool, str]:
        if action == "special_add":
            token = raw_text.strip()
            if not token:
                return False, self._render_special_target_input_prompt(
                    action, errors=["Ð£ÐºÐ°Ð¶Ð¸ user_id Ð¸Ð»Ð¸ @username."]
                )
            resolved = await self._resolve_user_token(token)
            if resolved is None:
                return False, self._render_special_target_input_prompt(
                    action, errors=["ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð½Ð°Ð¹Ñ‚Ð¸ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ."]
                )
            await self._user_memory_store.upsert_special_target(
                resolved.chat_id,
                SpecialTargetPatch(
                    enabled=True,
                    human_like=True,
                    bypass_delay=True,
                    bypass_probability=True,
                    bypass_cooldown=True,
                    reply_only_questions=False,
                    require_owner_mention_or_context=False,
                    username=resolved.label.lstrip("@"),
                ),
            )
            return True, await self._render_special_target_detail(resolved.chat_id)

        if action == "special_remove":
            token = raw_text.strip()
            if not token:
                return False, self._render_special_target_input_prompt(
                    action, errors=["Ð£ÐºÐ°Ð¶Ð¸ user_id Ð¸Ð»Ð¸ @username."]
                )
            resolved = await self._resolve_user_token(token)
            if resolved is None:
                return False, self._render_special_target_input_prompt(
                    action, errors=["ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð½Ð°Ð¹Ñ‚Ð¸ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ."]
                )
            removed = await self._user_memory_store.remove_special_target(
                resolved.chat_id
            )
            notice = "Ð¦ÐµÐ»ÑŒ ÑƒÐ´Ð°Ð»ÐµÐ½Ð°." if removed else "Ð¢Ð°ÐºÐ¾Ð¹ Ñ†ÐµÐ»Ð¸ Ð½Ðµ Ð±Ñ‹Ð»Ð¾ Ð² ÑÐ¿Ð¸ÑÐºÐµ."
            return True, await self._render_special_targets_panel(
                page=0, extra_notice=notice
            )

        if action.startswith("special_chats_"):
            user_id_text = action.removeprefix("special_chats_")
            if not user_id_text.isdigit():
                return False, self._render_special_target_input_prompt(
                    action, errors=["Ð¦ÐµÐ»ÑŒ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð°."]
                )
            user_id = int(user_id_text)
            target = await self._user_memory_store.get_special_target(user_id)
            if target is None:
                return False, self._render_special_target_input_prompt(
                    action, errors=["Ð¦ÐµÐ»ÑŒ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð°."]
                )
            tokens = self._extract_chat_tokens(raw_text)
            if not tokens:
                await self._user_memory_store.upsert_special_target(
                    user_id, SpecialTargetPatch(allowed_chat_ids=[])
                )
                return True, await self._render_special_target_detail(user_id)
            resolved, errors = await self._resolve_chat_tokens(tokens)
            if not resolved:
                return False, self._render_special_target_input_prompt(
                    action, errors=errors or ["ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ñ€Ð°ÑÐ¿Ð¾Ð·Ð½Ð°Ñ‚ÑŒ Ñ‡Ð°Ñ‚Ñ‹."]
                )
            await self._user_memory_store.upsert_special_target(
                user_id,
                SpecialTargetPatch(
                    allowed_chat_ids=[item.chat_id for item in resolved]
                ),
            )
            return True, await self._render_special_target_detail(user_id)

        if action.startswith("special_perchat_"):
            user_id_text = action.removeprefix("special_perchat_")
            if not user_id_text.isdigit():
                return False, "Ð¦ÐµÐ»ÑŒ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð°."
            user_id = int(user_id_text)
            target = await self._user_memory_store.get_special_target(user_id)
            if target is None:
                return False, "Ð¦ÐµÐ»ÑŒ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð°."
            # Parse input: "chat_id flag=value flag=value"
            # Example: "2260613420 require_owner_mention_or_context=false"
            # Or "clear 2260613420" to remove overrides for that chat
            line = raw_text.strip()
            parts = line.split()
            if not parts:
                return False, self._render_perchat_input_prompt(
                    user_id, errors=["ÐŸÑƒÑÑ‚Ð¾Ð¹ Ð²Ð²Ð¾Ð´."]
                )
            if parts[0].casefold() == "clear" and len(parts) >= 2:
                chat_id_str = parts[1].lstrip("-")
                if not chat_id_str.isdigit():
                    return False, self._render_perchat_input_prompt(
                        user_id, errors=["ÐÐµÐºÐ¾Ñ€Ñ€ÐµÐºÑ‚Ð½Ñ‹Ð¹ chat_id."]
                    )
                new_overrides = dict(target.chat_overrides)
                new_overrides.pop(parts[1], None)
                await self._user_memory_store.upsert_special_target(
                    user_id, SpecialTargetPatch(chat_overrides=new_overrides)
                )
                return True, await self._render_special_target_detail(user_id)
            # Parse "chat_id flag=bool ..."
            chat_id_str = parts[0]
            if not chat_id_str.lstrip("-").isdigit():
                return False, self._render_perchat_input_prompt(
                    user_id, errors=["ÐŸÐµÑ€Ð²Ñ‹Ð¼ ÑƒÐºÐ°Ð¶Ð¸ chat_id."]
                )
            flag_map: dict[str, bool] = {}
            _bool_vals = {
                "true": True,
                "on": True,
                "Ð²ÐºÐ»": True,
                "1": True,
                "false": False,
                "off": False,
                "Ð²Ñ‹ÐºÐ»": False,
                "0": False,
            }
            _flag_aliases = {
                "require": "require_owner_mention_or_context",
                "mention": "require_owner_mention_or_context",
                "require_owner_mention_or_context": "require_owner_mention_or_context",
                "questions": "reply_only_questions",
                "reply_only_questions": "reply_only_questions",
                "human": "human_like",
                "human_like": "human_like",
            }
            errors_list = []
            for part in parts[1:]:
                if "=" in part:
                    k, _, v = part.partition("=")
                    flag_name = _flag_aliases.get(k.lower())
                    bool_val = _bool_vals.get(v.lower())
                    if flag_name and bool_val is not None:
                        flag_map[flag_name] = bool_val
                    else:
                        errors_list.append(f"ÐÐµ Ñ€Ð°ÑÐ¿Ð¾Ð·Ð½Ð°Ð½Ð¾: {part}")
            if not flag_map:
                return False, self._render_perchat_input_prompt(
                    user_id, errors=errors_list or ["Ð£ÐºÐ°Ð¶Ð¸ Ñ…Ð¾Ñ‚Ñ Ð±Ñ‹ Ð¾Ð´Ð¸Ð½ Ñ„Ð»Ð°Ð³."]
                )
            new_overrides = dict(target.chat_overrides)
            existing = dict(new_overrides.get(chat_id_str, {}))
            existing.update(flag_map)
            new_overrides[chat_id_str] = existing
            await self._user_memory_store.upsert_special_target(
                user_id, SpecialTargetPatch(chat_overrides=new_overrides)
            )
            return True, await self._render_special_target_detail(user_id)

        return False, self._render_special_target_input_prompt(
            action, errors=["ÐÐµÐ¸Ð·Ð²ÐµÑÑ‚Ð½Ð¾Ðµ Ð´ÐµÐ¹ÑÑ‚Ð²Ð¸Ðµ."]
        )

    async def _apply_close_contact_input(
        self, action: str, raw_text: str
    ) -> tuple[bool, str]:
        if action == "close_add":
            lines = [
                self._sanitize_structured_input_line(line)
                for line in raw_text.splitlines()
                if line.strip()
            ]
            if len(lines) < 2:
                return False, self._render_close_contact_input_prompt(
                    action,
                    errors=[
                        "ÐÑƒÐ¶Ð½Ð¾ Ð¼Ð¸Ð½Ð¸Ð¼ÑƒÐ¼ 2 ÑÑ‚Ñ€Ð¾ÐºÐ¸: user_id/@username Ð¸ Ñ€Ð¾Ð»ÑŒ. Ð¢Ñ€ÐµÑ‚ÑŒÐµÐ¹ ÑÑ‚Ñ€Ð¾ÐºÐ¾Ð¹ Ð¼Ð¾Ð¶Ð½Ð¾ Ð´Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ ÐºÐ¾Ð¼Ð¼ÐµÐ½Ñ‚Ð°Ñ€Ð¸Ð¹."
                    ],
                )
            resolved = await self._resolve_user_token(lines[0])
            if resolved is None:
                return False, self._render_close_contact_input_prompt(
                    action, errors=["ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð½Ð°Ð¹Ñ‚Ð¸ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ."]
                )
            relation_type = self._normalize_close_contact_relation(lines[1])
            if relation_type is None:
                return False, self._render_close_contact_input_prompt(
                    action,
                    errors=[
                        "Ð Ð¾Ð»ÑŒ Ð½Ðµ Ñ€Ð°ÑÐ¿Ð¾Ð·Ð½Ð°Ð½Ð°. Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐ¹: Ð±Ð»Ð¸Ð·ÐºÐ¸Ð¹, Ð¼ÐµÐ½ÐµÐµ Ð±Ð»Ð¸Ð·ÐºÐ¸Ð¹, Ð¿Ð»Ð°Ð½Ñ‹, Ð´ÐµÐ»Ð¾."
                    ],
                )
            comment = " ".join(lines[2:]).strip()
            await self._user_memory_store.upsert_close_contact(
                resolved.chat_id,
                CloseContactPatch(
                    relation_type=relation_type,
                    username=resolved.label.lstrip("@"),
                    comment=comment,
                    updated_at=self._now_text(),
                ),
            )
            return True, await self._render_close_contact_detail(resolved.chat_id)

        if action == "close_remove":
            token = self._sanitize_structured_input_line(raw_text.strip())
            if not token:
                return False, self._render_close_contact_input_prompt(
                    action, errors=["Ð£ÐºÐ°Ð¶Ð¸ user_id Ð¸Ð»Ð¸ @username."]
                )
            resolved = await self._resolve_user_token(token)
            if resolved is None:
                return False, self._render_close_contact_input_prompt(
                    action, errors=["ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð½Ð°Ð¹Ñ‚Ð¸ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ."]
                )
            removed = await self._user_memory_store.remove_close_contact(
                resolved.chat_id
            )
            notice = "ÐšÐ¾Ð½Ñ‚Ð°ÐºÑ‚ ÑƒÐ´Ð°Ð»Ñ‘Ð½." if removed else "ÐšÐ¾Ð½Ñ‚Ð°ÐºÑ‚ Ð½Ðµ Ð±Ñ‹Ð» Ð½Ð°Ð¹Ð´ÐµÐ½."
            return True, await self._render_close_contacts_panel(
                page=0, extra_notice=notice
            )

        if action.startswith("close_comment_"):
            user_id_text = action.removeprefix("close_comment_")
            if not user_id_text.isdigit():
                return False, self._render_close_contact_input_prompt(
                    action, errors=["ÐšÐ¾Ð½Ñ‚Ð°ÐºÑ‚ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½."]
                )
            user_id = int(user_id_text)
            contact = await self._user_memory_store.get_close_contact(user_id)
            if contact is None:
                return False, self._render_close_contact_input_prompt(
                    action, errors=["ÐšÐ¾Ð½Ñ‚Ð°ÐºÑ‚ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½."]
                )
            await self._user_memory_store.upsert_close_contact(
                user_id,
                CloseContactPatch(
                    comment=self._sanitize_structured_input_line(raw_text.strip()),
                    updated_at=self._now_text(),
                ),
            )
            return True, await self._render_close_contact_detail(user_id)

        return False, self._render_close_contact_input_prompt(
            action, errors=["ÐÐµÐ¸Ð·Ð²ÐµÑÑ‚Ð½Ð¾Ðµ Ð´ÐµÐ¹ÑÑ‚Ð²Ð¸Ðµ."]
        )

    async def _resolve_chat_tokens(
        self, tokens: list[str]
    ) -> tuple[list[ResolvedChat], list[str]]:
        resolved: list[ResolvedChat] = []
        errors: list[str] = []
        seen: set[int] = set()
        for token in tokens:
            try:
                item = await self._resolve_chat_token(token)
            except ValueError as exc:
                errors.append(f"{html.escape(token)}: {html.escape(str(exc))}")
                continue
            if item.chat_id in seen:
                continue
            seen.add(item.chat_id)
            resolved.append(item)
        return resolved, errors

    async def _resolve_chat_token(self, token: str) -> ResolvedChat:
        lookup = self._normalize_chat_lookup(token)
        if lookup is None:
            raise ValueError("Ð½ÐµÐ¿Ð¾Ð´Ð´ÐµÑ€Ð¶Ð¸Ð²Ð°ÐµÐ¼Ñ‹Ð¹ Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚")

        if isinstance(lookup, int):
            try:
                chat = await self._client.get_chat(lookup)
            except Exception:
                supergroup_lookup = self._normalize_numeric_supergroup_id(lookup)
                if supergroup_lookup is not None and supergroup_lookup != lookup:
                    try:
                        chat = await self._client.get_chat(supergroup_lookup)
                    except Exception:
                        return ResolvedChat(chat_id=lookup, label=f"chat_id {lookup}")
                else:
                    return ResolvedChat(chat_id=lookup, label=f"chat_id {lookup}")
        else:
            try:
                chat = await self._client.get_chat(lookup)
            except Exception as exc:
                raise ValueError("Ð±Ð¾Ñ‚ Ð½Ðµ ÑÐ¼Ð¾Ð³ Ð¾Ñ‚ÐºÑ€Ñ‹Ñ‚ÑŒ ÑÑ‚Ð¾Ñ‚ Ñ‡Ð°Ñ‚") from exc

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
        if username:
            label = f"@{username} ({chat.id})"
        elif title:
            label = f"{title} ({chat.id})"
        else:
            label = f"chat_id {chat.id}"
        return ResolvedChat(chat_id=chat.id, label=label)

    async def _resolve_user_token(self, token: str) -> ResolvedChat | None:
        cleaned = token.strip()
        if not cleaned:
            return None
        is_numeric = re.fullmatch(r"-?\d+", cleaned) is not None
        normalized_username = cleaned.lstrip("@")
        if is_numeric:
            lookup: str | int = int(cleaned)
        elif cleaned.startswith("@") or USERNAME_RE.fullmatch(cleaned):
            lookup = cleaned if cleaned.startswith("@") else f"@{cleaned}"
        else:
            return None
        user = None
        try:
            user = await self._client.get_users(lookup)
        except Exception:
            user = None
        if user is None:
            try:
                user = await self._client.get_chat(lookup)
            except Exception:
                user = None
        if user is None and not is_numeric:
            known_user_id = await self._user_memory_store.find_user_id_by_username(
                normalized_username
            )
            if known_user_id is not None:
                return ResolvedChat(
                    chat_id=known_user_id, label=f"@{normalized_username}"
                )
        if user is None and is_numeric:
            return ResolvedChat(chat_id=int(cleaned), label=f"user_id {int(cleaned)}")
        if user is None:
            return None
        username = getattr(user, "username", None)
        if username:
            label = f"@{username}"
        else:
            label = (
                " ".join(
                    part
                    for part in [
                        getattr(user, "first_name", None),
                        getattr(user, "last_name", None),
                    ]
                    if part
                ).strip()
                or f"user_id {getattr(user, 'id', cleaned)}"
            )
        return ResolvedChat(
            chat_id=getattr(user, "id", int(cleaned) if is_numeric else 0), label=label
        )

    def _normalize_chat_lookup(self, token: str) -> str | int | None:
        cleaned = token.strip().strip(",;")
        if not cleaned:
            return None
        if re.fullmatch(r"-?\d+", cleaned):
            return int(cleaned)
        if cleaned.startswith("@"):
            username = cleaned[1:]
            return cleaned if USERNAME_RE.fullmatch(username) else None

        link_match = PUBLIC_LINK_RE.match(cleaned)
        if link_match:
            path = link_match.group("path").split("?", 1)[0].strip("/")
            if not path:
                return None
            parts = [part for part in path.split("/") if part]
            if not parts:
                return None
            head = parts[0]
            if head == "c" and len(parts) >= 2 and parts[1].isdigit():
                return int(f"-100{parts[1]}")
            if head.startswith("+") or head == "joinchat":
                return cleaned
            return f"@{head}"

        return f"@{cleaned}" if USERNAME_RE.fullmatch(cleaned) else None

    def _normalize_numeric_supergroup_id(self, lookup: int) -> int | None:
        if lookup < 0:
            return lookup
        text = str(lookup)
        if len(text) < 9:
            return None
        try:
            return int(f"-100{text}")
        except ValueError:
            return None

    def _extract_chat_tokens(self, raw_text: str) -> list[str]:
        return [item for item in CHAT_TOKEN_RE.split(raw_text.strip()) if item]

    async def _refresh_models(self) -> bool:
        try:
            await self._groq_client.refresh_models()
            return True
        except Exception:
            LOGGER.exception("control_refresh_failed")
            return False

    async def _upsert_panel_message(
        self,
        *,
        chat_id: int,
        message_id: int | None,
        text: str,
        reply_markup: InlineKeyboardMarkup | None,
    ) -> tuple[int, int]:
        if message_id is not None:
            try:
                await self._client.edit_message_text(
                    chat_id,
                    message_id,
                    text,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )
                return chat_id, message_id
            except MessageNotModified:
                return chat_id, message_id
            except RPCError:
                LOGGER.warning(
                    "control_panel_edit_failed chat_id=%s message_id=%s",
                    chat_id,
                    message_id,
                    exc_info=True,
                )

        sent = await self._client.send_message(
            chat_id,
            text,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
        return sent.chat.id, sent.id

    def _render_main_panel(self, snapshot: PersistentState) -> str:
        limits = snapshot.model_limits.get(snapshot.active_model, snapshot.last_limits)
        enabled_count = sum(
            1 for enabled in snapshot.enabled_models.values() if enabled
        )
        preferred_order = preferred_generator_order(
            available_models=snapshot.available_models,
            enabled_models=snapshot.enabled_models,
            active_model=snapshot.active_model,
            model_limits=snapshot.model_limits,
        )
        order_preview = (
            " -> ".join(preferred_order[:5])
            if preferred_order
            else "Ð½ÐµÑ‚ Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð½Ñ‹Ñ… Ð¼Ð¾Ð´ÐµÐ»ÐµÐ¹"
        )
        return (
            "<b>ProjectOwner Control</b>\n\n"
            f"<b>ÐÐºÑ‚Ð¸Ð²Ð½Ñ‹Ð¹ Ð³ÐµÐ½ÐµÑ€Ð°Ñ‚Ð¾Ñ€:</b> {html.escape(snapshot.active_model)}\n"
            f"<b>ÐœÐ¾Ð´ÐµÐ»ÑŒ-ÑÑƒÐ´ÑŒÑ:</b> {html.escape(snapshot.judge_model)}\n"
            f"<b>Ð ÐµÐ·ÐµÑ€Ð²:</b> {self._bool_text(snapshot.fallback_enabled)}\n"
            f"<b>Ð ÐµÐ¶Ð¸Ð¼ AI:</b> {self._bool_text(snapshot.ai_mode_enabled)}\n"
            f"<b>ÐšÐ¾Ð¼Ð°Ð½Ð´Ð½Ñ‹Ð¹ Ñ€ÐµÐ¶Ð¸Ð¼:</b> {self._bool_text(snapshot.command_mode_enabled)}\n"
            f"<b>ÐÐ²Ñ‚Ð¾Ð¾Ñ‚Ð²ÐµÑ‚:</b> {self._bool_text(snapshot.auto_reply_enabled)}\n"
            f"<b>ÐšÐ¾Ð¼Ñƒ Ð¾Ñ‚Ð²ÐµÑ‡Ð°Ñ‚ÑŒ:</b> {html.escape(self._describe_reply_audience_mode(snapshot.reply_audience_mode))}\n"
            f"<b>Ð¢Ð¾Ð»ÑŒÐºÐ¾ Ð²Ð¾Ð¿Ñ€Ð¾ÑÑ‹/Ð·Ð°Ð¿Ñ€Ð¾ÑÑ‹:</b> {self._bool_text(snapshot.reply_only_questions)}\n"
            f"<b>Ð¢Ð¾Ð»ÑŒÐºÐ¾ Ð¿Ñ€Ð¸ Ð¾Ð±Ñ€Ð°Ñ‰ÐµÐ½Ð¸Ð¸ Ðº Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ñƒ/Ð¿Ð¾ ÐºÐ¾Ð½Ñ‚ÐµÐºÑÑ‚Ñƒ:</b> {self._bool_text(snapshot.require_owner_mention_or_context)}\n"
            f"<b>ÐŸÑƒÐ» Ð¼Ð¾Ð´ÐµÐ»ÐµÐ¹:</b> {enabled_count}/{len(snapshot.available_models)} Ð²ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¾\n"
            f"<b>Ð Ð°Ð·Ñ€ÐµÑˆÑ‘Ð½Ð½Ñ‹Ðµ Ñ‡Ð°Ñ‚Ñ‹:</b> {len(snapshot.allowed_chat_ids)}\n"
            f"<b>ÐžÑÑ‚Ð°Ð»Ð¾ÑÑŒ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ¾Ð²:</b> {self._format_limit_value(limits.remaining_requests, limits.request_limit)}\n"
            f"<b>ÐžÑÑ‚Ð°Ð»Ð¾ÑÑŒ Ñ‚Ð¾ÐºÐµÐ½Ð¾Ð²:</b> {self._format_limit_value(limits.remaining_tokens, limits.token_limit)}\n"
            f"<b>ÐŸÑ€ÐµÐ´Ð¿Ð¾Ñ‡Ñ‚Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ñ‹Ð¹ Ð¿Ð¾Ñ€ÑÐ´Ð¾Ðº:</b> {html.escape(order_preview)}\n"
            f"<b>ÐŸÐ¾ÑÐ»ÐµÐ´Ð½ÐµÐµ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ Ð¿ÑƒÐ»Ð°:</b> {self._unknown(snapshot.models_refreshed_at)}"
        )

    def _render_models_panel(self, snapshot: PersistentState) -> str:
        order_lines = preferred_generator_order(
            available_models=snapshot.available_models,
            enabled_models=snapshot.enabled_models,
            active_model=snapshot.active_model,
            model_limits=snapshot.model_limits,
        )
        lines = [
            "<b>ÐŸÑƒÐ» Ð¼Ð¾Ð´ÐµÐ»ÐµÐ¹</b>",
            "",
            f"<b>ÐÐºÑ‚Ð¸Ð²Ð½Ñ‹Ð¹ Ð³ÐµÐ½ÐµÑ€Ð°Ñ‚Ð¾Ñ€:</b> {html.escape(snapshot.active_model)}",
            f"<b>ÐœÐ¾Ð´ÐµÐ»ÑŒ-ÑÑƒÐ´ÑŒÑ:</b> {html.escape(snapshot.judge_model)}",
            f"<b>ÐŸÐ¾ÑÐ»ÐµÐ´Ð½ÐµÐµ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ:</b> {self._unknown(snapshot.models_refreshed_at)}",
            "",
            "<b>Ð¢ÐµÐºÑƒÑ‰Ð¸Ð¹ Ð¿Ð¾Ñ€ÑÐ´Ð¾Ðº Ð³ÐµÐ½ÐµÑ€Ð°Ñ†Ð¸Ð¸</b>",
        ]
        if order_lines:
            for index, model_name in enumerate(order_lines[:9], start=1):
                lines.append(f"{index}. {html.escape(model_name)}")
        else:
            lines.append("Ð½ÐµÑ‚ Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð½Ñ‹Ñ… Ð¼Ð¾Ð´ÐµÐ»ÐµÐ¹")

        lines.extend(["", "<b>Ð¡Ð¾ÑÑ‚Ð¾ÑÐ½Ð¸Ðµ Ð¼Ð¾Ð´ÐµÐ»ÐµÐ¹</b>"])
        for info in MODEL_CATALOG:
            if info.name in snapshot.available_models:
                lines.append(self._render_model_line(info.name, snapshot))
        return "\n".join(lines)

    def _render_model_selection_panel(
        self, snapshot: PersistentState, mode: str
    ) -> str:
        titles = {
            "active": "Ð’Ñ‹Ð±Ð¾Ñ€ Ð³ÐµÐ½ÐµÑ€Ð°Ñ‚Ð¾Ñ€Ð°",
            "judge": "Ð’Ñ‹Ð±Ð¾Ñ€ Ð¼Ð¾Ð´ÐµÐ»Ð¸-ÑÑƒÐ´ÑŒÐ¸",
            "toggle": "Ð’ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¸Ðµ Ð¸ Ð¾Ñ‚ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¸Ðµ Ð¼Ð¾Ð´ÐµÐ»ÐµÐ¹",
        }
        lines = [f"<b>{titles.get(mode, 'ÐœÐ¾Ð´ÐµÐ»Ð¸')}</b>", ""]
        if mode == "active":
            lines.append(
                f"<b>Ð¡ÐµÐ¹Ñ‡Ð°Ñ Ð³ÐµÐ½ÐµÑ€Ð°Ñ‚Ð¾Ñ€:</b> {html.escape(snapshot.active_model)}"
            )
        elif mode == "judge":
            lines.append(
                f"<b>Ð¡ÐµÐ¹Ñ‡Ð°Ñ Ð¼Ð¾Ð´ÐµÐ»ÑŒ-ÑÑƒÐ´ÑŒÑ:</b> {html.escape(snapshot.judge_model)}"
            )
        else:
            enabled_count = sum(
                1 for enabled in snapshot.enabled_models.values() if enabled
            )
            lines.append(
                f"<b>Ð¡ÐµÐ¹Ñ‡Ð°Ñ Ð²ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¾:</b> {enabled_count}/{len(snapshot.available_models)}"
            )
        lines.append("")
        for info in MODEL_CATALOG:
            if info.name in snapshot.available_models:
                lines.append(self._render_model_line(info.name, snapshot))
        return "\n".join(lines)

    def _render_chat_panel(self, snapshot: PersistentState) -> str:
        return (
            "<b>Ð§Ð°Ñ‚Ñ‹ Ð´Ð»Ñ Ð°Ð²Ñ‚Ð¾Ð¾Ñ‚Ð²ÐµÑ‚Ð°</b>\n\n"
            f"<b>Ð Ð°Ð·Ñ€ÐµÑˆÐµÐ½Ð¾ Ñ‡Ð°Ñ‚Ð¾Ð²:</b> {len(snapshot.allowed_chat_ids)}\n"
            "Ð—Ð´ÐµÑÑŒ Ð¼Ð¾Ð¶Ð½Ð¾ Ð¿Ð¾ÑÐ¼Ð¾Ñ‚Ñ€ÐµÑ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº, Ð´Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ð½Ð¾Ð²Ñ‹Ðµ Ñ‡Ð°Ñ‚Ñ‹ Ð¸Ð»Ð¸ ÑƒÐ±Ñ€Ð°Ñ‚ÑŒ ÑÑ‚Ð°Ñ€Ñ‹Ðµ."
        )

    def _render_allowed_chats_panel(self, snapshot: PersistentState) -> str:
        lines = ["<b>Ð Ð°Ð·Ñ€ÐµÑˆÑ‘Ð½Ð½Ñ‹Ðµ Ñ‡Ð°Ñ‚Ñ‹</b>", ""]
        if not snapshot.allowed_chat_ids:
            lines.append("Ð¡Ð¿Ð¸ÑÐ¾Ðº Ð¿ÑƒÑÑ‚.")
        else:
            for chat_id in snapshot.allowed_chat_ids[:50]:
                lines.append(f"â€¢ <code>{chat_id}</code>")
            if len(snapshot.allowed_chat_ids) > 50:
                lines.append(f"... ÐµÑ‰Ñ‘ {len(snapshot.allowed_chat_ids) - 50}")
        return "\n".join(lines)

    def _render_chat_input_prompt(
        self, action: str, errors: list[str] | None = None
    ) -> str:
        title = "Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ Ñ‡Ð°Ñ‚Ð¾Ð²" if action == "add" else "Ð£Ð´Ð°Ð»ÐµÐ½Ð¸Ðµ Ñ‡Ð°Ñ‚Ð¾Ð²"
        lines = [
            f"<b>{title}</b>",
            "",
            "ÐžÑ‚Ð¿Ñ€Ð°Ð²ÑŒ ÑÑÑ‹Ð»ÐºÑƒ, username Ð¸Ð»Ð¸ chat_id. ÐœÐ¾Ð¶Ð½Ð¾ Ð½ÐµÑÐºÐ¾Ð»ÑŒÐºÐ¾ Ñ‡ÐµÑ€ÐµÐ· Ð¿Ñ€Ð¾Ð±ÐµÐ» Ð¸Ð»Ð¸ Ñ Ð½Ð¾Ð²Ð¾Ð¹ ÑÑ‚Ñ€Ð¾ÐºÐ¸.",
        ]
        if errors:
            lines.extend(["", "<b>Ð§Ñ‚Ð¾ Ð½Ðµ Ñ‚Ð°Ðº:</b>"])
            lines.extend(f"â€¢ {error}" for error in errors[:8])
        return "\n".join(lines)

    def _render_chat_action_result(
        self,
        action: str,
        changed: list[ResolvedChat],
        skipped: list[ResolvedChat],
        errors: list[str],
        snapshot: PersistentState,
    ) -> str:
        title = "Ð§Ð°Ñ‚Ñ‹ Ð´Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ñ‹" if action == "add" else "Ð§Ð°Ñ‚Ñ‹ ÑƒÐ±Ñ€Ð°Ð½Ñ‹"
        lines = [
            f"<b>{title}</b>",
            "",
            f"<b>Ð˜Ð·Ð¼ÐµÐ½ÐµÐ½Ð¾:</b> {len(changed)}",
            f"<b>Ð‘ÐµÐ· Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ð¹:</b> {len(skipped)}",
            f"<b>ÐžÑˆÐ¸Ð±Ð¾Ðº:</b> {len(errors)}",
            f"<b>Ð¢ÐµÐ¿ÐµÑ€ÑŒ Ñ€Ð°Ð·Ñ€ÐµÑˆÐµÐ½Ð¾:</b> {len(snapshot.allowed_chat_ids)}",
        ]
        if changed:
            lines.extend(["", "<b>ÐžÐ±Ð½Ð¾Ð²Ð»Ñ‘Ð½Ð½Ñ‹Ðµ Ñ‡Ð°Ñ‚Ñ‹:</b>"])
            lines.extend(f"â€¢ {html.escape(item.label)}" for item in changed[:8])
        if skipped:
            lines.extend(["", "<b>Ð‘ÐµÐ· Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ð¹:</b>"])
            lines.extend(f"â€¢ {html.escape(item.label)}" for item in skipped[:8])
        if errors:
            lines.extend(["", "<b>ÐžÑˆÐ¸Ð±ÐºÐ¸:</b>"])
            lines.extend(f"â€¢ {error}" for error in errors[:8])
        return "\n".join(lines)

    async def _render_special_targets_panel(
        self, page: int = 0, extra_notice: str | None = None
    ) -> str:
        targets = await self._user_memory_store.get_special_targets_snapshot()
        ordered = list(sorted(targets.items(), key=lambda item: item[0]))
        items, page, total_pages = self._paginate_pairs(ordered, page)
        lines = ["<b>Ð¡Ð¿ÐµÑ†-Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ð¸ Ð´Ð»Ñ Ð¾Ñ‚Ð²ÐµÑ‚Ð°</b>", ""]
        if extra_notice:
            lines.append(html.escape(extra_notice))
            lines.append("")
        if not ordered:
            lines.append("Ð¡Ð¿Ð¸ÑÐ¾Ðº Ð¿ÑƒÑÑ‚.")
            lines.append(
                "Ð”Ð¾Ð±Ð°Ð²ÑŒ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ, Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð²ÐºÐ»ÑŽÑ‡Ð¸Ñ‚ÑŒ Ð´Ð»Ñ Ð½ÐµÐ³Ð¾ Ð¾Ñ‚Ð´ÐµÐ»ÑŒÐ½Ñ‹Ð¹ human-like Ñ€ÐµÐ¶Ð¸Ð¼ Ð¾Ñ‚Ð²ÐµÑ‚Ð°."
            )
            return "\n".join(lines)
        lines.append(f"<b>Ð’ÑÐµÐ³Ð¾ Ñ†ÐµÐ»ÐµÐ¹:</b> {len(ordered)}")
        lines.append(f"<b>Ð¡Ñ‚Ñ€Ð°Ð½Ð¸Ñ†Ð°:</b> {page + 1}/{total_pages}")
        lines.append("")
        for user_id, target in items:
            label = f"@{target.username}" if target.username else f"user_id {user_id}"
            scope = (
                "Ð²ÑÐµ Ñ€Ð°Ð·Ñ€ÐµÑˆÑ‘Ð½Ð½Ñ‹Ðµ Ñ‡Ð°Ñ‚Ñ‹"
                if not target.allowed_chat_ids
                else f"Ñ‡Ð°Ñ‚Ð¾Ð²: {len(target.allowed_chat_ids)}"
            )
            trigger_mode = self._describe_special_target_trigger_mode(target)
            lines.append(
                f"â€¢ <code>{user_id}</code> | {html.escape(label)} | "
                f"{'ON' if target.enabled else 'OFF'} | {html.escape(scope)} | {html.escape(trigger_mode)}"
            )
        return "\n".join(lines)

    async def _render_close_contacts_panel(
        self, page: int = 0, extra_notice: str | None = None
    ) -> str:
        contacts = await self._user_memory_store.get_close_contacts_snapshot()
        ordered = list(sorted(contacts.items(), key=lambda item: item[0]))
        items, page, total_pages = self._paginate_pairs(ordered, page)
        lines = ["<b>Ð‘Ð°Ð·Ð° Ð±Ð»Ð¸Ð·ÐºÐ¸Ñ… Ð¸ Ð²Ð°Ð¶Ð½Ñ‹Ñ… Ð»ÑŽÐ´ÐµÐ¹</b>", ""]
        if extra_notice:
            lines.append(html.escape(extra_notice))
            lines.append("")
        if not ordered:
            lines.append("Ð¡Ð¿Ð¸ÑÐ¾Ðº Ð¿ÑƒÑÑ‚.")
            lines.append(
                "Ð”Ð¾Ð±Ð°Ð²ÑŒ Ñ‡ÐµÐ»Ð¾Ð²ÐµÐºÐ°, Ñ‡Ñ‚Ð¾Ð±Ñ‹ ÑÐ¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ Ñ€Ð¾Ð»ÑŒ, ÐºÐ¾Ð¼Ð¼ÐµÐ½Ñ‚Ð°Ñ€Ð¸Ð¹ Ð¸ Ð¿Ð¾ÑÑ‚Ð¾ÑÐ½Ð½Ñ‹Ðµ Ð·Ð°Ð¼ÐµÑ‚ÐºÐ¸ Ð¿Ð¾ Ð¾Ð±Ñ‰ÐµÐ½Ð¸ÑŽ."
            )
            return "\n".join(lines)
        lines.append(f"<b>Ð’ÑÐµÐ³Ð¾ ÐºÐ¾Ð½Ñ‚Ð°ÐºÑ‚Ð¾Ð²:</b> {len(ordered)}")
        lines.append(f"<b>Ð¡Ñ‚Ñ€Ð°Ð½Ð¸Ñ†Ð°:</b> {page + 1}/{total_pages}")
        lines.append("")
        for user_id, contact in items:
            label = f"@{contact.username}" if contact.username else f"user_id {user_id}"
            relation = self._describe_close_contact_relation(contact.relation_type)
            comment = (contact.comment or "").strip()
            preview = f" | {html.escape(comment[:70])}" if comment else ""
            lines.append(
                f"â€¢ <code>{user_id}</code> | {html.escape(label)} | {html.escape(relation)}{preview}"
            )
        return "\n".join(lines)

    def _render_close_contact_input_prompt(
        self, action: str, errors: list[str] | None = None
    ) -> str:
        if action == "close_add":
            lines = [
                "<b>Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ñ‡ÐµÐ»Ð¾Ð²ÐµÐºÐ° Ð² Ð±Ð°Ð·Ñƒ Ð±Ð»Ð¸Ð·ÐºÐ¸Ñ…</b>",
                "",
                "ÐŸÑ€Ð¸ÑˆÐ»Ð¸ 2-3 ÑÑ‚Ñ€Ð¾ÐºÐ¸:",
                "1. user_id Ð¸Ð»Ð¸ @username",
                "2. Ñ€Ð¾Ð»ÑŒ: Ð±Ð»Ð¸Ð·ÐºÐ¸Ð¹ / Ð¼ÐµÐ½ÐµÐµ Ð±Ð»Ð¸Ð·ÐºÐ¸Ð¹ / Ð¿Ð»Ð°Ð½Ñ‹ / Ð´ÐµÐ»Ð¾",
                "3. ÐºÐ¾Ð¼Ð¼ÐµÐ½Ñ‚Ð°Ñ€Ð¸Ð¹ Ð´Ð»Ñ Ð˜Ð˜, ÐºÐ°Ðº Ñ Ð½Ð¸Ð¼ Ð¾Ð±Ñ‰Ð°Ñ‚ÑŒÑÑ, Ñ‡Ñ‚Ð¾ ÑƒÑ‡Ð¸Ñ‚Ñ‹Ð²Ð°Ñ‚ÑŒ",
            ]
        elif action == "close_remove":
            lines = [
                "<b>Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ñ‡ÐµÐ»Ð¾Ð²ÐµÐºÐ° Ð¸Ð· Ð±Ð°Ð·Ñ‹ Ð±Ð»Ð¸Ð·ÐºÐ¸Ñ…</b>",
                "",
                "ÐŸÑ€Ð¸ÑˆÐ»Ð¸ user_id Ð¸Ð»Ð¸ @username.",
            ]
        else:
            lines = [
                "<b>ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ ÐºÐ¾Ð¼Ð¼ÐµÐ½Ñ‚Ð°Ñ€Ð¸Ð¹</b>",
                "",
                "ÐŸÑ€Ð¸ÑˆÐ»Ð¸ Ð½Ð¾Ð²Ñ‹Ð¹ ÐºÐ¾Ð¼Ð¼ÐµÐ½Ñ‚Ð°Ñ€Ð¸Ð¹ Ð¾ Ñ‚Ð¾Ð¼, ÐºÐ°Ðº Ð˜Ð˜ Ð´Ð¾Ð»Ð¶ÐµÐ½ Ð¾Ð±Ñ‰Ð°Ñ‚ÑŒÑÑ Ñ ÑÑ‚Ð¸Ð¼ Ñ‡ÐµÐ»Ð¾Ð²ÐµÐºÐ¾Ð¼.",
            ]
        if errors:
            lines.extend(["", "<b>ÐžÑˆÐ¸Ð±ÐºÐ¸:</b>"])
            lines.extend(f"â€¢ {html.escape(error)}" for error in errors[:8])
        return "\n".join(lines)

    async def _render_close_contact_detail(self, user_id: int) -> str:
        contact = await self._user_memory_store.get_close_contact(user_id)
        if contact is None:
            return "<b>ÐšÐ¾Ð½Ñ‚Ð°ÐºÑ‚ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½</b>"
        label = f"@{contact.username}" if contact.username else f"user_id {user_id}"
        profile = await self._user_memory_store.get_profile(user_id)
        learned_style = (
            f"{profile.typical_tone}, ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ð¹: {profile.message_count}, Ñ‚ÐµÐ¼Ñ‹: {', '.join(profile.common_topics[:4])}"
            if profile.message_count > 0
            else "ÐµÑ‰Ñ‘ Ð½Ðµ Ð½Ð°ÐºÐ¾Ð¿Ð»ÐµÐ½Ð¾"
        )
        comment = html.escape(contact.comment or "Ð½ÐµÑ‚")
        return (
            "<b>ÐšÐ°Ñ€Ñ‚Ð¾Ñ‡ÐºÐ° Ð±Ð»Ð¸Ð·ÐºÐ¾Ð³Ð¾ Ñ‡ÐµÐ»Ð¾Ð²ÐµÐºÐ°</b>\n\n"
            f"<b>User:</b> {html.escape(label)}\n"
            f"<b>ID:</b> <code>{user_id}</code>\n"
            f"<b>ÐšÑ‚Ð¾ Ð¾Ð½ Ñ‚ÐµÐ±Ðµ:</b> {html.escape(self._describe_close_contact_relation(contact.relation_type))}\n"
            f"<b>ÐšÐ¾Ð¼Ð¼ÐµÐ½Ñ‚Ð°Ñ€Ð¸Ð¹:</b> {comment}\n"
            f"<b>ÐšÐ°Ðº Ð¾Ð½ Ð¾Ð±Ñ‹Ñ‡Ð½Ð¾ Ð¾Ð±Ñ‰Ð°ÐµÑ‚ÑÑ:</b> {html.escape(learned_style)}\n"
            f"<b>ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¾:</b> {self._unknown(contact.updated_at)}"
        )

    def _render_special_target_input_prompt(
        self, action: str, errors: list[str] | None = None
    ) -> str:
        if action == "special_add":
            title = "Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ ÑÐ¿ÐµÑ†-Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ"
            hint = "ÐŸÑ€Ð¸ÑˆÐ»Ð¸ `user_id` Ð¸Ð»Ð¸ `@username`."
        elif action == "special_remove":
            title = "Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ ÑÐ¿ÐµÑ†-Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ"
            hint = "ÐŸÑ€Ð¸ÑˆÐ»Ð¸ `user_id` Ð¸Ð»Ð¸ `@username`."
        else:
            title = "ÐžÐ³Ñ€Ð°Ð½Ð¸Ñ‡Ð¸Ñ‚ÑŒ Ñ‡Ð°Ñ‚Ñ‹ Ñ†ÐµÐ»Ð¸"
            hint = "ÐŸÑ€Ð¸ÑˆÐ»Ð¸ chat_id / ÑÑÑ‹Ð»ÐºÑƒ / @username Ñ‡Ð°Ñ‚Ð° Ñ‡ÐµÑ€ÐµÐ· Ð¿Ñ€Ð¾Ð±ÐµÐ» Ð¸Ð»Ð¸ Ð½Ð¾Ð²ÑƒÑŽ ÑÑ‚Ñ€Ð¾ÐºÑƒ. Ð•ÑÐ»Ð¸ Ð½ÑƒÐ¶ÐµÐ½ Ñ€ÐµÐ¶Ð¸Ð¼ Ð²Ð¾ Ð²ÑÐµÑ… Ñ€Ð°Ð·Ñ€ÐµÑˆÑ‘Ð½Ð½Ñ‹Ñ… Ñ‡Ð°Ñ‚Ð°Ñ…, Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐ¹ ÐºÐ½Ð¾Ð¿ÐºÑƒ ÑÐ±Ñ€Ð¾ÑÐ° Ð² ÐºÐ°Ñ€Ñ‚Ð¾Ñ‡ÐºÐµ."
        lines = [f"<b>{title}</b>", "", hint]
        if errors:
            lines.extend(["", "<b>ÐžÑˆÐ¸Ð±ÐºÐ¸:</b>"])
            lines.extend(f"â€¢ {html.escape(error)}" for error in errors[:8])
        return "\n".join(lines)

    async def _render_special_target_detail(self, user_id: int) -> str:
        target = await self._user_memory_store.get_special_target(user_id)
        if target is None:
            return "<b>Ð¡Ð¿ÐµÑ†-Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑŒ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½</b>"
        label = f"@{target.username}" if target.username else f"user_id {user_id}"
        if target.allowed_chat_ids:
            chat_scope = ", ".join(
                f"<code>{chat_id}</code>" for chat_id in target.allowed_chat_ids[:12]
            )
        else:
            chat_scope = "Ð²ÑÐµ Ñ€Ð°Ð·Ñ€ÐµÑˆÑ‘Ð½Ð½Ñ‹Ðµ Ñ‡Ð°Ñ‚Ñ‹"
        overrides_text = ""
        if target.chat_overrides:
            lines = []
            for chat_id_str, flags in target.chat_overrides.items():
                flag_parts = ", ".join(f"{k}={v}" for k, v in flags.items())
                lines.append(f"  <code>{chat_id_str}</code>: {flag_parts}")
            overrides_text = "\n<b>Per-chat Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸:</b>\n" + "\n".join(lines)
        return (
            "<b>ÐÐ°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ ÑÐ¿ÐµÑ†-Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ</b>\n\n"
            f"<b>User:</b> {html.escape(label)}\n"
            f"<b>ID:</b> <code>{user_id}</code>\n"
            f"<b>Ð’ÐºÐ»ÑŽÑ‡Ñ‘Ð½:</b> {self._bool_text(target.enabled)}\n"
            f"<b>Human-like:</b> {self._bool_text(target.human_like)}\n"
            f"<b>Ð‘ÐµÐ· Ð·Ð°Ð´ÐµÑ€Ð¶ÐºÐ¸:</b> {self._bool_text(target.bypass_delay)}\n"
            f"<b>Ð‘ÐµÐ· Ð²ÐµÑ€Ð¾ÑÑ‚Ð½Ð¾ÑÑ‚Ð¸:</b> {self._bool_text(target.bypass_probability)}\n"
            f"<b>Ð‘ÐµÐ· cooldown:</b> {self._bool_text(target.bypass_cooldown)}\n"
            f"<b>Ð¢Ð¾Ð»ÑŒÐºÐ¾ Ð²Ð¾Ð¿Ñ€Ð¾ÑÑ‹:</b> {self._bool_text(target.reply_only_questions)}\n"
            f"<b>Ð¢Ð¾Ð»ÑŒÐºÐ¾ Ð¿Ñ€Ð¸ Ð¾Ð±Ñ€Ð°Ñ‰ÐµÐ½Ð¸Ð¸ Ðº Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ñƒ:</b> {self._bool_text(target.require_owner_mention_or_context)}\n"
            f"<b>Ð§Ð°Ñ‚Ñ‹:</b> {chat_scope}"
            f"{overrides_text}"
        )

    def _render_style_panel(self, style_snapshot) -> str:
        tone = "Ð½ÐµÐ¹Ñ‚Ñ€Ð°Ð»ÑŒÐ½Ñ‹Ð¹"
        if style_snapshot.slang_score > style_snapshot.formality_score:
            tone = "Ð½ÐµÑ„Ð¾Ñ€Ð¼Ð°Ð»ÑŒÐ½Ñ‹Ð¹"
        if style_snapshot.formality_score > style_snapshot.slang_score + 0.1:
            tone = "Ñ„Ð¾Ñ€Ð¼Ð°Ð»ÑŒÐ½Ñ‹Ð¹"

        directness = "ÑÑ€ÐµÐ´Ð½ÑÑ"
        if style_snapshot.directness_score >= 0.45:
            directness = "Ð²Ñ‹ÑÐ¾ÐºÐ°Ñ"
        elif style_snapshot.directness_score < 0.2:
            directness = "Ð½Ð¸Ð·ÐºÐ°Ñ"

        verbosity = "ÑÐ±Ð°Ð»Ð°Ð½ÑÐ¸Ñ€Ð¾Ð²Ð°Ð½Ð½Ð°Ñ"
        if style_snapshot.average_words <= 8:
            verbosity = "ÐºÐ¾Ñ€Ð¾Ñ‚ÐºÐ°Ñ"
        elif style_snapshot.average_words >= 18:
            verbosity = "Ð¿Ð¾Ð´Ñ€Ð¾Ð±Ð½Ð°Ñ"

        return (
            "<b>ÐŸÑ€Ð¾Ñ„Ð¸Ð»ÑŒ ÑÑ‚Ð¸Ð»Ñ Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ð°</b>\n\n"
            f"<b>Ð¡Ð¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ð¹ Ð¿Ñ€Ð¾Ð°Ð½Ð°Ð»Ð¸Ð·Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¾:</b> {style_snapshot.analyzed_messages}\n"
            f"<b>Ð¡Ñ€ÐµÐ´Ð½ÑÑ Ð´Ð»Ð¸Ð½Ð°:</b> {style_snapshot.average_length:.1f} ÑÐ¸Ð¼Ð²Ð¾Ð»Ð¾Ð²\n"
            f"<b>Ð¡Ñ€ÐµÐ´Ð½ÐµÐµ Ñ‡Ð¸ÑÐ»Ð¾ ÑÐ»Ð¾Ð²:</b> {style_snapshot.average_words:.1f}\n"
            f"<b>Ð¢Ð¾Ð½:</b> {tone}\n"
            f"<b>ÐŸÑ€ÑÐ¼Ð¾Ñ‚Ð°:</b> {directness}\n"
            f"<b>ÐŸÐ¾Ð´Ñ€Ð¾Ð±Ð½Ð¾ÑÑ‚ÑŒ:</b> {verbosity}\n"
            f"<b>ÐŸÐ»Ð¾Ñ‚Ð½Ð¾ÑÑ‚ÑŒ Ð¿ÑƒÐ½ÐºÑ‚ÑƒÐ°Ñ†Ð¸Ð¸:</b> {style_snapshot.punctuation_density:.3f}\n"
            f"<b>ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¾:</b> {self._unknown(style_snapshot.last_updated)}"
        )

    def _render_model_line(self, model_name: str, snapshot: PersistentState) -> str:
        info = MODEL_BY_NAME.get(model_name)
        stage = model_stage_label(info.stage if info else "optional")
        enabled = self._bool_text(snapshot.enabled_models.get(model_name, True))
        flags: list[str] = [stage, enabled]
        if model_name == snapshot.active_model:
            flags.append("Ð³ÐµÐ½")
        if model_name == snapshot.judge_model:
            flags.append("ÑÑƒÐ´ÑŒÑ")
        limits = snapshot.model_limits.get(model_name, RateLimitState(model=model_name))
        req = self._format_limit_value(limits.remaining_requests, limits.request_limit)
        tok = self._format_limit_value(limits.remaining_tokens, limits.token_limit)
        return f"â€¢ <code>{html.escape(model_name)}</code> | {html.escape(', '.join(flags))} | req {html.escape(req)} | tok {html.escape(tok)}"

    def _build_main_markup(self, snapshot: PersistentState) -> InlineKeyboardMarkup:
        auto_reply_label = f"ÐÐ²Ñ‚Ð¾Ð¾Ñ‚Ð²ÐµÑ‚: {self._bool_text(snapshot.auto_reply_enabled)}"
        audience_summary = self._describe_audience_flags(snapshot.reply_audience_flags)
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Ð¡Ñ‚Ð°Ñ‚ÑƒÑ", callback_data="control_status"),
                    InlineKeyboardButton("ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ", callback_data="control_refresh"),
                ],
                [InlineKeyboardButton("Ð¡Ñ‚Ð¸Ð»ÑŒ", callback_data="control_style")],
                [
                    InlineKeyboardButton(
                        f"Ð ÐµÐ·ÐµÑ€Ð²: {self._bool_text(snapshot.fallback_enabled)}",
                        callback_data="control_fallback_toggle",
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"Ð ÐµÐ¶Ð¸Ð¼ AI: {self._bool_text(snapshot.ai_mode_enabled)}",
                        callback_data="control_ai_mode_toggle",
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"ÐšÐ¾Ð¼Ð°Ð½Ð´Ð½Ñ‹Ð¹ Ñ€ÐµÐ¶Ð¸Ð¼: {self._bool_text(snapshot.command_mode_enabled)}",
                        callback_data="control_command_toggle",
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"Ð ÐµÐ¶Ð¸Ð¼ Ð¾Ñ‚Ð²ÐµÑ‚Ð°: {snapshot.response_style_mode}",
                        callback_data="control_response_style_cycle",
                    )
                ],
                [
                    InlineKeyboardButton(
                        auto_reply_label, callback_data="control_autoreply_toggle"
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"ÐÑƒÐ´Ð¸Ñ‚Ð¾Ñ€Ð¸Ñ: {audience_summary}",
                        callback_data="control_audience_panel",
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"Ð¢Ð¾Ð»ÑŒÐºÐ¾ Ð²Ð¾Ð¿Ñ€Ð¾ÑÑ‹: {self._bool_text(snapshot.reply_only_questions)}",
                        callback_data="control_reply_only_questions_toggle",
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"ÐÑƒÐ¶Ð½Ð¾ Ð¾Ð±Ñ€Ð°Ñ‰ÐµÐ½Ð¸Ðµ Ðº Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ñƒ: {self._bool_text(snapshot.require_owner_mention_or_context)}",
                        callback_data="control_owner_context_toggle",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Ð§Ð°Ñ‚Ñ‹ Ð´Ð»Ñ Ð¾Ñ‚Ð²ÐµÑ‚Ð°", callback_data="control_chat_panel"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "ðŸ‘¥ ÐŸÐ¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ð¸", callback_data="control_user_panel"
                    )
                ],
                [InlineKeyboardButton("ÐœÐ¾Ð´ÐµÐ»Ð¸", callback_data="control_models")],
            ]
        )

    def _build_models_markup(self, snapshot: PersistentState) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Ð’Ñ‹Ð±Ñ€Ð°Ñ‚ÑŒ Ð³ÐµÐ½ÐµÑ€Ð°Ñ‚Ð¾Ñ€",
                        callback_data="control_models_select_active",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Ð’Ñ‹Ð±Ñ€Ð°Ñ‚ÑŒ Ð¼Ð¾Ð´ÐµÐ»ÑŒ-ÑÑƒÐ´ÑŒÑŽ",
                        callback_data="control_models_select_judge",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Ð’ÐºÐ»/Ð²Ñ‹ÐºÐ» Ð¼Ð¾Ð´ÐµÐ»Ð¸", callback_data="control_models_toggle_panel"
                    )
                ],
                [InlineKeyboardButton("ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ Ð¿ÑƒÐ»", callback_data="control_refresh")],
                [InlineKeyboardButton("ÐÐ°Ð·Ð°Ð´", callback_data="control_back_main")],
            ]
        )

    def _build_model_selection_markup(
        self, snapshot: PersistentState, mode: str
    ) -> InlineKeyboardMarkup:
        if mode == "active":
            prefix = MODEL_ACTIVE_PREFIX
        elif mode == "judge":
            prefix = MODEL_JUDGE_PREFIX
        else:
            prefix = MODEL_TOGGLE_PREFIX

        rows: list[list[InlineKeyboardButton]] = []
        for index, model_name in enumerate(snapshot.available_models):
            if mode == "active":
                marker = "* " if model_name == snapshot.active_model else ""
            elif mode == "judge":
                marker = "* " if model_name == snapshot.judge_model else ""
            else:
                marker = (
                    "ON " if snapshot.enabled_models.get(model_name, True) else "OFF "
                )
            rows.append(
                [
                    InlineKeyboardButton(
                        f"{marker}{model_name}"[:64], callback_data=f"{prefix}{index}"
                    )
                ]
            )
        rows.append(
            [InlineKeyboardButton("ÐÐ°Ð·Ð°Ð´", callback_data="control_back_models")]
        )
        return InlineKeyboardMarkup(rows)

    def _build_chat_panel_markup(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "ÐŸÐ¾ÐºÐ°Ð·Ð°Ñ‚ÑŒ Ñ€Ð°Ð·Ñ€ÐµÑˆÑ‘Ð½Ð½Ñ‹Ðµ", callback_data="control_chat_show"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ñ‡Ð°Ñ‚Ñ‹", callback_data="control_chat_add"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Ð£Ð±Ñ€Ð°Ñ‚ÑŒ Ñ‡Ð°Ñ‚Ñ‹", callback_data="control_chat_remove"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Ð¡Ð¿ÐµÑ†-Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ð¸", callback_data="control_special_panel"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Ð‘Ð»Ð¸Ð·ÐºÐ¸Ðµ Ð¸ Ð²Ð°Ð¶Ð½Ñ‹Ðµ", callback_data="control_close_panel"
                    )
                ],
                [InlineKeyboardButton("ÐÐ°Ð·Ð°Ð´", callback_data="control_back_main")],
            ]
        )

    def _build_chat_input_markup(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "ÐžÑ‚Ð¼ÐµÐ½Ð°", callback_data="control_cancel_input"
                    ),
                    InlineKeyboardButton("ÐÐ°Ð·Ð°Ð´", callback_data="control_back_chat"),
                ]
            ]
        )

    def _build_audience_markup(self, flags: dict[str, bool]) -> InlineKeyboardMarkup:
        if not isinstance(flags, dict):
            flags = {}
        categories = [
            ("STRANGERS", "ÐÐµÐ·Ð½Ð°ÐºÐ¾Ð¼Ñ†Ñ‹"),
            ("KNOWN", "Ð—Ð½Ð°ÐºÐ¾Ð¼Ñ‹Ðµ"),
            ("FRIENDS", "Ð”Ñ€ÑƒÐ·ÑŒÑ"),
            ("BUSINESS", "ÐŸÐ¾ Ð´ÐµÐ»Ñƒ"),
        ]
        rows: list[list[InlineKeyboardButton]] = []
        for key, label in categories:
            enabled = flags.get(key, True)
            status = "âœ“ Ð¾Ñ‚Ð²ÐµÑ‡Ð°Ñ‚ÑŒ" if enabled else "âœ— Ð¼Ð¾Ð»Ñ‡Ð°Ñ‚ÑŒ"
            rows.append(
                [
                    InlineKeyboardButton(
                        f"{label}: {status}",
                        callback_data=f"control_audience_toggle_{key}",
                    )
                ]
            )
        rows.append([InlineKeyboardButton("ÐÐ°Ð·Ð°Ð´", callback_data="control_back_main")])
        return InlineKeyboardMarkup(rows)

    async def _build_special_targets_markup(
        self, page: int = 0
    ) -> InlineKeyboardMarkup:
        targets = await self._user_memory_store.get_special_targets_snapshot()
        rows: list[list[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(
                    "ÐŸÐ¾ÐºÐ°Ð·Ð°Ñ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº", callback_data="control_special_show"
                )
            ],
            [
                InlineKeyboardButton(
                    "Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ", callback_data="control_special_add"
                )
            ],
            [
                InlineKeyboardButton(
                    "Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ", callback_data="control_special_remove"
                )
            ],
        ]
        ordered = list(sorted(targets.items(), key=lambda item: item[0]))
        items, page, total_pages = self._paginate_pairs(ordered, page)
        for user_id, target in items:
            label = f"@{target.username}" if target.username else f"user {user_id}"
            rows.append(
                [
                    InlineKeyboardButton(
                        label[:60], callback_data=f"{SPECIAL_TARGET_PREFIX}{user_id}"
                    )
                ]
            )
        pagination_row = self._build_pagination_row(
            page, total_pages, SPECIAL_TARGET_PAGE_PREFIX
        )
        if pagination_row:
            rows.append(pagination_row)
        rows.append([InlineKeyboardButton("ÐÐ°Ð·Ð°Ð´", callback_data="control_back_chat")])
        return InlineKeyboardMarkup(rows)

    async def _build_close_contacts_markup(self, page: int = 0) -> InlineKeyboardMarkup:
        contacts = await self._user_memory_store.get_close_contacts_snapshot()
        rows: list[list[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(
                    "ÐŸÐ¾ÐºÐ°Ð·Ð°Ñ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº", callback_data="control_close_show"
                )
            ],
            [
                InlineKeyboardButton(
                    "Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ñ‡ÐµÐ»Ð¾Ð²ÐµÐºÐ°", callback_data="control_close_add"
                )
            ],
            [
                InlineKeyboardButton(
                    "Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ñ‡ÐµÐ»Ð¾Ð²ÐµÐºÐ°", callback_data="control_close_remove"
                )
            ],
        ]
        ordered = list(sorted(contacts.items(), key=lambda item: item[0]))
        items, page, total_pages = self._paginate_pairs(ordered, page)
        for user_id, contact in items:
            label = f"@{contact.username}" if contact.username else f"user {user_id}"
            rows.append(
                [
                    InlineKeyboardButton(
                        label[:60], callback_data=f"{CLOSE_CONTACT_PREFIX}{user_id}"
                    )
                ]
            )
        pagination_row = self._build_pagination_row(
            page, total_pages, CLOSE_CONTACT_PAGE_PREFIX
        )
        if pagination_row:
            rows.append(pagination_row)
        rows.append([InlineKeyboardButton("ÐÐ°Ð·Ð°Ð´", callback_data="control_back_chat")])
        return InlineKeyboardMarkup(rows)

    async def _build_close_contact_detail_markup(
        self, user_id: int
    ) -> InlineKeyboardMarkup:
        contact = await self._user_memory_store.get_close_contact(user_id)
        role_label = (
            f"Ð Ð¾Ð»ÑŒ: {self._describe_close_contact_relation(contact.relation_type)}"
            if contact is not None
            else "Ð¡Ð¼ÐµÐ½Ð¸Ñ‚ÑŒ Ñ€Ð¾Ð»ÑŒ"
        )
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        role_label[:64],
                        callback_data=f"{CLOSE_CONTACT_ROLE_PREFIX}{user_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Ð˜Ð·Ð¼ÐµÐ½Ð¸Ñ‚ÑŒ ÐºÐ¾Ð¼Ð¼ÐµÐ½Ñ‚Ð°Ñ€Ð¸Ð¹",
                        callback_data=f"{CLOSE_CONTACT_COMMENT_PREFIX}{user_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ",
                        callback_data=f"{CLOSE_CONTACT_DELETE_PREFIX}{user_id}",
                    )
                ],
                [InlineKeyboardButton("ÐÐ°Ð·Ð°Ð´", callback_data="control_back_close")],
            ]
        )

    def _build_back_markup(self, callback_data: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("ÐÐ°Ð·Ð°Ð´", callback_data=callback_data)]]
        )

    def _model_name_from_callback(
        self, data: str, snapshot: PersistentState, prefix: str
    ) -> str | None:
        index_text = data.removeprefix(prefix)
        if not index_text.isdigit():
            return None
        index = int(index_text)
        if index < 0 or index >= len(snapshot.available_models):
            return None
        return snapshot.available_models[index]

    def _special_target_user_id_from_callback(
        self, data: str, prefix: str
    ) -> int | None:
        value = data.removeprefix(prefix)
        if not value.isdigit():
            return None
        return int(value)

    def _format_limit_value(self, remaining: str | None, limit: str | None) -> str:
        if remaining and limit:
            return f"{remaining}/{limit}"
        if remaining:
            return remaining
        return "unknown"

    async def _render_user_panel(self, page: int = 0) -> str:
        entries = await self._get_user_panel_entries()
        pairs, safe_page, total_pages = self._paginate_pairs(entries, page)
        lines = [
            f"<b>ðŸ‘¥ ÐŸÐ¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ð¸</b> (ÑÑ‚Ñ€. {safe_page + 1}/{total_pages}, Ð²ÑÐµÐ³Ð¾ {len(entries)})\n"
        ]
        if not pairs:
            lines.append("ÐÐµÑ‚ Ð·Ð°Ð¿Ð¸ÑÐµÐ¹ Ð¾ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑÑ….")
        else:
            for uid, label in pairs:
                blocked = await self._is_user_blocked(uid)
                status = " ðŸš«" if blocked else ""
                lines.append(f"â€¢ {html.escape(label)}{status} â€” <code>{uid}</code>")
        return "\n".join(lines)

    async def _build_user_panel_markup(self, page: int = 0) -> InlineKeyboardMarkup:
        entries = await self._get_user_panel_entries()
        pairs, safe_page, total_pages = self._paginate_pairs(entries, page)
        rows: list[list[InlineKeyboardButton]] = []
        for uid, label in pairs:
            short = label[:28]
            rows.append(
                [InlineKeyboardButton(short, callback_data=f"{USER_PANEL_PREFIX}{uid}")]
            )
        pagination = self._build_pagination_row(
            safe_page, total_pages, USER_PANEL_PAGE_PREFIX
        )
        if pagination:
            rows.append(pagination)
        rows.append([InlineKeyboardButton("ÐÐ°Ð·Ð°Ð´", callback_data="control_back_main")])
        return InlineKeyboardMarkup(rows)

    async def _render_user_detail(self, user_id: int) -> str:
        label = await self._get_user_label(user_id)
        blocked = await self._is_user_blocked(user_id)
        is_special = (
            await self._user_memory_store.get_special_target(user_id)
        ) is not None
        is_close = (
            await self._user_memory_store.get_close_contact(user_id)
        ) is not None
        profile = await self._user_memory_store.get_profile(user_id)

        lines = [f"<b>ðŸ‘¤ {html.escape(label)}</b>", f"ID: <code>{user_id}</code>", ""]
        lines.append(f"ÐžÑ‚Ð²ÐµÑ‚Ñ‹: {'ðŸš« Ð¾Ñ‚ÐºÐ»ÑŽÑ‡ÐµÐ½Ñ‹' if blocked else 'âœ… Ð²ÐºÐ»ÑŽÑ‡ÐµÐ½Ñ‹'}")
        lines.append(f"Ð¡Ð¿ÐµÑ†. Ñ†ÐµÐ»ÑŒ: {'Ð´Ð° âœ“' if is_special else 'Ð½ÐµÑ‚'}")
        lines.append(f"Ð‘Ð»Ð¸Ð·ÐºÐ¸Ð¹ ÐºÐ¾Ð½Ñ‚Ð°ÐºÑ‚: {'Ð´Ð° âœ“' if is_close else 'Ð½ÐµÑ‚'}")
        if profile and profile.message_count > 0:
            lines.append(f"Ð¡Ð¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ð¹: {profile.message_count}")
            lines.append(f"Ð¢Ð¾Ð½: {profile.typical_tone}")
        return "\n".join(lines)

    def _build_user_detail_markup(self, user_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "ðŸš« Ð—Ð°Ð±Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ",
                        callback_data=f"{USER_BLOCK_PREFIX}{user_id}",
                    ),
                    InlineKeyboardButton(
                        "âœ… Ð Ð°Ð·Ð±Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ",
                        callback_data=f"{USER_UNBLOCK_PREFIX}{user_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "â­ Ð¡Ð¿ÐµÑ†. Ñ†ÐµÐ»ÑŒ",
                        callback_data=f"{SPECIAL_TARGET_PREFIX}{user_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "ðŸ’¬ Ð‘Ð»Ð¸Ð·ÐºÐ¸Ð¹ ÐºÐ¾Ð½Ñ‚Ð°ÐºÑ‚",
                        callback_data=f"{CLOSE_CONTACT_PREFIX}{user_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "ÐÐ°Ð·Ð°Ð´ Ðº ÑÐ¿Ð¸ÑÐºÑƒ", callback_data="control_user_panel"
                    )
                ],
            ]
        )

    async def _get_user_panel_entries(self) -> list[tuple[int, str]]:
        """Get all known users from entity_memory and user_memory combined."""
        seen: dict[int, str] = {}
        # From user_memory profiles
        profiles = await self._user_memory_store.get_all_profiles()
        for uid_str, profile in profiles.items():
            try:
                uid = int(uid_str)
            except ValueError:
                continue
            label = f"@{profile.username}" if profile.username else f"user_{uid}"
            seen[uid] = label
        # From entity_memory
        if self._entity_memory_store is not None:
            em_entries = await self._entity_memory_store.get_all_entries_raw()
            for uid_str, entry in em_entries.items():
                try:
                    uid = int(uid_str)
                except ValueError:
                    continue
                label = (
                    f"@{entry.username}"
                    if entry.username
                    else (entry.display_name or f"user_{uid}")
                )
                seen.setdefault(uid, label)
        # From special targets
        special = await self._user_memory_store.get_special_targets_snapshot()
        for uid_str, target in special.items():
            try:
                uid = int(uid_str)
            except ValueError:
                continue
            label = f"@{target.username}" if target.username else f"user_{uid}"
            seen.setdefault(uid, label)
        return sorted(seen.items(), key=lambda x: str(x[1]).lower())

    async def _get_user_label(self, user_id: int) -> str:
        special = await self._user_memory_store.get_special_target(user_id)
        if special and special.username:
            return f"@{special.username}"
        if self._entity_memory_store is not None and hasattr(
            self._entity_memory_store, "build_context_for_target"
        ):
            entry_label = None
            try:
                em = await self._entity_memory_store.build_context_for_target(
                    user_id=user_id
                )
                if em:
                    entry_label = (
                        em.split("\n")[0]
                        .replace("Known profile info about the current person:", "")
                        .strip()
                    )
            except Exception:
                pass
            if entry_label:
                return entry_label
        profile = await self._user_memory_store.get_profile(user_id)
        if profile and profile.username:
            return f"@{profile.username}"
        return f"user_{user_id}"

    async def _is_user_blocked(self, user_id: int) -> bool:
        if self._owner_directives_store is None:
            return False
        decision = await self._owner_directives_store.resolve_sender(
            user_id=user_id,
            username=None,
            display_name=None,
        )
        return not decision.reply_enabled

    def _bool_text(self, value: bool) -> str:
        return "Ð’ÐšÐ›" if value else "Ð’Ð«ÐšÐ›"

    def _unknown(self, value: str | None) -> str:
        return html.escape(value or "unknown")

    def _page_from_callback(self, data: str, prefix: str) -> int:
        value = data.removeprefix(prefix)
        return int(value) if value.isdigit() else 0

    def _paginate_pairs(
        self, pairs: list[tuple], page: int
    ) -> tuple[list[tuple], int, int]:
        total = len(pairs)
        total_pages = max(1, (total + LIST_PAGE_SIZE - 1) // LIST_PAGE_SIZE)
        safe_page = max(0, min(page, total_pages - 1))
        start = safe_page * LIST_PAGE_SIZE
        end = start + LIST_PAGE_SIZE
        return pairs[start:end], safe_page, total_pages

    def _build_pagination_row(
        self, page: int, total_pages: int, prefix: str
    ) -> list[InlineKeyboardButton] | None:
        if total_pages <= 1:
            return None
        row: list[InlineKeyboardButton] = []
        if page > 0:
            row.append(InlineKeyboardButton("â†", callback_data=f"{prefix}{page - 1}"))
        row.append(
            InlineKeyboardButton(
                f"{page + 1}/{total_pages}", callback_data=f"{prefix}{page}"
            )
        )
        if page + 1 < total_pages:
            row.append(InlineKeyboardButton("â†’", callback_data=f"{prefix}{page + 1}"))
        return row

    def _normalize_close_contact_relation(self, value: str) -> str | None:
        normalized = " ".join(
            self._sanitize_structured_input_line(str(value or ""))
            .strip()
            .casefold()
            .split()
        )
        mapping = {
            "Ð±Ð»Ð¸Ð·ÐºÐ¸Ð¹": "CLOSE",
            "close": "CLOSE",
            "Ð¾Ñ‡ÐµÐ½ÑŒ Ð±Ð»Ð¸Ð·ÐºÐ¸Ð¹": "CLOSE",
            "Ð¼ÐµÐ½ÐµÐµ Ð±Ð»Ð¸Ð·ÐºÐ¸Ð¹": "LESS_CLOSE",
            "Ð½Ðµ Ð¾Ñ‡ÐµÐ½ÑŒ Ð±Ð»Ð¸Ð·ÐºÐ¸Ð¹": "LESS_CLOSE",
            "Ð·Ð½Ð°ÐºÐ¾Ð¼Ñ‹Ð¹": "LESS_CLOSE",
            "less_close": "LESS_CLOSE",
            "less close": "LESS_CLOSE",
            "Ð¿Ð»Ð°Ð½Ñ‹": "PLANS",
            "Ð´Ð»Ñ Ð¿Ð»Ð°Ð½Ð¾Ð²": "PLANS",
            "plans": "PLANS",
            "Ð´ÐµÐ»Ð¾": "BUSINESS",
            "Ð¿Ð¾ Ð´ÐµÐ»Ñƒ": "BUSINESS",
            "Ð´ÐµÐ»Ð¾Ð²Ð¾Ð¹": "BUSINESS",
            "business": "BUSINESS",
        }
        return mapping.get(normalized)

    def _sanitize_structured_input_line(self, value: str) -> str:
        cleaned = str(value or "").strip()
        cleaned = re.sub(r"^\s*(?:\d+\s*[\)\.\-:]+|[-â€¢*]+)\s*", "", cleaned)
        return cleaned.strip()

    def _describe_close_contact_relation(self, relation_type: str | None) -> str:
        labels = {
            "CLOSE": "Ð±Ð»Ð¸Ð·ÐºÐ¸Ð¹",
            "LESS_CLOSE": "Ð¼ÐµÐ½ÐµÐµ Ð±Ð»Ð¸Ð·ÐºÐ¸Ð¹",
            "PLANS": "Ð½ÑƒÐ¶ÐµÐ½ Ð½Ð° Ð¿Ð»Ð°Ð½Ñ‹",
            "BUSINESS": "Ð¿Ð¾ Ð´ÐµÐ»Ñƒ / ÑÐµÑ€ÑŒÑ‘Ð·Ð½Ð¾",
        }
        return labels.get(
            str(relation_type or "LESS_CLOSE").strip().upper(), "Ð¼ÐµÐ½ÐµÐµ Ð±Ð»Ð¸Ð·ÐºÐ¸Ð¹"
        )

    def _next_close_contact_relation(self, current: str | None) -> str:
        modes = ["CLOSE", "LESS_CLOSE", "PLANS", "BUSINESS"]
        normalized = str(current or "LESS_CLOSE").strip().upper()
        if normalized not in modes:
            return "LESS_CLOSE"
        return modes[(modes.index(normalized) + 1) % len(modes)]

    def _now_text(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _describe_special_target_trigger_mode(
        self, target: SpecialTargetSettings
    ) -> str:
        if target.reply_only_questions and target.require_owner_mention_or_context:
            return "Ð²Ð¾Ð¿Ñ€Ð¾ÑÑ‹/Ð·Ð°Ð¿Ñ€Ð¾ÑÑ‹ Ð¸ Ð¾Ð±Ñ€Ð°Ñ‰ÐµÐ½Ð¸Ðµ Ðº Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ñƒ"
        if target.reply_only_questions:
            return "Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð²Ð¾Ð¿Ñ€Ð¾ÑÑ‹/Ð·Ð°Ð¿Ñ€Ð¾ÑÑ‹"
        if target.require_owner_mention_or_context:
            return "Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð¿Ñ€Ð¸ Ð¾Ð±Ñ€Ð°Ñ‰ÐµÐ½Ð¸Ð¸ Ðº Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ñƒ/Ð¿Ð¾ ÐºÐ¾Ð½Ñ‚ÐµÐºÑÑ‚Ñƒ"
        return "Ð»ÑŽÐ±Ñ‹Ðµ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ"

    def _describe_reply_audience_mode(self, mode: str | None) -> str:
        normalized = str(mode or "ALL").strip().upper()
        labels = {
            "ALL": "Ð²ÑÐµÐ¼",
            "FRIENDS": "Ð´Ñ€ÑƒÐ·ÑŒÑÐ¼",
            "KNOWN": "Ð·Ð½Ð°ÐºÐ¾Ð¼Ñ‹Ð¼",
            "STRANGERS": "Ð½ÐµÐ·Ð½Ð°ÐºÐ¾Ð¼Ñ†Ð°Ð¼",
            "BUSINESS": "Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð¿Ð¾ Ð´ÐµÐ»Ñƒ",
        }
        return labels.get(normalized, "Ð²ÑÐµÐ¼")

    def _describe_audience_flags(self, flags: dict[str, bool] | None) -> str:
        if not isinstance(flags, dict):
            flags = {}
        parts = []
        labels = {
            "STRANGERS": "ÐÐµÐ·Ð½Ð°ÐºÐ¾Ð¼Ñ†Ñ‹",
            "KNOWN": "Ð—Ð½Ð°ÐºÐ¾Ð¼Ñ‹Ðµ",
            "FRIENDS": "Ð”Ñ€ÑƒÐ·ÑŒÑ",
            "BUSINESS": "ÐŸÐ¾ Ð´ÐµÐ»Ñƒ",
        }
        for key, label in labels.items():
            if flags.get(key, True):
                parts.append(label)
        if not parts:
            return "Ð½Ð¸ÐºÐ¾Ð¼Ñƒ"
        return ", ".join(parts)

    def _next_response_style_mode(self, current: str | None) -> str:
        modes = ["SHORT", "NORMAL", "DETAILED", "HUMANLIKE", "SAFE"]
        normalized = str(current or "NORMAL").strip().upper()
        if normalized not in modes:
            return "NORMAL"
        return modes[(modes.index(normalized) + 1) % len(modes)]

    def _next_reply_audience_mode(self, current: str | None) -> str:
        normalized = str(current or "ALL").strip().upper()
        if normalized not in REPLY_AUDIENCE_MODES:
            return "ALL"
        return REPLY_AUDIENCE_MODES[
            (REPLY_AUDIENCE_MODES.index(normalized) + 1) % len(REPLY_AUDIENCE_MODES)
        ]

    def _render_special_target_input_prompt(
        self, action: str, errors: list[str] | None = None
    ) -> str:
        if action == "special_add":
            title = "Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ñ‡ÐµÐ»Ð¾Ð²ÐµÐºÐ°"
            hint = "ÐŸÑ€Ð¸ÑˆÐ»Ð¸ `user_id` Ð¸Ð»Ð¸ `@username`."
        elif action == "special_remove":
            title = "Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ñ‡ÐµÐ»Ð¾Ð²ÐµÐºÐ°"
            hint = "ÐŸÑ€Ð¸ÑˆÐ»Ð¸ `user_id` Ð¸Ð»Ð¸ `@username`."
        else:
            title = "Ð§Ð°Ñ‚Ñ‹ Ð´Ð»Ñ Ð¾Ñ‚Ð²ÐµÑ‚Ð° ÑÑ‚Ð¾Ð¼Ñƒ Ñ‡ÐµÐ»Ð¾Ð²ÐµÐºÑƒ"
            hint = "ÐŸÑ€Ð¸ÑˆÐ»Ð¸ chat_id / ÑÑÑ‹Ð»ÐºÑƒ / @username Ñ‡Ð°Ñ‚Ð° Ñ‡ÐµÑ€ÐµÐ· Ð¿Ñ€Ð¾Ð±ÐµÐ» Ð¸Ð»Ð¸ Ð½Ð¾Ð²ÑƒÑŽ ÑÑ‚Ñ€Ð¾ÐºÑƒ. Ð›Ð¡ Ñ‚Ð¾Ð¶Ðµ ÑÑ‡Ð¸Ñ‚Ð°ÐµÑ‚ÑÑ Ð¾Ð±Ñ‹Ñ‡Ð½Ñ‹Ð¼ Ñ‡Ð°Ñ‚Ð¾Ð¼ Ð¸ Ð½Ð°ÑÑ‚Ñ€Ð°Ð¸Ð²Ð°ÐµÑ‚ÑÑ Ñ‚Ð°Ðº Ð¶Ðµ Ñ‡ÐµÑ€ÐµÐ· chat_id."
        lines = [f"<b>{title}</b>", "", hint]
        if errors:
            lines.extend(["", "<b>ÐžÑˆÐ¸Ð±ÐºÐ¸:</b>"])
            lines.extend(f"â€¢ {html.escape(error)}" for error in errors[:8])
        return "\n".join(lines)

    async def _render_special_target_detail(self, user_id: int) -> str:
        target = await self._user_memory_store.get_special_target(user_id)
        if target is None:
            return "<b>ÐŸÐ¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑŒ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½</b>"
        label = f"@{target.username}" if target.username else f"user_id {user_id}"
        reply_mode = "Ñ‡ÐµÐ»Ð¾Ð²ÐµÐº" if target.human_like else "Ð¸Ð¸"
        trigger_mode = self._describe_special_target_trigger_mode(target)
        if target.allowed_chat_ids:
            chat_scope = ", ".join(
                f"<code>{chat_id}</code>" for chat_id in target.allowed_chat_ids[:12]
            )
        else:
            chat_scope = "Ð½Ðµ Ð½Ð°ÑÑ‚Ñ€Ð¾ÐµÐ½Ñ‹"
        return (
            "<b>ÐÐ°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ð¾Ñ‚Ð²ÐµÑ‚Ð° Ð´Ð»Ñ Ñ‡ÐµÐ»Ð¾Ð²ÐµÐºÐ°</b>\n\n"
            f"<b>User:</b> {html.escape(label)}\n"
            f"<b>ID:</b> <code>{user_id}</code>\n"
            f"<b>Ð’ÐºÐ»ÑŽÑ‡Ñ‘Ð½:</b> {self._bool_text(target.enabled)}\n"
            f"<b>Ð ÐµÐ¶Ð¸Ð¼ Ð¾Ñ‚Ð²ÐµÑ‚Ð°:</b> {reply_mode}\n"
            f"<b>ÐÐ° Ñ‡Ñ‚Ð¾ Ð¾Ñ‚Ð²ÐµÑ‡Ð°Ñ‚ÑŒ:</b> {html.escape(trigger_mode)}\n"
            f"<b>Ð¢Ð¾Ð»ÑŒÐºÐ¾ Ð²Ð¾Ð¿Ñ€Ð¾ÑÑ‹/Ð·Ð°Ð¿Ñ€Ð¾ÑÑ‹:</b> {self._bool_text(target.reply_only_questions)}\n"
            f"<b>Ð¢Ð¾Ð»ÑŒÐºÐ¾ Ð¿Ñ€Ð¸ Ð¾Ð±Ñ€Ð°Ñ‰ÐµÐ½Ð¸Ð¸ Ðº Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ñƒ/Ð¿Ð¾ ÐºÐ¾Ð½Ñ‚ÐµÐºÑÑ‚Ñƒ:</b> {self._bool_text(target.require_owner_mention_or_context)}\n"
            f"<b>Ð‘ÐµÐ· Ð·Ð°Ð´ÐµÑ€Ð¶ÐºÐ¸:</b> {self._bool_text(target.bypass_delay)}\n"
            f"<b>Ð‘ÐµÐ· Ð²ÐµÑ€Ð¾ÑÑ‚Ð½Ð¾ÑÑ‚Ð¸:</b> {self._bool_text(target.bypass_probability)}\n"
            f"<b>Ð‘ÐµÐ· cooldown:</b> {self._bool_text(target.bypass_cooldown)}\n"
            f"<b>Ð§Ð°Ñ‚Ñ‹ Ð´Ð»Ñ Ð¾Ñ‚Ð²ÐµÑ‚Ð°:</b> {chat_scope}\n"
            "<b>ÐŸÑ€Ð¸Ð¼ÐµÑ‡Ð°Ð½Ð¸Ðµ:</b> ÐµÑÐ»Ð¸ Ñ‡Ð°Ñ‚Ñ‹ Ð½Ðµ Ð·Ð°Ð´Ð°Ð½Ñ‹, ÑÑ‚Ð¾Ñ‚ Ñ€ÐµÐ¶Ð¸Ð¼ Ð½Ðµ ÑÑ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÑ‚."
        )

    async def _build_special_target_detail_markup(
        self, user_id: int
    ) -> InlineKeyboardMarkup:
        target = await self._user_memory_store.get_special_target(user_id)
        mode_label = (
            "Ð ÐµÐ¶Ð¸Ð¼: Ñ‡ÐµÐ»Ð¾Ð²ÐµÐº"
            if target is not None and target.human_like
            else "Ð ÐµÐ¶Ð¸Ð¼: Ð¸Ð¸"
        )
        questions_label = (
            "ÐžÑ‚Ð²ÐµÑ‡Ð°Ñ‚ÑŒ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð½Ð° Ð²Ð¾Ð¿Ñ€Ð¾ÑÑ‹/Ð·Ð°Ð¿Ñ€Ð¾ÑÑ‹: Ð´Ð°"
            if target is not None and target.reply_only_questions
            else "ÐžÑ‚Ð²ÐµÑ‡Ð°Ñ‚ÑŒ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð½Ð° Ð²Ð¾Ð¿Ñ€Ð¾ÑÑ‹/Ð·Ð°Ð¿Ñ€Ð¾ÑÑ‹: Ð½ÐµÑ‚"
        )
        mention_label = (
            "Ð¢Ð¾Ð»ÑŒÐºÐ¾ Ð¿Ñ€Ð¸ Ð¾Ð±Ñ€Ð°Ñ‰ÐµÐ½Ð¸Ð¸ Ðº Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ñƒ: Ð´Ð°"
            if target is not None and target.require_owner_mention_or_context
            else "Ð¢Ð¾Ð»ÑŒÐºÐ¾ Ð¿Ñ€Ð¸ Ð¾Ð±Ñ€Ð°Ñ‰ÐµÐ½Ð¸Ð¸ Ðº Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ñƒ: Ð½ÐµÑ‚"
        )
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Ð’ÐºÐ»/Ð²Ñ‹ÐºÐ»",
                        callback_data=f"{SPECIAL_TARGET_TOGGLE_PREFIX}{SPECIAL_TARGET_FLAG_CODES['enabled']}_{user_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        mode_label,
                        callback_data=f"{SPECIAL_TARGET_TOGGLE_PREFIX}{SPECIAL_TARGET_FLAG_CODES['human_like']}_{user_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        questions_label,
                        callback_data=f"{SPECIAL_TARGET_TOGGLE_PREFIX}{SPECIAL_TARGET_FLAG_CODES['reply_only_questions']}_{user_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        mention_label,
                        callback_data=f"{SPECIAL_TARGET_TOGGLE_PREFIX}{SPECIAL_TARGET_FLAG_CODES['require_owner_mention_or_context']}_{user_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Bypass delay",
                        callback_data=f"{SPECIAL_TARGET_TOGGLE_PREFIX}{SPECIAL_TARGET_FLAG_CODES['bypass_delay']}_{user_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Bypass probability",
                        callback_data=f"{SPECIAL_TARGET_TOGGLE_PREFIX}{SPECIAL_TARGET_FLAG_CODES['bypass_probability']}_{user_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Bypass cooldown",
                        callback_data=f"{SPECIAL_TARGET_TOGGLE_PREFIX}{SPECIAL_TARGET_FLAG_CODES['bypass_cooldown']}_{user_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"ÐÐ²Ñ‚Ð¾Ñ‚Ñ€Ð°Ð½ÑÐºÑ€Ð¸Ð¿Ñ†Ð¸Ñ: {'Ð´Ð°' if target is not None and target.auto_transcribe else 'Ð½ÐµÑ‚'}",
                        callback_data=f"{SPECIAL_TARGET_TOGGLE_PREFIX}{SPECIAL_TARGET_FLAG_CODES['auto_transcribe']}_{user_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "Ð§Ð°Ñ‚Ñ‹ Ð´Ð»Ñ Ð¾Ñ‚Ð²ÐµÑ‚Ð°",
                        callback_data=f"control_special_chats_{user_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "âš™ï¸ Per-chat Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸",
                        callback_data=f"control_special_perchat_{user_id}",
                    )
                ],
                [InlineKeyboardButton("ÐÐ°Ð·Ð°Ð´", callback_data="control_back_special")],
            ]
        )

    def _render_perchat_input_prompt(
        self, user_id: int, errors: list[str] | None = None
    ) -> str:
        lines = [
            "<b>Per-chat Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸</b>",
            "",
            "Ð¤Ð¾Ñ€Ð¼Ð°Ñ‚: <code>chat_id Ñ„Ð»Ð°Ð³=Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ðµ</code>",
            "Ð¤Ð»Ð°Ð³Ð¸: <code>require=true/false</code>, <code>questions=true/false</code>, <code>human=true/false</code>",
            "ÐžÑ‡Ð¸ÑÑ‚Ð¸Ñ‚ÑŒ: <code>clear chat_id</code>",
            "",
            "ÐŸÑ€Ð¸Ð¼ÐµÑ€Ñ‹:",
            "<code>2260613420 require=false</code> â€” Ð² ÑÑ‚Ð¾Ð¼ Ñ‡Ð°Ñ‚Ðµ Ð¾Ñ‚Ð²ÐµÑ‡Ð°Ñ‚ÑŒ Ð±ÐµÐ· ÑƒÐ¿Ð¾Ð¼Ð¸Ð½Ð°Ð½Ð¸Ñ",
            "<code>-1001234567890 require=true questions=true</code> â€” Ð² Ð³Ñ€ÑƒÐ¿Ð¿Ðµ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð²Ð¾Ð¿Ñ€Ð¾ÑÑ‹",
            "<code>clear 2260613420</code> â€” ÑƒÐ±Ñ€Ð°Ñ‚ÑŒ Ð¿ÐµÑ€ÐµÐ¾Ð¿Ñ€ÐµÐ´ÐµÐ»ÐµÐ½Ð¸Ñ Ð´Ð»Ñ Ñ‡Ð°Ñ‚Ð°",
        ]
        if errors:
            lines += ["", "<b>ÐžÑˆÐ¸Ð±ÐºÐ¸:</b>"] + [f"â€¢ {html.escape(e)}" for e in errors]
        return "\n".join(lines)

    def _is_owner(self, user_id: int | None) -> bool:
        return bool(user_id) and user_id == self._config.owner_user_id

