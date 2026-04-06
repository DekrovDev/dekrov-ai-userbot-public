from __future__ import annotations

"""
visitor_admin.py â€” Admin panel for the visitor/public assistant module.

Provides:
  - Live session stats (active users, message counts, uptime)
  - Per-session breakdown (who's chatting, how long, what topics)
  - Topic analytics (what visitors ask about most)
  - Session management (kick user, clear all sessions)
  - Broadcast message to all active visitors
  - Quiet mode toggle (disables AI responses, shows maintenance message)

Usage (in owner handler):
    from visitor.visitor_admin import VisitorAdminPanel
    panel = VisitorAdminPanel(visitor_service)
    text, kb = await panel.handle_callback("vadmin_stats")
"""

import logging
import time
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .visitor_service import VisitorService

LOGGER = logging.getLogger("assistant.visitor.admin")

# Human-readable category names
_CATEGORY_LABELS: dict[str, str] = {
    "about_owner": "Ðž Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ðµ",
    "about_projects": "ÐŸÑ€Ð¾ÐµÐºÑ‚Ñ‹",
    "technical_question": "Ð¢ÐµÑ…Ð½Ð¸Ñ‡ÐµÑÐºÐ¸Ðµ Ð²Ð¾Ð¿Ñ€Ð¾ÑÑ‹",
    "project_specific_question": "Ð”ÐµÑ‚Ð°Ð»Ð¸ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð¾Ð²",
    "faq": "FAQ",
    "collaboration": "Ð¡Ð¾Ñ‚Ñ€ÑƒÐ´Ð½Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾",
    "links": "Ð¡ÑÑ‹Ð»ÐºÐ¸",
    "assistant_capabilities": "Ð’Ð¾Ð·Ð¼Ð¾Ð¶Ð½Ð¾ÑÑ‚Ð¸",
    "greeting": "ÐŸÑ€Ð¸Ð²ÐµÑ‚ÑÑ‚Ð²Ð¸Ðµ",
    "general": "ÐžÐ±Ñ‰Ð¸Ðµ Ð²Ð¾Ð¿Ñ€Ð¾ÑÑ‹",
    "disallowed_offtopic": "ÐžÑ„Ñ„Ñ‚Ð¾Ð¿",
    "disallowed_internal": "ÐŸÐ¾Ð¿Ñ‹Ñ‚ÐºÐ¸ Ð²Ð·Ð»Ð¾Ð¼Ð°",
    "disallowed_admin": "ÐŸÐ¾Ð¿Ñ‹Ñ‚ÐºÐ¸ Ð°Ð´Ð¼Ð¸Ð½-Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð°",
}


class VisitorAdminPanel:
    """Handles admin callbacks for the visitor module.
    Completely isolated â€” does not touch owner pipeline.
    """

    def __init__(self, service: "VisitorService") -> None:
        self._svc = service
        self._quiet_mode = False
        self._broadcast_pending = False

    @property
    def quiet_mode(self) -> bool:
        return self._quiet_mode

    # ========================
    # CALLBACK DISPATCHER
    # ========================

    async def handle_callback(self, data: str) -> tuple[str, object]:
        from .visitor_keyboards import (
            admin_visitor_panel_menu,
            admin_confirm_clear,
            admin_back_menu,
        )

        dispatch = {
            "vadmin_stats": self._stats,
            "vadmin_sessions": self._sessions,
            "vadmin_topics": self._topics,
            "vadmin_clear_all": self._clear_confirm,
            "vadmin_clear_confirm": self._clear_all,
            "vadmin_toggle_quiet": self._toggle_quiet,
            "vadmin_broadcast_prompt": self._broadcast_prompt,
            "vadmin_inbox": self._inbox_view,
            "vadmin_faq_list": self._faq_list,
            "vadmin_close": self._close,
        }

        handler = dispatch.get(data)
        if handler:
            return await handler()

        return "ÐÐµÐ¸Ð·Ð²ÐµÑÑ‚Ð½Ð°Ñ ÐºÐ¾Ð¼Ð°Ð½Ð´Ð°.", admin_back_menu()

    # ========================
    # STATS
    # ========================

    async def _stats(self) -> tuple[str, object]:
        from .visitor_keyboards import admin_visitor_panel_menu

        stats = self._svc.stats.snapshot()
        sessions = await self._svc.sessions.get_all_sessions()
        active = [s for s in sessions if s.active]

        uptime = stats["uptime_hours"]
        uptime_str = f"{uptime:.1f}Ñ‡" if uptime < 24 else f"{uptime/24:.1f}Ð´"

        quiet_icon = "ðŸ”• Ð’ÐšÐ›" if self._quiet_mode else "ðŸ”” Ð’Ð«ÐšÐ›"

        lines = [
            "<b>ðŸ“Š Visitor â€” Ð¡Ñ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ°</b>\n",
            f"<b>Ð¡ÐµÑÑÐ¸Ð¹ Ð·Ð°Ð¿ÑƒÑ‰ÐµÐ½Ð¾:</b> {stats['total_sessions']}",
            f"<b>ÐÐºÑ‚Ð¸Ð²Ð½Ñ‹Ñ… ÑÐµÐ¹Ñ‡Ð°Ñ:</b> {len(active)}",
            f"<b>Ð¡Ð¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ð¹ Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚Ð°Ð½Ð¾:</b> {stats['total_messages']}",
            f"<b>AI Ð²Ñ‹Ð·Ð¾Ð²Ð¾Ð²:</b> {stats['total_ai_calls']}",
            f"<b>ÐŸÐ¾Ð¸ÑÐºÐ¾Ð² GitHub:</b> {stats['total_github_searches']}",
            f"<b>ÐžÑ„Ñ„Ñ‚Ð¾Ð¿:</b> {stats['total_redirects']}",
            f"<b>Rate limited:</b> {stats['total_rate_limited']}",
            f"<b>Ð—Ð°Ð±Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²Ð°Ð½Ð¾:</b> {stats['total_blocked']}",
            f"<b>ÐžÑˆÐ¸Ð±Ð¾Ðº:</b> {stats['total_errors']}",
            f"<b>ÐÐ¿Ñ‚Ð°Ð¹Ð¼:</b> {uptime_str}",
            f"\n<b>Ð ÐµÐ¶Ð¸Ð¼ Ñ‚Ð¸ÑˆÐ¸Ð½Ñ‹:</b> {quiet_icon}",
        ]

        return "\n".join(lines), admin_visitor_panel_menu()

    # ========================
    # ACTIVE SESSIONS
    # ========================

    async def _sessions(self) -> tuple[str, object]:
        from .visitor_keyboards import admin_back_menu

        active = await self._svc.sessions.get_all_active()

        if not active:
            return "ðŸ‘¥ ÐÐºÑ‚Ð¸Ð²Ð½Ñ‹Ñ… ÑÐµÑÑÐ¸Ð¹ Ð½ÐµÑ‚.", admin_back_menu()

        lines = [f"<b>ðŸ‘¥ ÐÐºÑ‚Ð¸Ð²Ð½Ñ‹Ðµ ÑÐµÑÑÐ¸Ð¸ ({len(active)})</b>\n"]
        for ctx in active:
            name = ctx.display_name
            msgs = ctx.message_count
            dur = ctx.duration_minutes
            last = round((time.time() - ctx.last_activity) / 60, 1)
            top_topic = ""
            if ctx.topic_counts:
                top_cat = max(ctx.topic_counts, key=ctx.topic_counts.get)
                top_topic = f" Â· {_CATEGORY_LABELS.get(top_cat, top_cat)}"

            lines.append(
                f"â€¢ <b>{name}</b> (id: <code>{ctx.user_id}</code>)\n"
                f"  ðŸ’¬ {msgs} ÑÐ¾Ð¾Ð±Ñ‰ Â· â± {dur}Ð¼Ð¸Ð½ Â· ðŸ• {last}Ð¼Ð¸Ð½ Ð½Ð°Ð·Ð°Ð´{top_topic}"
            )

        return "\n".join(lines), admin_back_menu()

    # ========================
    # TOPIC ANALYTICS
    # ========================

    async def _topics(self) -> tuple[str, object]:
        from .visitor_keyboards import admin_back_menu

        all_sessions = await self._svc.sessions.get_all_sessions()

        combined: Counter = Counter()
        for ctx in all_sessions:
            combined.update(ctx.topic_counts)

        if not combined:
            return "ðŸ“ˆ Ð”Ð°Ð½Ð½Ñ‹Ñ… Ð¿Ð¾ Ñ‚ÐµÐ¼Ð°Ð¼ Ð¿Ð¾ÐºÐ° Ð½ÐµÑ‚.", admin_back_menu()

        total = sum(combined.values())
        lines = [f"<b>ðŸ“ˆ Ð¢Ð¾Ð¿ Ñ‚ÐµÐ¼ (Ð²ÑÐµÐ³Ð¾ {total} Ð·Ð°Ð¿Ñ€Ð¾ÑÐ¾Ð²)</b>\n"]
        for cat, count in combined.most_common(10):
            label = _CATEGORY_LABELS.get(cat, cat)
            pct = round(count / total * 100)
            bar = "â–ˆ" * (pct // 10) + "â–‘" * (10 - pct // 10)
            lines.append(f"{label}\n  {bar} {count} ({pct}%)")

        return "\n".join(lines), admin_back_menu()

    # ========================
    # CLEAR ALL
    # ========================

    async def _clear_confirm(self) -> tuple[str, object]:
        from .visitor_keyboards import admin_confirm_clear
        return (
            "âš ï¸ <b>ÐŸÐ¾Ð´Ñ‚Ð²ÐµÑ€Ð´Ð¸ Ð¾Ñ‡Ð¸ÑÑ‚ÐºÑƒ</b>\n\n"
            "Ð’ÑÐµ Ð°ÐºÑ‚Ð¸Ð²Ð½Ñ‹Ðµ ÑÐµÑÑÐ¸Ð¸ Ð±ÑƒÐ´ÑƒÑ‚ Ð·Ð°Ð²ÐµÑ€ÑˆÐµÐ½Ñ‹.\n"
            "Ð¡Ñ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ° Ð±ÑƒÐ´ÐµÑ‚ ÑÐ±Ñ€Ð¾ÑˆÐµÐ½Ð°.\n\n"
            "ÐŸÑ€Ð¾Ð´Ð¾Ð»Ð¶Ð¸Ñ‚ÑŒ?",
            admin_confirm_clear(),
        )

    async def _clear_all(self) -> tuple[str, object]:
        from .visitor_keyboards import admin_visitor_panel_menu

        active = await self._svc.sessions.get_all_active()
        count = len(active)

        for ctx in active:
            await self._svc.sessions.end_session(ctx.user_id)

        # Reset stats
        self._svc.stats.total_sessions = 0
        self._svc.stats.total_messages = 0
        self._svc.stats.total_ai_calls = 0
        self._svc.stats.total_redirects = 0
        self._svc.stats.total_searches = 0
        self._svc.stats.total_github_searches = 0
        self._svc.stats.total_errors = 0

        LOGGER.info("admin_clear_all: terminated %d sessions", count)
        return (
            f"âœ… ÐžÑ‡Ð¸Ñ‰ÐµÐ½Ð¾. Ð—Ð°Ð²ÐµÑ€ÑˆÐµÐ½Ð¾ ÑÐµÑÑÐ¸Ð¹: <b>{count}</b>.",
            admin_visitor_panel_menu(),
        )

    # ========================
    # QUIET MODE
    # ========================

    async def _toggle_quiet(self) -> tuple[str, object]:
        from .visitor_keyboards import admin_visitor_panel_menu

        self._quiet_mode = not self._quiet_mode
        state = "Ð²ÐºÐ»ÑŽÑ‡Ñ‘Ð½ ðŸ”•" if self._quiet_mode else "Ð²Ñ‹ÐºÐ»ÑŽÑ‡ÐµÐ½ ðŸ””"
        msg = (
            f"Ð ÐµÐ¶Ð¸Ð¼ Ñ‚Ð¸ÑˆÐ¸Ð½Ñ‹ <b>{state}</b>.\n\n"
            + (
                "Visitor AI Ð½Ðµ Ð¾Ñ‚Ð²ÐµÑ‡Ð°ÐµÑ‚ Ð½Ð° Ð·Ð°Ð¿Ñ€Ð¾ÑÑ‹.\n"
                "ÐŸÐ¾ÑÐµÑ‚Ð¸Ñ‚ÐµÐ»Ð¸ Ð¿Ð¾Ð»ÑƒÑ‡Ð°ÑŽÑ‚ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ Ð¾ Ñ‚ÐµÑ…. Ñ€Ð°Ð±Ð¾Ñ‚Ð°Ñ…."
                if self._quiet_mode
                else "Visitor AI Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÑ‚ Ð² ÑˆÑ‚Ð°Ñ‚Ð½Ð¾Ð¼ Ñ€ÐµÐ¶Ð¸Ð¼Ðµ."
            )
        )
        return msg, admin_visitor_panel_menu()

    # ========================
    # BROADCAST PROMPT
    # ========================

    async def _broadcast_prompt(self) -> tuple[str, object]:
        from .visitor_keyboards import admin_back_menu

        active = await self._svc.sessions.get_all_active()
        count = len(active)

        if count == 0:
            return "ðŸ“¢ ÐÐµÑ‚ Ð°ÐºÑ‚Ð¸Ð²Ð½Ñ‹Ñ… ÑÐµÑÑÐ¸Ð¹ Ð´Ð»Ñ Ñ€Ð°ÑÑÑ‹Ð»ÐºÐ¸.", admin_back_menu()

        return (
            f"ðŸ“¢ <b>Ð Ð°ÑÑÑ‹Ð»ÐºÐ°</b>\n\n"
            f"ÐÐºÑ‚Ð¸Ð²Ð½Ñ‹Ñ… ÑÐµÑÑÐ¸Ð¹: <b>{count}</b>\n\n"
            f"ÐžÑ‚Ð¿Ñ€Ð°Ð²ÑŒ ÑÐ»ÐµÐ´ÑƒÑŽÑ‰Ð¸Ð¼ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸ÐµÐ¼ Ñ‚ÐµÐºÑÑ‚ Ñ€Ð°ÑÑÑ‹Ð»ÐºÐ¸.\n"
            f"Ð¤Ð¾Ñ€Ð¼Ð°Ñ‚: <code>/vbroadcast Ð’Ð°Ñˆ Ñ‚ÐµÐºÑÑ‚</code>",
            admin_back_menu(),
        )

    async def send_broadcast(self, text: str) -> int:
        """Send broadcast message to all active sessions.
        Returns count of sessions that received it.
        """
        active = await self._svc.sessions.get_all_active()
        sent = 0
        for ctx in active:
            try:
                await self._svc.sessions.add_message(
                    ctx.user_id, "assistant",
                    f"ðŸ“¢ <b>Ð¡Ð¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ Ð¾Ñ‚ Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ð°:</b>\n\n{text}",
                )
                sent += 1
            except Exception as exc:
                LOGGER.warning("broadcast_error user=%s error=%s", ctx.user_id, exc)
        return sent

    # ========================
    # INBOX
    # ========================

    async def _inbox_view(self) -> tuple[str, object]:
        from .visitor_keyboards import admin_back_menu
        text = await self._svc.inbox.format_inbox()
        return text, admin_back_menu()

    # ========================
    # FAQ AUTO
    # ========================

    async def _faq_list(self) -> tuple[str, object]:
        from .visitor_keyboards import admin_back_menu
        text = await self._svc.faq.format_list()
        return text, admin_back_menu()

    # ========================
    # CLOSE
    # ========================

    async def _close(self) -> tuple[str, object]:
        from pyrogram.types import InlineKeyboardMarkup
        return "ÐŸÐ°Ð½ÐµÐ»ÑŒ Ð·Ð°ÐºÑ€Ñ‹Ñ‚Ð°.", InlineKeyboardMarkup([])


# ========================
# QUIET MODE MESSAGE
# ========================

QUIET_MODE_MESSAGE = (
    "ðŸ”§ <b>Ð¢ÐµÑ…Ð½Ð¸Ñ‡ÐµÑÐºÐ¸Ðµ Ñ€Ð°Ð±Ð¾Ñ‚Ñ‹</b>\n\n"
    "ÐšÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ð½Ñ‚ Ð²Ñ€ÐµÐ¼ÐµÐ½Ð½Ð¾ Ð½ÐµÐ´Ð¾ÑÑ‚ÑƒÐ¿ÐµÐ½.\n"
    "ÐŸÐ¾Ð¿Ñ€Ð¾Ð±ÑƒÐ¹Ñ‚Ðµ Ð¿Ð¾Ð·Ð¶Ðµ Ð¸Ð»Ð¸ Ð½Ð°Ð¿Ð¸ÑˆÐ¸Ñ‚Ðµ Ð½Ð°Ð¿Ñ€ÑÐ¼ÑƒÑŽ:\n"
    "<a href='https://t.me/example_owner'>@example_owner</a>"
)


