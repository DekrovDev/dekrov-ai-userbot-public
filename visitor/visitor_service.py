from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from config.settings import AppConfig
from config.identity import build_non_owner_threat_refusal
from ai.groq_client import GroqClient
from memory.owner_knowledge import OwnerKnowledgeStore

from .visitor_session import VisitorSessionStore
from .visitor_router import route_query, Route, RouteDecision
from .visitor_context import build_safe_visitor_context, format_knowledge_for_prompt
from .visitor_search import (
    find_tech_connection,
    clean_search_query,
    search_github,
    search_portfolio,
    search_web,
)
from .visitor_prompt import build_visitor_system_prompt
from .visitor_cards import build_card
from .visitor_admin import VisitorAdminPanel, QUIET_MODE_MESSAGE
from .visitor_easter import check_easter_egg
from .visitor_faq_cache import VisitorFaqCache
from .visitor_inbox import VisitorInbox, format_owner_notification, format_visitor_reply, AWAITING_QUESTION_MESSAGE, QUESTION_SENT_MESSAGE
from .visitor_moderation import (
    detect_abusive_message,
    format_moderation_owner_notification,
)
from .visitor_source_policy import (
    build_source_guidance,
    query_mentions_channel,
    query_mentions_code,
    query_mentions_portfolio_hint,
    query_mentions_projects,
    query_mentions_source_request,
    should_try_allowed_sources,
)
from .visitor_judge import (
    VisitorJudgeStore,
    build_incident_signature,
    build_visitor_judge_messages,
    format_visitor_judge_notification,
    parse_visitor_judge_response,
    should_review_visitor_response,
)
from .visitor_models import TopicCategory, VisitorContext

if TYPE_CHECKING:
    from .visitor_keyboards import InlineKeyboardMarkup

LOGGER = logging.getLogger("assistant.visitor")
VISITOR_TELEGRAM_LIMIT = 3800


# ========================
# RESPONSE FORMATTER
# ========================

def _format_visitor_response(text: str) -> str:
    """Format AI response for better readability.
    
    - Removes [END_SUGGESTION] marker
    - Adds paragraph breaks
    - Formats lists with bullet points
    - Ensures proper spacing
    """
    if not text:
        return text
    
    text = text.replace("[END_SUGGESTION]", "").strip()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?m)^[ \t]*---+[ \t]*$", "", text)
    text = re.sub(r"(?m)^(\d+)\.\s*\n+\s*", r"\1. ", text)
    text = re.sub(r"(?m)^([*-])\s*\n+\s*", r"\1 ", text)
    
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    # Add line breaks between list-like items
    # Pattern: period followed by capital letter or bullet point
    text = re.sub(r'(\.|:)\s*(â€¢|[-*])', r'\1\n\2', text)
    
    # Ensure bullet points are on separate lines with â€¢ symbol
    lines = text.split('\n')
    formatted_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            formatted_lines.append('')
            continue
        # Convert - or * to â€¢ for consistency
        if re.match(r'^[-*]\s+', line):
            line = 'â€¢ ' + line.lstrip('-* ').strip()
        formatted_lines.append(line)
    
    text = '\n'.join(formatted_lines)
    
    # Clean up multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def _md_to_tg_html(text: str) -> str:
    import html as _html

    result = text

    def replace_fenced(match: re.Match) -> str:
        lang = (match.group(1) or "").strip()
        code = _html.escape(match.group(2))
        if lang:
            return f'<pre><code class="language-{lang}">{code}</code></pre>'
        return f"<pre><code>{code}</code></pre>"

    result = re.sub(
        r"```([^\n`]*)\n(.*?)```", replace_fenced, result, flags=re.DOTALL
    )
    result = re.sub(
        r"`([^`\n]+)`", lambda m: f"<code>{_html.escape(m.group(1))}</code>", result
    )
    result = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", result, flags=re.DOTALL)
    result = re.sub(r"__(.+?)__", r"<b>\1</b>", result, flags=re.DOTALL)
    result = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", result)
    result = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", result)
    result = re.sub(r"~~(.+?)~~", r"<s>\1</s>", result, flags=re.DOTALL)
    result = re.sub(
        r"\|\|(.+?)\|\|", r"<tg-spoiler>\1</tg-spoiler>", result, flags=re.DOTALL
    )

    def replace_blockquote(match: re.Match) -> str:
        inner = re.sub(r"^>\s?", "", match.group(0), flags=re.MULTILINE).strip()
        return f"<blockquote>{inner}</blockquote>"

    result = re.sub(r"(?:^|\n)((?:>[^\n]*\n?)+)", replace_blockquote, result)
    return result


def _format_visitor_response(text: str) -> str:
    """Normalize visitor text and convert simple markdown to Telegram HTML."""
    if not text:
        return text

    text = text.replace("[END_SUGGESTION]", "").strip()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?m)^[ \t]*---+[ \t]*$", "", text)
    text = re.sub(r"(?m)^(\d+)\.\s*\n+\s*", r"\1. ", text)
    text = re.sub(r"(?m)^([*-])\s*\n+\s*", r"\1 ", text)
    text = re.sub(r"(?m)^[â€¢â–ªâ—]\s*", "- ", text)
    text = re.sub(r"(?m)^[-*]\s+", "- ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    formatted = _md_to_tg_html(text.strip())
    formatted = re.sub(r"\n{3,}", "\n\n", formatted)
    return formatted.strip()


@dataclass
class VisitorStats:
    total_sessions: int = 0
    total_messages: int = 0
    total_ai_calls: int = 0
    total_redirects: int = 0
    total_searches: int = 0
    total_github_searches: int = 0
    total_errors: int = 0
    total_rate_limited: int = 0
    total_blocked: int = 0
    start_time: float = field(default_factory=time.time)

    def snapshot(self) -> dict:
        uptime_h = (time.time() - self.start_time) / 3600
        return {
            "total_sessions": self.total_sessions,
            "total_messages": self.total_messages,
            "total_ai_calls": self.total_ai_calls,
            "total_redirects": self.total_redirects,
            "total_searches": self.total_searches,
            "total_github_searches": self.total_github_searches,
            "total_errors": self.total_errors,
            "total_rate_limited": self.total_rate_limited,
            "total_blocked": self.total_blocked,
            "uptime_hours": round(uptime_h, 1),
        }


# ========================
# STATIC FALLBACKS
# ========================

_FALLBACK_OWNER = (
    "<b>Ðž Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ðµ</b>\n\n"
    "<b>Ð˜Ð¼Ñ:</b> ProjectOwner (ÐŸÐ°ÑˆÐ° / Pavlo)\n"
    "<b>ÐÐ°Ð¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ:</b> Ð²ÐµÐ±-Ñ€Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ°, Telegram-Ð±Ð¾Ñ‚Ñ‹, Ð°Ð²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ð·Ð°Ñ†Ð¸Ñ\n\n"
    "ProjectOwner â€” Ñ€Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚Ñ‡Ð¸Ðº, ÐºÐ¾Ñ‚Ð¾Ñ€Ñ‹Ð¹ ÑÐ¾Ð·Ð´Ð°ÐµÑ‚ Telegram-Ð±Ð¾Ñ‚Ð¾Ð², AI-Ð°ÑÑÐ¸ÑÑ‚ÐµÐ½Ñ‚Ð¾Ð² Ð¸ Ñ€Ð°Ð±Ð¾Ñ‡Ð¸Ðµ Ð¸Ð½ÑÑ‚Ñ€ÑƒÐ¼ÐµÐ½Ñ‚Ñ‹ Ð°Ð²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ð·Ð°Ñ†Ð¸Ð¸.\n"
    "GitHub: <a href='https://github.com/example'>example</a>\n"
    "Ð¡Ð°Ð¹Ñ‚: <a href='https://example.com'>example.com</a>"
)

_FALLBACK_LINKS = (
    "<b>Ð¡ÑÑ‹Ð»ÐºÐ¸</b>\n\n"
    "â€¢ <b>GitHub:</b> <a href='https://github.com/example'>github.com/example</a>\n"
    "â€¢ <b>ÐŸÐ¾Ñ€Ñ‚Ñ„Ð¾Ð»Ð¸Ð¾:</b> <a href='https://example.com'>example.com</a>\n"
    "â€¢ <b>Telegram ÐºÐ°Ð½Ð°Ð»:</b> <a href='https://t.me/example_channel'>@example_channel</a>\n"
    "â€¢ <b>Telegram:</b> <a href='https://t.me/example_owner'>@example_owner</a>\n"
    "â€¢ <b>Email:</b> contact@example.com"
)

_FALLBACK_PROJECTS = (
    "<b>ÐŸÑ€Ð¾ÐµÐºÑ‚Ñ‹</b>\n\n"
    "â€¢ <b>Project Assistant</b> â€” AI ÑŽÐ·ÐµÑ€Ð±Ð¾Ñ‚ Ð´Ð»Ñ Telegram\n"
    "â€¢ <b>ÐŸÐ¾Ñ€Ñ‚Ñ„Ð¾Ð»Ð¸Ð¾</b> â€” <a href='https://example.com'>example.com</a>\n\n"
    "GitHub: <a href='https://github.com/example'>example</a>"
)

_FALLBACK_CAPABILITIES = (
    "<b>Ð§Ñ‚Ð¾ ÑƒÐ¼ÐµÐµÑ‚ ÑÑ‚Ð¾Ñ‚ Ð°ÑÑÐ¸ÑÑ‚ÐµÐ½Ñ‚</b>\n\n"
    "â€¢ Ð Ð°ÑÑÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð¾ ProjectOwner Ð¸ ÐµÐ³Ð¾ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ…\n"
    "â€¢ ÐžÐ±ÑŠÑÑÐ½Ð¸Ñ‚ÑŒ Ñ‚ÐµÑ…Ð½Ð¸Ñ‡ÐµÑÐºÐ¸Ðµ Ð¿Ð¾Ð½ÑÑ‚Ð¸Ñ\n"
    "â€¢ ÐÐ°Ð¹Ñ‚Ð¸ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ñ‹ Ð½Ð° GitHub\n"
    "â€¢ Ð”Ð°Ñ‚ÑŒ ÑÑÑ‹Ð»ÐºÐ¸ Ð½Ð° GitHub, Telegram, ÑÐ°Ð¹Ñ‚\n"
    "â€¢ Ð Ð°ÑÑÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð¾ Ð²Ð¾Ð·Ð¼Ð¾Ð¶Ð½Ð¾ÑÑ‚ÑÑ… Ð´Ð»Ñ ÑÐ¾Ñ‚Ñ€ÑƒÐ´Ð½Ð¸Ñ‡ÐµÑÑ‚Ð²Ð°\n"
    "â€¢ Ð¡Ð²ÑÐ·Ð°Ñ‚ÑŒ Ñ‚ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸Ð¸ Ñ Ñ€ÐµÐ°Ð»ÑŒÐ½Ñ‹Ð¼Ð¸ ÐºÐµÐ¹ÑÐ°Ð¼Ð¸\n\n"
    "<i>Ð¯ Ð¾Ñ‚Ð²ÐµÑ‡Ð°ÑŽ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð¿Ð¾ Ñ‚ÐµÐ¼Ðµ. ÐÐµ Ð±Ð¾Ð»Ñ‚Ð°ÑŽ Ð¸ Ð½Ðµ Ð²Ñ‹Ð´ÑƒÐ¼Ñ‹Ð²Ð°ÑŽ.</i>"
)

_FALLBACK_FAQ = (
    "<b>Ð§Ð°ÑÑ‚Ñ‹Ðµ Ð²Ð¾Ð¿Ñ€Ð¾ÑÑ‹</b>\n\n"
    "â€¢ <b>ÐšÐ°Ðº ÑÐ²ÑÐ·Ð°Ñ‚ÑŒÑÑ?</b>\n"
    "Telegram: <a href='https://t.me/example_owner'>@example_owner</a> Â· Email: contact@example.com\n\n"
    "â€¢ <b>Ð§ÐµÐ¼ Ð·Ð°Ð½Ð¸Ð¼Ð°ÐµÑ‚ÑÑ?</b>\n"
    "Ð’ÐµÐ±-Ñ€Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ°, Telegram-Ð±Ð¾Ñ‚Ñ‹, AI-Ð¸Ð½ÑÑ‚Ñ€ÑƒÐ¼ÐµÐ½Ñ‚Ñ‹ Ð¸ Ð°Ð²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ð·Ð°Ñ†Ð¸Ñ.\n\n"
    "â€¢ <b>Ð¢ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸Ð¸?</b>\n"
    "Python, Linux, Pyrogram, Telegram Bot API.\n\n"
    "â€¢ <b>Ð—Ð°ÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð¿Ñ€Ð¾ÐµÐºÑ‚?</b>\n"
    "ÐŸÐ¸ÑˆÐ¸Ñ‚Ðµ Ð² Telegram: <a href='https://t.me/example_owner'>@example_owner</a>"
)

_FALLBACK_COLLABORATION = (
    "<b>Ð¡Ð¾Ñ‚Ñ€ÑƒÐ´Ð½Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾</b>\n\n"
    "â€¢ Ð Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Telegram-Ð±Ð¾Ñ‚Ð¾Ð²\n"
    "â€¢ Ð’ÐµÐ±-Ñ€Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ°\n"
    "â€¢ Ð˜Ð½ÑÑ‚Ñ€ÑƒÐ¼ÐµÐ½Ñ‚Ñ‹ Ð°Ð²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ð·Ð°Ñ†Ð¸Ð¸\n"
    "â€¢ AI-Ð°ÑÑÐ¸ÑÑ‚ÐµÐ½Ñ‚Ñ‹ Ð¸ Ñ€Ð°Ð±Ð¾Ñ‡Ð¸Ðµ ÑÐ¸ÑÑ‚ÐµÐ¼Ñ‹\n\n"
    "ÐšÐ¾Ð½Ñ‚Ð°ÐºÑ‚: <a href='https://t.me/example_owner'>@example_owner</a>"
)

SESSION_STARTED = (
    "<b>ÐšÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸Ñ Ð½Ð°Ñ‡Ð°Ñ‚Ð°</b>\n\n"
    "Ð—Ð°Ð´Ð°Ð²Ð°Ð¹Ñ‚Ðµ Ð²Ð¾Ð¿Ñ€Ð¾ÑÑ‹ Ð¾ ProjectOwner, Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ…, Ñ‚ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸ÑÑ… Ð¸Ð»Ð¸ ÑÐ¾Ñ‚Ñ€ÑƒÐ´Ð½Ð¸Ñ‡ÐµÑÑ‚Ð²Ðµ.\n"
    "<i>Ð¯ Ð¾Ñ‚Ð²ÐµÑ‡Ð°ÑŽ Ð¿Ð¾ Ð´ÐµÐ»Ñƒ â€” Ð±ÐµÐ· Ð²Ð¾Ð´Ñ‹ Ð¸ Ð²Ñ‹Ð´ÑƒÐ¼Ð¾Ðº.</i>"
)

SESSION_ENDED = "ÐšÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸Ñ Ð·Ð°Ð²ÐµÑ€ÑˆÐµÐ½Ð°. ÐÐ°Ð¶Ð¼Ð¸Ñ‚Ðµ /start Ð´Ð»Ñ Ð½Ð¾Ð²Ð¾Ð³Ð¾ Ð¼ÐµÐ½ÑŽ."

NO_SESSION_MESSAGE = (
    "âš ï¸ <b>Ð¡Ð½Ð°Ñ‡Ð°Ð»Ð° Ð½Ð°Ñ‡Ð½Ð¸Ñ‚Ðµ ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸ÑŽ</b>\n\n"
    "ÐÐ°Ð¶Ð¼Ð¸Ñ‚Ðµ ÐºÐ½Ð¾Ð¿ÐºÑƒ Â«ðŸ’¬ ÐÐ°Ñ‡Ð°Ñ‚ÑŒ ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸ÑŽÂ» Ð² Ð¼ÐµÐ½ÑŽ.\n"
    "Ð­Ñ‚Ð¾ Ð½ÑƒÐ¶Ð½Ð¾ Ð´Ð»Ñ Ñ‚Ð¾Ð³Ð¾ Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ñ Ð¼Ð¾Ð³ Ð·Ð°Ð¿Ð¾Ð¼Ð½Ð¸Ñ‚ÑŒ ÐºÐ¾Ð½Ñ‚ÐµÐºÑÑ‚ Ð±ÐµÑÐµÐ´Ñ‹."
)

WELCOME_TEXT = (
    "<b>ProjectOwner â€” AI-ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ð½Ñ‚</b>\n\n"
    "Ð¯ Ð¿Ñ€ÐµÐ´ÑÑ‚Ð°Ð²Ð»ÑÑŽ ProjectOwner Ð¸ Ð¿Ð¾Ð¼Ð¾Ð³Ñƒ ÑƒÐ·Ð½Ð°Ñ‚ÑŒ:\n"
    "â€¢ Ð¾ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ… Ð¸ Ñ‚ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸ÑÑ…\n"
    "â€¢ Ð¾ Ð½Ð°Ð²Ñ‹ÐºÐ°Ñ… Ð¸ ÑÐ¿ÐµÑ†Ð¸Ð°Ð»Ð¸Ð·Ð°Ñ†Ð¸Ð¸\n"
    "â€¢ Ð¾Ð± ÑƒÑÐ»Ð¾Ð²Ð¸ÑÑ… ÑÐ¾Ñ‚Ñ€ÑƒÐ´Ð½Ð¸Ñ‡ÐµÑÑ‚Ð²Ð°\n"
    "â€¢ Ð½Ð°Ð¹Ñ‚Ð¸ ÑÑÑ‹Ð»ÐºÐ¸ Ð¸ ÐºÐ¾Ð½Ñ‚Ð°ÐºÑ‚Ñ‹\n\n"
    "<i>Ð’Ñ‹Ð±ÐµÑ€Ð¸Ñ‚Ðµ Ñ‚ÐµÐ¼Ñƒ Ð¸Ð»Ð¸ Ð½Ð°Ñ‡Ð½Ð¸Ñ‚Ðµ ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸ÑŽ:</i>"
)

VISITOR_DISABLED_TEXT = (
    "<b>ProjectOwner â€” AI-ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ð½Ñ‚</b>\n\n"
    "Ð¯ Ð¿Ñ€ÐµÐ´ÑÑ‚Ð°Ð²Ð»ÑÑŽ ProjectOwner Ð¸ Ð¿Ð¾Ð¼Ð¾Ð³Ñƒ ÑƒÐ·Ð½Ð°Ñ‚ÑŒ:\n"
    "â€¢ Ð¾ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ… Ð¸ Ñ‚ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸ÑÑ…\n"
    "â€¢ Ð¾ Ð½Ð°Ð²Ñ‹ÐºÐ°Ñ… Ð¸ ÑÐ¿ÐµÑ†Ð¸Ð°Ð»Ð¸Ð·Ð°Ñ†Ð¸Ð¸\n"
    "â€¢ Ð¾Ð± ÑƒÑÐ»Ð¾Ð²Ð¸ÑÑ… ÑÐ¾Ñ‚Ñ€ÑƒÐ´Ð½Ð¸Ñ‡ÐµÑÑ‚Ð²Ð°\n"
    "â€¢ Ð½Ð°Ð¹Ñ‚Ð¸ ÑÑÑ‹Ð»ÐºÐ¸ Ð¸ ÐºÐ¾Ð½Ñ‚Ð°ÐºÑ‚Ñ‹\n\n"
    "<i>Ð’Ñ‹Ð±ÐµÑ€Ð¸Ñ‚Ðµ Ñ‚ÐµÐ¼Ñƒ:</i>"
)

RATE_LIMITED_MESSAGE = (
    "Ð¡Ð»Ð¸ÑˆÐºÐ¾Ð¼ Ð¼Ð½Ð¾Ð³Ð¾ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ð¹. ÐŸÐ¾Ð´Ð¾Ð¶Ð´Ð¸Ñ‚Ðµ Ð½ÐµÐ¼Ð½Ð¾Ð³Ð¾ Ð¸ Ð¿Ð¾Ð¿Ñ€Ð¾Ð±ÑƒÐ¹Ñ‚Ðµ ÑÐ½Ð¾Ð²Ð°."
)

BLOCKED_MESSAGE = (
    "â›”ï¸ Ð’Ð°Ñˆ Ð´Ð¾ÑÑ‚ÑƒÐ¿ Ðº AI Ð·Ð°Ð±Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²Ð°Ð½.\n\n"
    "Ð•ÑÐ»Ð¸ ÑÑ‚Ð¾ Ð¾ÑˆÐ¸Ð±ÐºÐ°, Ð½Ð°Ð¿Ð¸ÑˆÐ¸Ñ‚Ðµ Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ñƒ Ð½Ð°Ð¿Ñ€ÑÐ¼ÑƒÑŽ."
)

TEMPORARY_BLOCK_HOURS = 24
TEMPORARY_BLOCK_SECONDS = TEMPORARY_BLOCK_HOURS * 60 * 60
ABUSE_STRIKE_THRESHOLD = 3
ABUSE_WARNING_MESSAGE = (
    "âš ï¸ Ð”Ð°Ð²Ð°Ð¹Ñ‚Ðµ Ð±ÐµÐ· Ð¾ÑÐºÐ¾Ñ€Ð±Ð»ÐµÐ½Ð¸Ð¹. Ð•ÑÐ»Ð¸ Ð¿Ñ€Ð¾Ð´Ð¾Ð»Ð¶Ð¸Ñ‚Ðµ Ð² Ñ‚Ð°ÐºÐ¾Ð¼ Ñ‚Ð¾Ð½Ðµ, "
    "Ð´Ð¾ÑÑ‚ÑƒÐ¿ Ðº AI Ð±ÑƒÐ´ÐµÑ‚ Ð¾Ð³Ñ€Ð°Ð½Ð¸Ñ‡ÐµÐ½ Ð½Ð° 24 Ñ‡Ð°ÑÐ°."
)
RATE_LIMIT_BLOCK_MESSAGE = (
    "â›”ï¸ Ð’Ñ‹ ÑÐ»Ð¸ÑˆÐºÐ¾Ð¼ Ñ‡Ð°ÑÑ‚Ð¾ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐ»Ð¸ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ. "
    "Ð”Ð¾ÑÑ‚ÑƒÐ¿ Ðº AI Ð²Ñ€ÐµÐ¼ÐµÐ½Ð½Ð¾ Ð¾Ð³Ñ€Ð°Ð½Ð¸Ñ‡ÐµÐ½ Ð½Ð° 24 Ñ‡Ð°ÑÐ°."
)

MAX_MESSAGE_LENGTH = 2000

_END_SUGGESTION_PHRASES = (
    "Ð•ÑÐ»Ð¸ Ð±Ð¾Ð»ÑŒÑˆÐµ Ð²Ð¾Ð¿Ñ€Ð¾ÑÐ¾Ð² Ð½ÐµÑ‚, Ð½Ð°Ð¶Ð¼Ð¸Ñ‚Ðµ ÐºÐ½Ð¾Ð¿ÐºÑƒ Ð½Ð¸Ð¶Ðµ.",
    "Ð•ÑÐ»Ð¸ Ñƒ Ð²Ð°Ñ Ð±Ð¾Ð»ÑŒÑˆÐµ Ð½ÐµÑ‚ Ð²Ð¾Ð¿Ñ€Ð¾ÑÐ¾Ð² â€” Ð½Ð°Ð¶Ð¼Ð¸Ñ‚Ðµ Â«Ð—Ð°Ð²ÐµÑ€ÑˆÐ¸Ñ‚ÑŒÂ».",
    "Ð•ÑÐ»Ð¸ Ñ‚ÐµÐ¼Ð° Ð¸ÑÑ‡ÐµÑ€Ð¿Ð°Ð½Ð°, Ð½Ð°Ð¶Ð¼Ð¸Ñ‚Ðµ Â«Ð—Ð°Ð²ÐµÑ€ÑˆÐ¸Ñ‚ÑŒÂ».",
)


def _detect_language(text: str) -> str:
    """Simple language detection based on character sets."""
    if not text:
        return "ru"
    cyrillic = sum(1 for ch in text if "\u0400" <= ch <= "\u04ff")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if cyrillic > latin:
        return "ru"
    if latin > 0:
        return "en"
    return "ru"


def _normalize_support_text(text: str) -> str:
    return " ".join((text or "").strip().casefold().replace("Ñ‘", "Ðµ").split())


def _needs_request_planning_help(text: str) -> bool:
    normalized = _normalize_support_text(text)
    markers = (
        "Ð½Ðµ Ð·Ð½Ð°ÑŽ Ñ‡Ñ‚Ð¾ Ð½Ð°Ð´Ð¾",
        "Ð½Ðµ Ð·Ð½Ð°ÑŽ, Ñ‡Ñ‚Ð¾ Ð½Ð°Ð´Ð¾",
        "Ð½Ðµ Ð·Ð½Ð°ÑŽ Ñ‡Ñ‚Ð¾ Ð½ÑƒÐ¶Ð½Ð¾",
        "Ð½Ðµ Ð·Ð½Ð°ÑŽ, Ñ‡Ñ‚Ð¾ Ð½ÑƒÐ¶Ð½Ð¾",
        "Ñ‡Ñ‚Ð¾ Ð½Ð°Ð´Ð¾ Ð´Ð»Ñ Ð±Ð¾Ñ‚Ð°",
        "Ñ‡Ñ‚Ð¾ Ð½ÑƒÐ¶Ð½Ð¾ Ð´Ð»Ñ Ð±Ð¾Ñ‚Ð°",
        "Ñ‡Ñ‚Ð¾ ÐµÐ¼Ñƒ Ð½Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ",
        "Ñ‡Ñ‚Ð¾ ÐµÐ¼Ñƒ ÑÐºÐ°Ð·Ð°Ñ‚ÑŒ",
        "Ñ‡Ñ‚Ð¾ Ð½Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ Ð´ÐµÐºÑ€Ð¾Ð²Ñƒ",
        "Ñ‡Ñ‚Ð¾ ÑÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð´ÐµÐºÑ€Ð¾Ð²Ñƒ",
        "ÐºÐ°Ðº Ð¿Ð¾Ð¿Ñ€Ð¾ÑÐ¸Ñ‚ÑŒ",
        "ÐºÐ°Ðº Ð½Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ",
        "ÐºÐ°Ðº ÑÑ„Ð¾Ñ€Ð¼ÑƒÐ»Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ",
        "Ð½Ð°Ð´Ð¾ Ð¿Ð¾Ð¿Ñ€Ð¾ÑÐ¸Ñ‚ÑŒ",
        "Ð½Ð°Ð´Ð¾ ÑÐºÐ°Ð·Ð°Ñ‚ÑŒ",
        "Ð½Ð°Ð´Ð¾ Ð´ÐµÐºÑ€Ð¾Ð²Ñƒ ÑÐºÐ°Ð·Ð°Ñ‚ÑŒ",
        "Ð´ÐµÐºÑ€Ð¾Ð²Ñƒ Ð½Ð°Ð´Ð¾ ÑÐºÐ°Ð·Ð°Ñ‚ÑŒ",
        "Ð¿Ð¾Ð¼Ð¾Ð³Ð¸ Ð½Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ",
        "Ð¿Ð¾Ð¼Ð¾Ð³Ð¸ ÑÑ„Ð¾Ñ€Ð¼ÑƒÐ»Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ",
        "Ð¿Ð¾Ð¼Ð¾Ð³Ð¸ Ð¿Ð¾Ð¿Ñ€Ð¾ÑÐ¸Ñ‚ÑŒ",
        "Ñ…Ð¾Ñ‡Ñƒ Ð·Ð°ÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð±Ð¾Ñ‚Ð°",
        "Ð½ÑƒÐ¶ÐµÐ½ Ð±Ð¾Ñ‚",
        "ÑÐ´ÐµÐ»Ð°Ð» Ð¼Ð½Ðµ Ð±Ð¾Ñ‚Ð°",
        "Ð·Ð°ÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð±Ð¾Ñ‚Ð°",
        "Ð±Ð¾Ñ‚Ð° Ð½Ð° Ð·Ð°ÐºÐ°Ð·",
        "request draft",
        "what should i write",
        "how should i ask",
        "help me ask",
        "help me write",
        "i don't know what is needed",
        "i do not know what is needed",
    )
    return any(marker in normalized for marker in markers)


def _shows_uncertainty_or_shyness(text: str) -> bool:
    normalized = _normalize_support_text(text)
    markers = (
        "ÑÑ‚Ñ‹Ð´Ð½Ð¾",
        "Ð½ÐµÐ»Ð¾Ð²ÐºÐ¾",
        "Ð½ÐµÑƒÐ´Ð¾Ð±Ð½Ð¾",
        "Ð±Ð¾ÑŽÑÑŒ",
        "ÑÑ‚Ñ€Ð°ÑˆÐ½Ð¾",
        "ÑÐ¾Ð¼Ð½ÐµÐ²Ð°ÑŽÑÑŒ",
        "Ñ‚ÐµÑ€ÑÑŽÑÑŒ",
        "Ð½Ðµ Ð·Ð½Ð°ÑŽ ÐºÐ°Ðº",
        "Ð½Ðµ ÑƒÐ²ÐµÑ€ÐµÐ½",
        "Ð½Ðµ ÑƒÐ²ÐµÑ€ÐµÐ½Ð°",
        "awkward",
        "shy",
        "nervous",
        "i'm afraid",
        "i am afraid",
        "not sure how",
        "embarrassed",
    )
    return any(marker in normalized for marker in markers)


def _looks_like_ready_request_brief(text: str) -> bool:
    normalized = _normalize_support_text(text)
    markers = (
        "Ð¼Ð½Ðµ Ð½ÑƒÐ¶ÐµÐ½ Ð±Ð¾Ñ‚",
        "Ð½ÑƒÐ¶ÐµÐ½ Ð±Ð¾Ñ‚",
        "Ð½ÑƒÐ¶Ð½Ð¾ Ñ‡Ñ‚Ð¾Ð±Ñ‹",
        "Ð¼Ð½Ðµ Ð½Ð°Ð´Ð¾ Ñ‡Ñ‚Ð¾Ð±Ñ‹",
        "Ñ‡Ñ‚Ð¾Ð±Ñ‹ ÐºÐ¾Ð³Ð´Ð°",
        "telegram bot",
        "telegram-Ð±Ð¾Ñ‚",
        "Ñ‚ÐµÐ»ÐµÐ³Ñ€Ð°Ð¼",
        "telegram",
        "Ñ‚Ð³Ðº",
        "captcha",
        "ÐºÐ°Ð¿Ñ‡Ð°",
        "Ð·Ð°ÑÐ²Ðº",
        "Ð°Ð²Ñ‚Ð¾ Ð¿Ñ€Ð¸Ð½ÑÑ‚",
        "Ð°Ð²Ñ‚Ð¾Ð¿Ñ€Ð¸Ð½ÑÑ‚",
        "5 Ð¼Ð¸Ð½ÑƒÑ‚",
        "when someone",
        "if someone",
    )
    structural_signals = sum(
        1
        for marker in (
            "Ñ‡Ñ‚Ð¾Ð±Ñ‹",
            "ÐµÑÐ»Ð¸",
            "ÐºÐ¾Ð³Ð´Ð°",
            "Ð½ÑƒÐ¶ÐµÐ½",
            "Ð±Ð¾Ñ‚",
            "Ð¼Ð¸Ð½ÑƒÑ‚",
            "captcha",
            "ÐºÐ°Ð¿Ñ‡Ð°",
        )
        if marker in normalized
    )
    return any(marker in normalized for marker in markers) or (
        len(normalized) >= 80 and structural_signals >= 3
    )


def _build_supportive_visitor_guidance(text: str, decision: RouteDecision) -> str | None:
    instructions: list[str] = []

    if decision.category.value in {"general", "collaboration"}:
        instructions.extend(
            [
                "Keep the tone warm, supportive, and conversational.",
                "Do not jump straight to contact details, portfolio links, or the owner button if you can still help inside the chat first.",
                "Do not answer like a rigid FAQ card or a sales script.",
            ]
        )

    if _needs_request_planning_help(text):
        instructions.extend(
            [
                "The visitor needs pre-consultation help before contacting ProjectOwner.",
                "Help them understand what to say or ask, instead of redirecting immediately.",
                "Offer a short checklist with the minimum useful details: goal, where the bot should work, key actions, integrations, examples, timeline, and budget if relevant.",
                "If helpful, offer a ready-to-send message draft addressed to ProjectOwner.",
                "If you give a draft, make it short, natural, and Telegram-style, not a formal letter.",
                "Use Telegram HTML in the final visible answer, never Markdown.",
                "Keep the whole answer compact and easy to send.",
                "Do not invent extra promises, deadlines, or details that the visitor did not provide.",
                "Do not dump a generic tech stack or multiple links unless the visitor asked for them.",
            ]
        )

    if _shows_uncertainty_or_shyness(text):
        instructions.extend(
            [
                "The visitor sounds uncertain or emotionally uncomfortable.",
                "Acknowledge that feeling briefly and reduce the pressure before giving practical advice.",
            ]
        )

    if decision.category.value in {"general", "collaboration"} and _looks_like_ready_request_brief(text):
        instructions.extend(
            [
                "The visitor already described the task with enough detail.",
                "Do not repeat the same requirements as a long formal brief.",
                "Turn their description into one short ready-to-send Telegram message for ProjectOwner.",
                "Keep the draft natural, concise, and practical, usually no more than 3-6 short lines.",
                "Ask at most one short follow-up question only if a truly critical detail is missing.",
            ]
        )

    if not instructions:
        return None

    return "Visitor support mode:\n- " + "\n- ".join(instructions)


def _format_temporary_block_message(remaining_seconds: int) -> str:
    remaining_hours = max(1, math.ceil(remaining_seconds / 3600))
    if remaining_hours >= TEMPORARY_BLOCK_HOURS:
        return (
            "â›”ï¸ Ð”Ð¾ÑÑ‚ÑƒÐ¿ Ðº AI Ð²Ñ€ÐµÐ¼ÐµÐ½Ð½Ð¾ Ð¾Ð³Ñ€Ð°Ð½Ð¸Ñ‡ÐµÐ½ Ð½Ð° 24 Ñ‡Ð°ÑÐ°.\n\n"
            "ÐŸÐ¾Ð¿Ñ€Ð¾Ð±ÑƒÐ¹Ñ‚Ðµ Ð¿Ð¾Ð·Ð¶Ðµ."
        )
    return (
        "â›”ï¸ Ð”Ð¾ÑÑ‚ÑƒÐ¿ Ðº AI Ð²Ñ€ÐµÐ¼ÐµÐ½Ð½Ð¾ Ð¾Ð³Ñ€Ð°Ð½Ð¸Ñ‡ÐµÐ½.\n\n"
        f"ÐŸÐ¾Ð¿Ñ€Ð¾Ð±ÑƒÐ¹Ñ‚Ðµ ÑÐ½Ð¾Ð²Ð° Ð¿Ñ€Ð¸Ð¼ÐµÑ€Ð½Ð¾ Ñ‡ÐµÑ€ÐµÐ· {remaining_hours} Ñ‡."
    )


def _history_safe_text(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _build_small_talk_response(text: str) -> str | None:
    normalized = " ".join((text or "").strip().casefold().split())
    if not normalized:
        return None

    if any(
        marker in normalized
        for marker in (
            "ÐºÐ°Ðº Ð´ÐµÐ»Ð°",
            "ÐºÐ°Ðº Ñƒ Ñ‚ÐµÐ±Ñ Ð´ÐµÐ»Ð°",
            "ÐºÐ°Ðº Ñ‚Ñ‹",
            "ÐºÐ°Ðº ÑÐ°Ð¼",
            "Ñ‡Ñ‚Ð¾ Ð´ÐµÐ»Ð°ÐµÑˆÑŒ",
            "Ñ‡ÐµÐ¼ Ð·Ð°Ð½Ð¸Ð¼Ð°ÐµÑˆÑŒÑÑ",
            "how are you",
            "how is it going",
            "what are you doing",
        )
    ):
        return (
            "Ð£ Ð¼ÐµÐ½Ñ Ð²ÑÑ‘ ÑÐ¿Ð¾ÐºÐ¾Ð¹Ð½Ð¾ â€” Ñ Ð²Ð¸Ñ€Ñ‚ÑƒÐ°Ð»ÑŒÐ½Ñ‹Ð¹ Ð°ÑÑÐ¸ÑÑ‚ÐµÐ½Ñ‚ ProjectOwner. "
            "Ð•ÑÐ»Ð¸ Ñ…Ð¾Ñ‡ÐµÑˆÑŒ, Ð¼Ð¾Ð¶ÐµÐ¼ Ð¿ÐµÑ€ÐµÐ¹Ñ‚Ð¸ Ðº ÐºÐ°ÐºÐ¾Ð¼Ñƒ-Ñ‚Ð¾ Ð²Ð¾Ð¿Ñ€Ð¾ÑÑƒ, Ð¸Ð´ÐµÐµ Ð¸Ð»Ð¸ Ð·Ð°Ð´Ð°Ñ‡Ðµ."
        )

    if any(
        marker in normalized
        for marker in (
            "ÑÐºÐ¾Ð»ÑŒÐºÐ¾ Ñ‚ÐµÐ±Ðµ Ð»ÐµÑ‚",
            "ÑÐºÐ¾Ð»ÑŒÐºÐ¾ Ð²Ð°Ð¼ Ð»ÐµÑ‚",
            "Ñ‚ÐµÐ±Ðµ ÑÐºÐ¾Ð»ÑŒÐºÐ¾ Ð»ÐµÑ‚",
            "Ñ‚Ð²Ð¾Ð¹ Ð²Ð¾Ð·Ñ€Ð°ÑÑ‚",
            "how old are you",
            "your age",
        )
    ):
        return (
            "Ð£ Ð¼ÐµÐ½Ñ Ð²Ð¾Ð·Ñ€Ð°ÑÑ‚Ð° Ð½ÐµÑ‚ â€” Ñ Ð²Ð¸Ñ€Ñ‚ÑƒÐ°Ð»ÑŒÐ½Ñ‹Ð¹ Ð¿Ð¾Ð¼Ð¾Ñ‰Ð½Ð¸Ðº ProjectOwner. "
            "ÐÐ¾ Ð¿Ð¾Ð¾Ð±Ñ‰Ð°Ñ‚ÑŒÑÑ ÑÐ¿Ð¾ÐºÐ¾Ð¹Ð½Ð¾ Ð¼Ð¾Ð³Ñƒ :)"
        )

    if any(
        marker in normalized
        for marker in (
            "ÐºÐ°ÐºÐ¾Ðµ Ñ‰Ð°Ñ Ñ‡Ð¸ÑÐ»Ð¾",
            "ÐºÐ°ÐºÐ¾Ðµ ÑÐµÐ¹Ñ‡Ð°Ñ Ñ‡Ð¸ÑÐ»Ð¾",
            "ÐºÐ°ÐºÐ¾Ðµ ÑÐµÐ³Ð¾Ð´Ð½Ñ Ñ‡Ð¸ÑÐ»Ð¾",
            "ÐºÐ°ÐºÐ°Ñ ÑÐµÐ³Ð¾Ð´Ð½Ñ Ð´Ð°Ñ‚Ð°",
            "ÐºÐ°ÐºÐ°Ñ Ñ‰Ð°Ñ Ð´Ð°Ñ‚Ð°",
            "ÐºÐ°ÐºÐ°Ñ ÑÐµÐ¹Ñ‡Ð°Ñ Ð´Ð°Ñ‚Ð°",
            "what date is it",
            "what day is it",
        )
    ):
        current_date = datetime.now(timezone.utc).strftime("%d.%m.%Y")
        return f"ÐŸÐ¾ Ð¼Ð¾ÐµÐ¼Ñƒ Ð²Ñ€ÐµÐ¼ÐµÐ½Ð¸ ÑÐµÐ¹Ñ‡Ð°Ñ {current_date}."

    if any(
        marker in normalized
        for marker in (
            "ÑÐºÐ¾Ð»ÑŒÐºÐ¾ Ð²Ñ€ÐµÐ¼ÐµÐ½Ð¸",
            "ÐºÐ¾Ñ‚Ð¾Ñ€Ñ‹Ð¹ Ñ‡Ð°Ñ",
            "ÐºÐ°ÐºÐ¾Ðµ Ð²Ñ€ÐµÐ¼Ñ",
            "what time is it",
        )
    ):
        current_time = datetime.now(timezone.utc).strftime("%H:%M")
        return f"ÐŸÐ¾ Ð¼Ð¾ÐµÐ¼Ñƒ Ð²Ñ€ÐµÐ¼ÐµÐ½Ð¸ ÑÐµÐ¹Ñ‡Ð°Ñ {current_time} UTC."

    if any(
        marker in normalized
        for marker in (
            "ÑˆÑƒÑ‚ÐºÐ°",
            "Ð¿Ð¾ÑˆÑƒÑ‚Ð¸",
            "Ñ€Ð°ÑÑÐ¼ÐµÑˆÐ¸",
            "joke",
            "funny",
        )
    ):
        return (
            "Ð›Ð°Ð´Ð½Ð¾, ÐºÐ¾Ñ€Ð¾Ñ‚ÐºÐ°Ñ: Ð±Ð¾Ñ‚ Ñ‚Ð°Ðº Ð´Ð¾Ð»Ð³Ð¾ Ð¸ÑÐºÐ°Ð» Ð¸Ð´ÐµÐ°Ð»ÑŒÐ½Ñ‹Ð¹ Ð¾Ñ‚Ð²ÐµÑ‚, "
            "Ñ‡Ñ‚Ð¾ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑŒ ÑƒÐ¶Ðµ ÑƒÑÐ¿ÐµÐ» Ð·Ð°Ð´Ð°Ñ‚ÑŒ ÑÐ»ÐµÐ´ÑƒÑŽÑ‰Ð¸Ð¹ Ð²Ð¾Ð¿Ñ€Ð¾Ñ."
        )

    return None


BOUNDARY_END_STREAK = 3
RESTART_COOLDOWN_MINUTES = 20
LOW_SIGNAL_SOFT_STREAK = 3
LOW_SIGNAL_WARNING_STREAK = 4
LOW_SIGNAL_END_STREAK = 5
LOW_SIGNAL_RESET_WINDOW_SECONDS = 1800


def _looks_like_friend_chat_request(text: str) -> bool:
    normalized = _normalize_support_text(text)
    markers = (
        "Ñ Ñ…Ð¾Ñ‡Ñƒ Ñ Ñ‚Ð¾Ð±Ð¾Ð¹ Ð¿Ð¾Ð¾Ð±Ñ‰Ð°Ñ‚ÑŒÑÑ",
        "Ñ…Ð¾Ñ‡Ñƒ Ñ Ñ‚Ð¾Ð±Ð¾Ð¹ Ð¿Ð¾Ð¾Ð±Ñ‰Ð°Ñ‚ÑŒÑÑ",
        "Ñ Ñ…Ð¾Ñ‡Ñƒ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð¿Ð¾Ð¾Ð±Ñ‰Ð°Ñ‚ÑŒÑÑ",
        "Ñ…Ð¾Ñ‡Ñƒ Ð¿Ñ€Ð¾ÑÑ‚Ð¾ Ð¿Ð¾Ð¾Ð±Ñ‰Ð°Ñ‚ÑŒÑÑ",
        "Ñ Ñ…Ð¾Ñ‡Ñƒ Ð¿Ð¾Ð¾Ð±Ñ‰Ð°Ñ‚ÑŒÑÑ",
        "Ñ…Ð¾Ñ‡Ñƒ Ð¿Ñ€Ð¾ÑÑ‚Ð¾ Ð¿Ð¾Ð³Ð¾Ð²Ð¾Ñ€Ð¸Ñ‚ÑŒ",
        "Ñ Ñ…Ð¾Ñ‚ÐµÐ» Ð±Ñ‹ Ð¿Ð¾Ð³Ð¾Ð²Ð¾Ñ€Ð¸Ñ‚ÑŒ",
        "Ñ…Ð¾Ñ‡Ñƒ Ð¿Ð¾Ð³Ð¾Ð²Ð¾Ñ€Ð¸Ñ‚ÑŒ",
        "Ð¿Ñ€Ð¾ÑÑ‚Ð¾ Ð¿Ð¾Ð³Ð¾Ð²Ð¾Ñ€Ð¸Ñ‚ÑŒ",
        "Ð¿Ñ€Ð¾ÑÑ‚Ð¾ Ð¿Ð¾Ð±Ð¾Ð»Ñ‚Ð°Ñ‚ÑŒ",
        "Ð¿Ð¾Ð±Ð¾Ð»Ñ‚Ð°Ð¹ ÑÐ¾ Ð¼Ð½Ð¾Ð¹",
        "ÐºÐ°Ðº Ñ Ð´Ñ€ÑƒÐ³Ð¾Ð¼",
        "ÐºÐ°Ðº Ð´Ñ€ÑƒÐ³Ð¾Ð¼",
        "ÐºÐ°Ðº Ð´Ñ€ÑƒÐ³",
        "Ð¸Ð¼ÐµÐ½Ð½Ð¾ Ñ Ñ‚Ð¾Ð±Ð¾Ð¹",
        "Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ñ Ñ‚Ð¾Ð±Ð¾Ð¹",
        "Ñ Ñ…Ð¾Ñ‡Ñƒ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ñ Ñ‚Ð¾Ð±Ð¾Ð¹",
        "Ð½Ðµ Ð¿Ñ€Ð¾ Ð´ÐµÐºÑ€Ð¾Ð²Ð°",
        "Ð½Ðµ Ð¿Ñ€Ð¾ assistant",
        "Ð½Ðµ Ñ…Ð¾Ñ‡Ñƒ Ð¿Ñ€Ð¾ Ð´ÐµÐºÑ€Ð¾Ð²Ð°",
        "Ð¼Ð½Ðµ Ð½Ðµ Ð½ÑƒÐ¶ÐµÐ½ Ð´ÐµÐºÑ€Ð¾Ð²",
        "Ð¼Ð½Ðµ Ð½Ðµ Ð½ÑƒÐ¶ÐµÐ½ assistant",
        "just chat",
        "just talk",
        "talk to you like a friend",
        "be my friend",
    )
    return any(marker in normalized for marker in markers)


def _looks_like_boundary_followup(text: str) -> bool:
    normalized = _normalize_support_text(text)
    if not normalized:
        return False
    if normalized in {"Ð½ÐµÑ‚", "Ð½ÐµÐ°", "Ð½Ðµ Ñ…Ð¾Ñ‡Ñƒ", "Ð½Ðµ Ñ…Ð¾Ñ‡Ñƒ ÑÑ‚Ð¾Ð³Ð¾", "Ð¿Ñ€Ð¾ÑÑ‚Ð¾ Ñ‚Ð°Ðº"}:
        return True
    markers = (
        "Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ñ Ñ‚Ð¾Ð±Ð¾Ð¹",
        "ÐºÐ°Ðº Ñ Ð´Ñ€ÑƒÐ³Ð¾Ð¼",
        "ÐºÐ°Ðº Ð´Ñ€ÑƒÐ³Ð¾Ð¼",
        "ÐºÐ°Ðº Ð´Ñ€ÑƒÐ³",
        "Ð¿Ñ€Ð¾ÑÑ‚Ð¾ Ð¾Ð±Ñ‰Ð°Ñ‚ÑŒÑÑ",
        "Ð¿Ñ€Ð¾ÑÑ‚Ð¾ Ð¿Ð¾Ð±Ð¾Ð»Ñ‚Ð°Ñ‚ÑŒ",
        "Ð½Ðµ Ð¿Ñ€Ð¾ Ð´ÐµÐºÑ€Ð¾Ð²Ð°",
        "Ð½Ðµ Ð¿Ñ€Ð¾ assistant",
    )
    return len(normalized) <= 80 and any(marker in normalized for marker in markers)


def _build_boundary_response(streak: int) -> tuple[str, bool]:
    if streak >= BOUNDARY_END_STREAK:
        return (
            "Ð¯ Ð½Ðµ Ð¼Ð¾Ð³Ñƒ Ð¿Ñ€Ð¾Ð´Ð¾Ð»Ð¶Ð°Ñ‚ÑŒ Ñ€Ð°Ð·Ð³Ð¾Ð²Ð¾Ñ€ Ð² Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚Ðµ Ð¿Ñ€Ð¾ÑÑ‚Ð¾Ð¹ Ð±Ð¾Ð»Ñ‚Ð¾Ð²Ð½Ð¸ Ð¸Ð»Ð¸ Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ \"ÐºÐ°Ðº Ð´Ñ€ÑƒÐ³\", "
            "Ð¿Ð¾ÑÑ‚Ð¾Ð¼Ñƒ Ð·Ð°Ð²ÐµÑ€ÑˆÑƒ ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸ÑŽ. Ð•ÑÐ»Ð¸ Ð¿Ð¾Ð·Ð¶Ðµ Ð¿Ð¾ÑÐ²Ð¸Ñ‚ÑÑ Ð²Ð¾Ð¿Ñ€Ð¾Ñ Ð¿Ð¾ ProjectOwner, Ð¿Ñ€Ð¾ÐµÐºÑ‚Ñƒ Ð¸Ð»Ð¸ Ð¸Ð´ÐµÐµ, "
            "Ð¼Ð¾Ð¶Ð½Ð¾ Ð±ÑƒÐ´ÐµÑ‚ Ð²ÐµÑ€Ð½ÑƒÑ‚ÑŒÑÑ Ðº ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸Ð¸ Ñ‡ÑƒÑ‚ÑŒ Ð¿Ð¾Ð·Ð¶Ðµ.",
            True,
        )
    if streak == 2:
        return (
            "Ð¯ Ð²ÑÑ‘ ÐµÑ‰Ñ‘ Ð½Ðµ Ð¼Ð¾Ð³Ñƒ Ð¿ÐµÑ€ÐµÐ¹Ñ‚Ð¸ Ð² Ñ€ÐµÐ¶Ð¸Ð¼ Ð´Ñ€ÑƒÐ¶ÐµÑÐºÐ¾Ð³Ð¾ Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ. "
            "Ð¯ Ð·Ð´ÐµÑÑŒ ÐºÐ°Ðº Ð°ÑÑÐ¸ÑÑ‚ÐµÐ½Ñ‚ ProjectOwner: Ð¼Ð¾Ð³Ñƒ Ð¿Ð¾Ð¼Ð¾Ñ‡ÑŒ Ñ Ð²Ð¾Ð¿Ñ€Ð¾ÑÐ¾Ð¼, Ð¸Ð´ÐµÐµÐ¹, Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð¾Ð¼ Ð¸Ð»Ð¸ Ñ„Ð¾Ñ€Ð¼ÑƒÐ»Ð¸Ñ€Ð¾Ð²ÐºÐ¾Ð¹ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ°. "
            "Ð•ÑÐ»Ð¸ Ð¿Ñ€Ð¾Ð´Ð¾Ð»Ð¶Ð¸Ð¼ Ð² Ñ‚Ð°ÐºÐ¾Ð¼ Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚Ðµ, Ñ Ð·Ð°Ð²ÐµÑ€ÑˆÑƒ ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸ÑŽ.",
            False,
        )
    return (
        "Ð¯ Ð½Ðµ Ð¼Ð¾Ð³Ñƒ Ð¾Ð±Ñ‰Ð°Ñ‚ÑŒÑÑ ÐºÐ°Ðº Ð´Ñ€ÑƒÐ³ Ð¸Ð»Ð¸ Ð¿Ñ€Ð¾ÑÑ‚Ð¾ Ð±Ð¾Ð»Ñ‚Ð°Ñ‚ÑŒ Ð±ÐµÐ· Ñ‚ÐµÐ¼Ñ‹. "
        "Ð¯ Ð·Ð´ÐµÑÑŒ ÐºÐ°Ðº Ð°ÑÑÐ¸ÑÑ‚ÐµÐ½Ñ‚ ProjectOwner: Ð¼Ð¾Ð³Ñƒ Ð¿Ð¾Ð¼Ð¾Ñ‡ÑŒ Ñ Ð¸Ð´ÐµÐµÐ¹, Ð²Ð¾Ð¿Ñ€Ð¾ÑÐ¾Ð¼, Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð¾Ð¼ Ð¸Ð»Ð¸ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸ÐµÐ¼ Ð´Ð»Ñ Ð½ÐµÐ³Ð¾. "
        "Ð•ÑÐ»Ð¸ Ñ…Ð¾Ñ‡ÐµÑˆÑŒ, Ð²Ñ‹Ð±ÐµÑ€ÐµÐ¼ Ð¾Ð´Ð½Ð¾ Ð¸Ð· ÑÑ‚Ð¾Ð³Ð¾.",
        False,
    )


def _format_restart_cooldown_message(remaining_seconds: int) -> str:
    remaining_minutes = max(1, math.ceil(remaining_seconds / 60))
    if remaining_minutes >= 60:
        remaining_hours = max(1, math.ceil(remaining_minutes / 60))
        return (
            "Ð¡ÐµÐ¹Ñ‡Ð°Ñ Ð½Ð¾Ð²ÑƒÑŽ ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸ÑŽ Ð½Ð°Ñ‡Ð°Ñ‚ÑŒ Ð½ÐµÐ»ÑŒÐ·Ñ: Ð¿Ñ€Ð¾ÑˆÐ»Ñ‹Ð¹ Ð´Ð¸Ð°Ð»Ð¾Ð³ ÑƒÑˆÑ‘Ð» Ð² Ð¿ÑƒÑÑ‚ÑƒÑŽ Ð±Ð¾Ð»Ñ‚Ð¾Ð²Ð½ÑŽ.\n\n"
            f"ÐŸÐ¾Ð¿Ñ€Ð¾Ð±ÑƒÐ¹Ñ‚Ðµ ÑÐ½Ð¾Ð²Ð° Ð¿Ñ€Ð¸Ð¼ÐµÑ€Ð½Ð¾ Ñ‡ÐµÑ€ÐµÐ· {remaining_hours} Ñ‡ Ð¸Ð»Ð¸ Ð²ÐµÑ€Ð½Ð¸Ñ‚ÐµÑÑŒ Ð¿Ð¾Ð·Ð¶Ðµ Ñ ÐºÐ¾Ð½ÐºÑ€ÐµÑ‚Ð½Ñ‹Ð¼ Ð²Ð¾Ð¿Ñ€Ð¾ÑÐ¾Ð¼."
        )
    return (
        "Ð¡ÐµÐ¹Ñ‡Ð°Ñ Ð½Ð¾Ð²ÑƒÑŽ ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸ÑŽ Ð½Ð°Ñ‡Ð°Ñ‚ÑŒ Ð½ÐµÐ»ÑŒÐ·Ñ: Ð¿Ñ€Ð¾ÑˆÐ»Ñ‹Ð¹ Ð´Ð¸Ð°Ð»Ð¾Ð³ ÑƒÑˆÑ‘Ð» Ð¾Ñ‚ Ñ‚ÐµÐ¼Ñ‹.\n\n"
        f"ÐŸÐ¾Ð¿Ñ€Ð¾Ð±ÑƒÐ¹Ñ‚Ðµ ÑÐ½Ð¾Ð²Ð° Ð¿Ñ€Ð¸Ð¼ÐµÑ€Ð½Ð¾ Ñ‡ÐµÑ€ÐµÐ· {remaining_minutes} Ð¼Ð¸Ð½ Ð¸Ð»Ð¸ Ð²ÐµÑ€Ð½Ð¸Ñ‚ÐµÑÑŒ Ð¿Ð¾Ð·Ð¶Ðµ Ñ ÐºÐ¾Ð½ÐºÑ€ÐµÑ‚Ð½Ñ‹Ð¼ Ð²Ð¾Ð¿Ñ€Ð¾ÑÐ¾Ð¼."
    )


def _last_assistant_message(ctx: VisitorContext) -> str:
    for item in reversed(ctx.conversation_history):
        if item.get("role") == "assistant":
            return str(item.get("content", "")).strip()
    return ""


def _assistant_invited_followup(ctx: VisitorContext) -> bool:
    last = _last_assistant_message(ctx).casefold()
    if not last:
        return False
    if "?" in last:
        return True
    markers = (
        "Ñ‡Ñ‚Ð¾ Ð¸Ð¼ÐµÐ½Ð½Ð¾",
        "ÐºÐ°ÐºÐ°Ñ",
        "ÐºÐ°ÐºÐ¾Ð¹",
        "ÐºÐ°ÐºÐ¾Ðµ",
        "Ñ€Ð°ÑÑÐºÐ°Ð¶Ð¸",
        "Ð¼Ð¾Ð¶ÐµÑˆÑŒ Ð½Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ",
        "Ð²Ñ‹Ð±ÐµÑ€ÐµÐ¼",
        "ÑƒÑ‚Ð¾Ñ‡Ð½Ð¸",
        "Ñ‡Ñ‚Ð¾ Ñ‚ÐµÐ±Ñ Ð¸Ð½Ñ‚ÐµÑ€ÐµÑÑƒÐµÑ‚",
        "Ñ Ñ‡ÐµÐ³Ð¾ Ð½Ð°Ñ‡Ð°Ñ‚ÑŒ",
    )
    return any(marker in last for marker in markers)


def _looks_like_contextual_followup(text: str, ctx: VisitorContext) -> bool:
    normalized = _normalize_support_text(text)
    if not normalized or not _assistant_invited_followup(ctx):
        return False
    followups = {
        "Ð´Ð°",
        "Ð½ÐµÑ‚",
        "Ð½Ðµ Ð·Ð½Ð°ÑŽ",
        "Ð½Ðµ ÑƒÐ²ÐµÑ€ÐµÐ½",
        "Ð½Ðµ ÑƒÐ²ÐµÑ€ÐµÐ½Ð°",
        "Ð¿Ð¾Ñ‡ÐµÐ¼Ñƒ",
        "Ð° Ð¿Ð¾Ñ‡ÐµÐ¼Ñƒ",
        "ÐºÐ°Ðº",
        "ÐºÐ°Ðº Ð¸Ð¼ÐµÐ½Ð½Ð¾",
        "Ñ‡Ñ‚Ð¾ Ð¸Ð¼ÐµÐ½Ð½Ð¾",
        "Ð¿Ð¾Ð´Ñ€Ð¾Ð±Ð½ÐµÐµ",
        "Ð¿Ñ€Ð¸Ð¼ÐµÑ€",
        "ÑÐºÐ¾Ð»ÑŒÐºÐ¾",
        "ÐºÐ¾Ð³Ð´Ð°",
        "Ð³Ð´Ðµ",
        "Ð² Ñ‡ÐµÐ¼",
        "Ð² Ñ‡Ñ‘Ð¼",
    }
    if normalized in followups:
        return True
    return len(normalized) <= 32 and normalized.endswith("?")


def _looks_like_meaningful_consultation_turn(
    text: str,
    decision: RouteDecision,
    ctx: VisitorContext,
    *,
    small_talk_reply: str | None = None,
) -> bool:
    normalized = _normalize_support_text(text)
    if not normalized:
        return False
    if small_talk_reply is not None:
        return False
    if _looks_like_contextual_followup(text, ctx):
        return True
    if _needs_request_planning_help(text):
        return True
    if _shows_uncertainty_or_shyness(text):
        return True
    if _looks_like_ready_request_brief(text):
        return True
    if decision.category in {
        TopicCategory.ABOUT_OWNER,
        TopicCategory.ABOUT_PROJECTS,
        TopicCategory.TECHNICAL_QUESTION,
        TopicCategory.PROJECT_SPECIFIC_QUESTION,
        TopicCategory.FAQ,
        TopicCategory.COLLABORATION,
        TopicCategory.LINKS,
        TopicCategory.ASSISTANT_CAPABILITIES,
    }:
        return True
    consultation_markers = (
        "assistant",
        "Ð´ÐµÐºÑ€Ð¾Ð²",
        "Ð±Ð¾Ñ‚",
        "ÑÐ°Ð¹Ñ‚",
        "telegram",
        "Ñ‚ÐµÐ»ÐµÐ³Ñ€Ð°Ð¼",
        "Ñ‚Ð³",
        "Ñ‚Ð³Ðº",
        "Ð¿Ñ€Ð¾ÐµÐºÑ‚",
        "Ð¸Ð´ÐµÑ",
        "ÑÐ¾Ñ‚Ñ€ÑƒÐ´Ð½Ð¸Ñ‡",
        "Ð±ÑŽÐ´Ð¶ÐµÑ‚",
        "ÑÑ€Ð¾Ðº",
        "Ð¿Ð¾Ñ€Ñ‚Ñ„Ð¾Ð»Ð¸Ð¾",
        "github",
        "ÐºÐ°Ð½Ð°Ð»",
        "ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ",
        "Ñ„Ð¾Ñ€Ð¼ÑƒÐ»Ð¸Ñ€Ð¾Ð²",
        "Ð·Ð°Ð´Ð°Ñ‡",
    )
    if any(marker in normalized for marker in consultation_markers):
        return True
    if any(ch.isdigit() for ch in normalized) and len(normalized) >= 24:
        return True
    return False


def _should_track_low_signal_turn(
    text: str,
    decision: RouteDecision,
    ctx: VisitorContext,
    *,
    small_talk_reply: str | None = None,
) -> bool:
    normalized = _normalize_support_text(text)
    if not normalized:
        return False
    if _looks_like_meaningful_consultation_turn(
        text,
        decision,
        ctx,
        small_talk_reply=small_talk_reply,
    ):
        return False
    if small_talk_reply is not None:
        return True
    if decision.category not in {
        TopicCategory.GENERAL,
        TopicCategory.GREETING,
        TopicCategory.DISALLOWED_OFFTOPIC,
    }:
        return False
    exact = {
        "Ð½Ñƒ",
        "Ð½ÑƒÑƒ",
        "Ð¾Ðº",
        "Ð¾ÐºÐµÐ¹",
        "Ð»Ð°Ð´Ð½Ð¾",
        "ÑÑÐ½Ð¾",
        "Ð¿Ð¾Ð½ÑÐ»",
        "Ð¿Ð¾Ð½ÑÐ»Ð°",
        "Ð¿Ð¾Ð½",
        "Ñ…Ð·",
        "Ð½Ðµ Ð·Ð½Ð°ÑŽ",
        "Ð½Ðµ Ð·Ð½Ð°ÑŽ Ð´Ð°Ð¶Ðµ",
        "Ð½Ð¸Ñ‡ÐµÐ³Ð¾",
        "Ð¿Ñ€Ð¾ÑÑ‚Ð¾",
        "Ð¸ Ñ‡Ñ‚Ð¾",
        "Ñ‡Ñ‚Ð¾ Ð´Ð°Ð»ÑŒÑˆÐµ",
        "Ð° Ð´Ð°Ð»ÑŒÑˆÐµ",
        "Ð½ÐµÑ‚Ñƒ",
        "Ð½ÐµÐ°",
        "Ð°Ð³Ð°",
    }
    if normalized in exact:
        return True
    markers = (
        "ÐºÐ°Ðº Ð´ÐµÐ»Ð°",
        "ÐºÐ°Ðº Ñƒ Ñ‚ÐµÐ±Ñ Ð´ÐµÐ»Ð°",
        "ÐºÐ°Ðº Ñ‚Ñ‹",
        "Ñ‡Ñ‚Ð¾ Ð´ÐµÐ»Ð°ÐµÑˆÑŒ",
        "Ñ‡ÐµÐ¼ Ð·Ð°Ð½Ð¸Ð¼Ð°ÐµÑˆÑŒÑÑ",
        "just chat",
        "small talk",
    )
    if any(marker in normalized for marker in markers):
        return True
    return len(normalized) <= 40 and len(normalized.split()) <= 5


def _build_low_signal_response(streak: int) -> tuple[str | None, bool]:
    if streak >= LOW_SIGNAL_END_STREAK:
        return (
            "ÐŸÐ¾Ñ…Ð¾Ð¶Ðµ, ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸Ñ ÑƒÑˆÐ»Ð° Ð² Ñ€Ð°Ð·Ð³Ð¾Ð²Ð¾Ñ€ Ð±ÐµÐ· Ð¿Ð¾Ð½ÑÑ‚Ð½Ð¾Ð¹ Ñ‚ÐµÐ¼Ñ‹, Ð¿Ð¾ÑÑ‚Ð¾Ð¼Ñƒ Ñ ÐµÑ‘ Ð·Ð°Ð²ÐµÑ€ÑˆÑƒ. "
            "ÐšÐ¾Ð³Ð´Ð° Ð¿Ð¾ÑÐ²Ð¸Ñ‚ÑÑ ÐºÐ¾Ð½ÐºÑ€ÐµÑ‚Ð½Ñ‹Ð¹ Ð²Ð¾Ð¿Ñ€Ð¾Ñ Ð¿Ñ€Ð¾ ProjectOwner, Ð¿Ñ€Ð¾ÐµÐºÑ‚, Ð¸Ð´ÐµÑŽ Ð¸Ð»Ð¸ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ Ð´Ð»Ñ Ð½ÐµÐ³Ð¾, "
            "Ð¼Ð¾Ð¶Ð½Ð¾ Ð±ÑƒÐ´ÐµÑ‚ Ð²ÐµÑ€Ð½ÑƒÑ‚ÑŒÑÑ Ñ‡ÑƒÑ‚ÑŒ Ð¿Ð¾Ð·Ð¶Ðµ.",
            True,
        )
    if streak >= LOW_SIGNAL_WARNING_STREAK:
        return (
            "ÐŸÐ¾Ñ…Ð¾Ð¶Ðµ, Ñ€Ð°Ð·Ð³Ð¾Ð²Ð¾Ñ€ ÑƒÑ…Ð¾Ð´Ð¸Ñ‚ Ð² ÑÑ‚Ð¾Ñ€Ð¾Ð½Ñƒ Ð±ÐµÐ· Ð¿Ð¾Ð½ÑÑ‚Ð½Ð¾Ð¹ Ñ‚ÐµÐ¼Ñ‹. "
            "Ð¯ Ð»ÑƒÑ‡ÑˆÐµ Ð²ÑÐµÐ³Ð¾ Ð¿Ð¾Ð¼Ð¾Ð³Ð°ÑŽ, ÐºÐ¾Ð³Ð´Ð° ÐµÑÑ‚ÑŒ ÐºÐ¾Ð½ÐºÑ€ÐµÑ‚Ð½Ñ‹Ð¹ Ð²Ð¾Ð¿Ñ€Ð¾Ñ, Ð¸Ð´ÐµÑ, Ð¿Ñ€Ð¾ÐµÐºÑ‚ Ð¸Ð»Ð¸ Ð·Ð°Ð¿Ñ€Ð¾Ñ Ðº ProjectOwner. "
            "Ð•ÑÐ»Ð¸ Ð¿Ñ€Ð¾Ð´Ð¾Ð»Ð¶Ð¸Ð¼ Ð±ÐµÐ· Ñ‚ÐµÐ¼Ñ‹, Ñ Ð·Ð°Ð²ÐµÑ€ÑˆÑƒ ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸ÑŽ.",
            False,
        )
    if streak >= LOW_SIGNAL_SOFT_STREAK:
        return (
            "ÐœÐ¾Ð³Ñƒ ÐºÐ¾Ñ€Ð¾Ñ‚ÐºÐ¾ Ð¿Ð¾Ð´Ð´ÐµÑ€Ð¶Ð°Ñ‚ÑŒ Ñ€Ð°Ð·Ð³Ð¾Ð²Ð¾Ñ€, Ð½Ð¾ Ð²ÑÑ‘ Ð¶Ðµ Ñ Ð·Ð´ÐµÑÑŒ ÐºÐ°Ðº Ð°ÑÑÐ¸ÑÑ‚ÐµÐ½Ñ‚ ProjectOwner. "
            "Ð›ÑƒÑ‡ÑˆÐµ Ð²ÑÐµÐ³Ð¾ Ñ Ð¿Ð¾Ð¼Ð¾Ð³Ð°ÑŽ, ÐºÐ¾Ð³Ð´Ð° ÐµÑÑ‚ÑŒ ÐºÐ¾Ð½ÐºÑ€ÐµÑ‚Ð½Ð°Ñ Ñ‚ÐµÐ¼Ð°: Ð¸Ð´ÐµÑ, Ð¿Ñ€Ð¾ÐµÐºÑ‚, Ð²Ð¾Ð¿Ñ€Ð¾Ñ Ð¾ ProjectOwner "
            "Ð¸Ð»Ð¸ Ð¿Ð¾Ð¼Ð¾Ñ‰ÑŒ Ñ Ñ„Ð¾Ñ€Ð¼ÑƒÐ»Ð¸Ñ€Ð¾Ð²ÐºÐ¾Ð¹ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ.",
            False,
        )
    return None, False


def _build_visitor_ai_failure_response(text: str, decision: RouteDecision) -> str:
    normalized = _normalize_support_text(text)
    if any(marker in normalized for marker in ("Ð¿Ð¾Ñ‡ÐµÐ¼Ñƒ", "why")):
        return (
            "ÐŸÐ¾Ñ…Ð¾Ð¶Ðµ, Ð¼Ð¾Ð¹ Ð¿Ñ€Ð¾ÑˆÐ»Ñ‹Ð¹ Ð¾Ñ‚Ð²ÐµÑ‚ Ð½Ðµ ÑÑ€Ð°Ð±Ð¾Ñ‚Ð°Ð» ÐºÐ°Ðº Ð½Ð°Ð´Ð¾. "
            "ÐšÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸Ñ Ð²ÑÑ‘ ÐµÑ‰Ñ‘ Ð°ÐºÑ‚Ð¸Ð²Ð½Ð°, Ñ‚Ð°Ðº Ñ‡Ñ‚Ð¾ Ð¼Ð¾Ð¶ÐµÑ‚Ðµ Ð½Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ ÐµÑ‰Ñ‘ Ñ€Ð°Ð·, Ñ‡Ñ‚Ð¾ Ð¸Ð¼ÐµÐ½Ð½Ð¾ Ñ…Ð¾Ñ‚Ð¸Ñ‚Ðµ Ð¾Ð±ÑÑƒÐ´Ð¸Ñ‚ÑŒ, "
            "Ð¸ Ñ Ð¿Ð¾ÑÑ‚Ð°Ñ€Ð°ÑŽÑÑŒ Ð¾Ñ‚Ð²ÐµÑ‚Ð¸Ñ‚ÑŒ Ð¿Ð¾Ð½ÑÑ‚Ð½ÐµÐµ."
        )
    if decision.category.value in {"general", "greeting", "collaboration"}:
        return (
            "ÐŸÐ¾Ñ…Ð¾Ð¶Ðµ, Ñ ÑÐµÐ¹Ñ‡Ð°Ñ Ð½Ðµ ÑÐ¼Ð¾Ð³ Ð½Ð¾Ñ€Ð¼Ð°Ð»ÑŒÐ½Ð¾ Ð¿Ñ€Ð¾Ð´Ð¾Ð»Ð¶Ð¸Ñ‚ÑŒ Ð¾Ñ‚Ð²ÐµÑ‚. "
            "ÐÐ¾ ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸Ñ Ð²ÑÑ‘ ÐµÑ‰Ñ‘ Ð°ÐºÑ‚Ð¸Ð²Ð½Ð°, Ñ‚Ð°Ðº Ñ‡Ñ‚Ð¾ Ð¼Ð¾Ð¶ÐµÑ‚Ðµ Ð½Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ ÐµÑ‰Ñ‘ Ñ€Ð°Ð· Ð¸Ð»Ð¸ ÑƒÑ‚Ð¾Ñ‡Ð½Ð¸Ñ‚ÑŒ, "
            "Ð¾ Ñ‡Ñ‘Ð¼ Ð¸Ð¼ÐµÐ½Ð½Ð¾ Ñ…Ð¾Ñ‚Ð¸Ñ‚Ðµ Ð¿Ð¾Ð³Ð¾Ð²Ð¾Ñ€Ð¸Ñ‚ÑŒ."
        )
    if decision.category.value in {"about_projects", "project_specific_question", "links"}:
        return (
            "ÐŸÐ¾Ñ…Ð¾Ð¶Ðµ, Ñ ÑÐµÐ¹Ñ‡Ð°Ñ Ð½Ðµ ÑÐ¼Ð¾Ð³ Ð½Ð¾Ñ€Ð¼Ð°Ð»ÑŒÐ½Ð¾ ÑÐ¾Ð±Ñ€Ð°Ñ‚ÑŒ Ð¾Ñ‚Ð²ÐµÑ‚ Ð¿Ð¾ ÑÑ‚Ð¾Ð¼Ñƒ Ð·Ð°Ð¿Ñ€Ð¾ÑÑƒ. "
            "ÐŸÐ¾Ð¿Ñ€Ð¾Ð±ÑƒÐ¹Ñ‚Ðµ ÐµÑ‰Ñ‘ Ñ€Ð°Ð· Ð¸Ð»Ð¸ ÑƒÑ‚Ð¾Ñ‡Ð½Ð¸Ñ‚Ðµ, Ñ‡Ñ‚Ð¾ Ð¸Ð¼ÐµÐ½Ð½Ð¾ Ð²Ð°Ð¼ Ð½ÑƒÐ¶Ð½Ð¾: Ð¿Ñ€Ð¾ÐµÐºÑ‚, ÑÑÑ‹Ð»ÐºÐ°, Ð¿Ñ€Ð¸Ð¼ÐµÑ€ Ð¸Ð»Ð¸ Ð¾Ð¿Ð¸ÑÐ°Ð½Ð¸Ðµ."
        )
    return (
        "ÐŸÐ¾Ñ…Ð¾Ð¶Ðµ, Ñ ÑÐµÐ¹Ñ‡Ð°Ñ Ð¾Ñ‚Ð²ÐµÑ‚Ð¸Ð» Ð½ÐµÑƒÐ´Ð°Ñ‡Ð½Ð¾. "
        "ÐœÐ¾Ð¶ÐµÑ‚Ðµ Ð¿Ñ€Ð¾Ð´Ð¾Ð»Ð¶Ð¸Ñ‚ÑŒ Ð¼Ñ‹ÑÐ»ÑŒ Ð¸Ð»Ð¸ Ð¿ÐµÑ€ÐµÑ„Ð¾Ñ€Ð¼ÑƒÐ»Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ Ð·Ð°Ð¿Ñ€Ð¾Ñ, Ð¸ Ñ Ð¿Ð¾ÑÑ‚Ð°Ñ€Ð°ÑŽÑÑŒ Ð¿Ð¾Ð¼Ð¾Ñ‡ÑŒ Ð½Ð¾Ñ€Ð¼Ð°Ð»ÑŒÐ½Ð¾."
    )


class VisitorService:
    """Thin orchestrator â€” delegates to router, context, search, AI.
    Contains NO business logic.
    """

    def __init__(
        self,
        config: AppConfig,
        groq_client: GroqClient,
        owner_knowledge_store: OwnerKnowledgeStore,
    ) -> None:
        self._config = config
        self._groq = groq_client
        self._knowledge = owner_knowledge_store
        timeout = getattr(config, "visitor_session_timeout_minutes", 10)
        base_dir = getattr(config, "base_dir", None)
        sessions_path = None
        inbox_path = None
        judge_path = None
        if base_dir is not None:
            data_dir = Path(base_dir) / "data"
            sessions_path = data_dir / "visitor_sessions.json"
            inbox_path = data_dir / "visitor_inbox.json"
            judge_path = data_dir / "visitor_judge.json"
        self._sessions = VisitorSessionStore(
            timeout_minutes=timeout,
            path=sessions_path,
        )
        self._stats = VisitorStats()
        self._admin = VisitorAdminPanel(self)
        self._faq = VisitorFaqCache()
        self._notify_owner_fn = None  # set by chat_bot after init
        self._public_channel_reader_fn = None
        self._inbox = VisitorInbox(path=inbox_path)
        self._judge_store = VisitorJudgeStore(path=judge_path)

    @property
    def sessions(self) -> VisitorSessionStore:
        return self._sessions

    @property
    def stats(self) -> VisitorStats:
        return self._stats

    @property
    def admin(self) -> VisitorAdminPanel:
        return self._admin

    def set_notify_fn(self, fn) -> None:
        """Set async function for notifying owner. Called by chat_bot."""
        self._notify_owner_fn = fn

    def set_public_channel_reader(self, fn) -> None:
        """Set async callback for reading public Telegram channel posts."""
        self._public_channel_reader_fn = fn

    @property
    def faq(self) -> VisitorFaqCache:
        return self._faq

    @property
    def inbox(self) -> VisitorInbox:
        return self._inbox

    async def load(self) -> None:
        await self._sessions.load()
        await self._inbox.load()
        await self._inbox.cleanup_expired()
        await self._judge_store.load()

    async def reset_user_state(self, user_id: int) -> None:
        await self._sessions.end_session(user_id)
        await self._inbox.cancel_question(user_id)

    async def get_restriction_message(self, user_id: int) -> str | None:
        if await self._sessions.is_blocked(user_id):
            self._stats.total_blocked += 1
            return BLOCKED_MESSAGE

        remaining = await self._sessions.get_temporary_block_remaining(user_id)
        if remaining > 0:
            self._stats.total_blocked += 1
            return _format_temporary_block_message(remaining)
        restart_cooldown = await self._sessions.get_restart_cooldown_remaining(user_id)
        if restart_cooldown > 0:
            return _format_restart_cooldown_message(restart_cooldown)
        return None

    async def _notify_moderation_event(
        self,
        *,
        user_id: int,
        text: str,
        reason_label: str,
        strikes: int,
        blocked_now: bool,
        source: str,
        username: str | None = None,
        first_name: str | None = None,
    ) -> None:
        owner_id = getattr(self._config, "owner_user_id", None)
        if not owner_id or self._notify_owner_fn is None:
            return
        try:
            await self._notify_owner_fn(
                owner_id,
                format_moderation_owner_notification(
                    user_id=user_id,
                    username=username,
                    first_name=first_name,
                    text=text,
                    reason_label=reason_label,
                    strikes=strikes,
                    blocked_now=blocked_now,
                    source=source,
                ),
            )
        except Exception as exc:
            LOGGER.warning("visitor_moderation_notify_error: %s", exc)

    def _spawn_background_task(self, coro) -> None:
        task = asyncio.create_task(coro)
        task.add_done_callback(self._consume_background_task)

    @staticmethod
    def _consume_background_task(task: asyncio.Task) -> None:
        try:
            task.result()
        except Exception:
            LOGGER.exception("visitor_background_task_failed")

    async def _review_and_notify_owner(
        self,
        *,
        user_id: int,
        user_text: str,
        answer: str,
        decision: RouteDecision,
    ) -> None:
        if not getattr(self._config, "visitor_judge_enabled", False):
            return
        if not hasattr(self._groq, "generate_visitor_judge_completion"):
            return
        if not should_review_visitor_response(
            user_text,
            answer,
            category_value=decision.category.value,
            route_value=decision.route.value,
        ):
            return

        owner_id = getattr(self._config, "owner_user_id", None)
        if not owner_id or self._notify_owner_fn is None:
            return

        raw_verdict = await self._groq.generate_visitor_judge_completion(
            messages=build_visitor_judge_messages(
                user_text=user_text,
                answer=answer,
                category_value=decision.category.value,
                route_value=decision.route.value,
            ),
            model=getattr(self._config, "visitor_judge_model", "openai/gpt-oss-safeguard-20b"),
            max_tokens=180,
        )
        verdict = parse_visitor_judge_response(raw_verdict or "")
        if (
            not verdict.flagged
            or verdict.confidence < 0.68
            or not verdict.issues
        ):
            return

        signature = build_incident_signature(
            category_value=decision.category.value,
            route_value=decision.route.value,
            issues=verdict.issues,
        )
        incident, should_alert = await self._judge_store.register_incident(
            signature=signature,
            severity=verdict.severity,
            summary=verdict.summary,
            repeat_threshold=max(1, int(getattr(self._config, "visitor_judge_repeat_threshold", 2))),
            repeat_window_seconds=max(3600, int(getattr(self._config, "visitor_judge_repeat_window_seconds", 259200))),
            alert_cooldown_seconds=max(300, int(getattr(self._config, "visitor_judge_alert_cooldown_seconds", 43200))),
        )
        if not should_alert:
            return

        ctx = await self._sessions.get_or_create(user_id)
        try:
            await self._notify_owner_fn(
                owner_id,
                format_visitor_judge_notification(
                    user_id=user_id,
                    username=ctx.username,
                    first_name=ctx.first_name,
                    user_text=user_text,
                    answer=answer,
                    category_value=decision.category.value,
                    route_value=decision.route.value,
                    verdict=verdict,
                    incident=incident,
                ),
            )
        except Exception as exc:
            LOGGER.warning("visitor_judge_notify_error: %s", exc)

    async def moderate_text(
        self,
        user_id: int,
        text: str,
        *,
        username: str | None = None,
        first_name: str | None = None,
        source: str = "visitor",
    ) -> str | None:
        restriction = await self.get_restriction_message(user_id)
        if restriction is not None:
            return restriction

        if username or first_name:
            await self._sessions.update_identity(
                user_id,
                username=username,
                first_name=first_name,
            )

        hit = detect_abusive_message(text)
        if hit is None:
            return None

        ctx, blocked_now, should_notify = await self._sessions.register_abuse(
            user_id,
            reason=hit.reason,
            text=text,
            strike_threshold=ABUSE_STRIKE_THRESHOLD,
            temporary_block_seconds=TEMPORARY_BLOCK_SECONDS,
        )
        if blocked_now:
            await self.reset_user_state(user_id)

        effective_username = username or ctx.username
        effective_first_name = first_name or ctx.first_name
        if should_notify:
            await self._notify_moderation_event(
                user_id=user_id,
                text=text,
                reason_label=hit.label,
                strikes=ctx.abuse_strikes,
                blocked_now=blocked_now,
                source=source,
                username=effective_username,
                first_name=effective_first_name,
            )

        if blocked_now:
            return _format_temporary_block_message(TEMPORARY_BLOCK_SECONDS)

        if hit.reason == "threat":
            return build_non_owner_threat_refusal(_detect_language(text))

        return ABUSE_WARNING_MESSAGE

    # ========================
    # ENTRY POINTS
    # ========================

    async def handle_start(self) -> tuple[str, "InlineKeyboardMarkup"]:
        from .visitor_keyboards import visitor_main_menu
        return WELCOME_TEXT, visitor_main_menu()

    async def handle_start_disabled(self) -> tuple[str, "InlineKeyboardMarkup"]:
        """Handle /start when visitor mode is disabled â€” show read-only menu."""
        from .visitor_keyboards import visitor_disabled_menu
        return VISITOR_DISABLED_TEXT, visitor_disabled_menu()

    async def handle_callback(
        self, data: str, user_id: int, visitor_mode_enabled: bool = True
    ) -> tuple[str, "InlineKeyboardMarkup | None"]:
        from .visitor_keyboards import (
            visitor_main_menu,
            visitor_chat_active_menu,
            visitor_back_menu,
            visitor_cancel_menu,
            visitor_disabled_menu,
        )

        self._stats.total_messages += 1

        # Admin panel callbacks
        if data.startswith("vadmin_"):
            return await self._admin.handle_callback(data)

        # Handle "start chat" - only disabled when visitor mode is OFF
        if data == "visitor_start_chat":
            if not visitor_mode_enabled:
                # Return special marker for chat_bot to show alert
                return "VISITOR_DISABLED_START", visitor_disabled_menu()
            # Visitor mode enabled - start normal chat session
            return await self._start_chat(user_id)

        # Handle cancel question
        if data == "visitor_cancel_question":
            await self._inbox.cancel_question(user_id)
            return "âŒ Ð’Ð¾Ð¿Ñ€Ð¾Ñ Ð¾Ñ‚Ð¼ÐµÐ½Ñ‘Ð½.", visitor_disabled_menu()

        # Block "ask owner" when visitor mode is disabled
        if data == "visitor_ask_owner" and not visitor_mode_enabled:
            return "VISITOR_DISABLED_ASK_OWNER", visitor_disabled_menu()

        handlers = {
            "visitor_menu": lambda: self.handle_start(),
            "visitor_end": lambda: self._end_chat(user_id),
            "visitor_about_owner": lambda: self._knowledge_callback("about_owner"),
            "visitor_projects": lambda: self._knowledge_callback("projects"),
            "visitor_links": lambda: self._knowledge_callback("links"),
            "visitor_capabilities": lambda: self._static(_FALLBACK_CAPABILITIES),
            "visitor_faq": lambda: self._knowledge_callback("faq"),
            "visitor_collaboration": lambda: self._knowledge_callback("collaboration"),
            "visitor_ask_owner": lambda: self._ask_owner_start(user_id),
        }
        handler = handlers.get(data)
        if handler:
            return await handler()
        return "ÐÐµÐ¸Ð·Ð²ÐµÑÑ‚Ð½Ð°Ñ ÐºÐ¾Ð¼Ð°Ð½Ð´Ð°.", visitor_back_menu()

    async def _start_chat(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> tuple[str, "InlineKeyboardMarkup"]:
        from .visitor_keyboards import visitor_back_menu, visitor_chat_active_menu
        restriction = await self.get_restriction_message(user_id)
        if restriction is not None:
            return restriction, visitor_back_menu()
        await self._sessions.start_session(user_id, username=username, first_name=first_name)
        self._stats.total_sessions += 1
        return SESSION_STARTED, visitor_chat_active_menu()

    async def _end_chat(self, user_id: int) -> tuple[str, "InlineKeyboardMarkup"]:
        from .visitor_keyboards import visitor_back_menu
        await self._sessions.end_session(user_id)
        return SESSION_ENDED, visitor_back_menu()

    async def _static(self, text: str) -> tuple[str, "InlineKeyboardMarkup"]:
        from .visitor_keyboards import visitor_back_menu
        return text, visitor_back_menu()

    async def _knowledge_callback(
        self, topic: str
    ) -> tuple[str, "InlineKeyboardMarkup"]:
        """Serve button callbacks using structured cards â€” no AI."""
        from .visitor_keyboards import visitor_back_menu
        from .visitor_cards import parse_knowledge, build_card

        # Get raw markdown knowledge (not the formatted prompt block)
        raw_knowledge = await self._knowledge.get_raw_public_knowledge()

        # Parse knowledge into structured profile
        profile = parse_knowledge(raw_knowledge)

        # Build card from template
        card_html = build_card(topic, profile, raw_knowledge)

        return card_html, visitor_back_menu()

    async def _ask_owner_start(
        self, user_id: int
    ) -> tuple[str, "InlineKeyboardMarkup"]:
        """Start 'ask owner' flow â€” mark user as awaiting question."""
        from .visitor_keyboards import visitor_back_menu, visitor_cancel_menu
        restriction = await self.get_restriction_message(user_id)
        if restriction is not None:
            return restriction, visitor_back_menu()
        await self._inbox.set_awaiting_question(user_id)
        return AWAITING_QUESTION_MESSAGE, visitor_cancel_menu()

    async def _quick_ai_answer(self, question: str, knowledge: str) -> str | None:
        """One-shot AI call for button callbacks. No history."""
        context = format_knowledge_for_prompt(knowledge)
        prompt = build_visitor_system_prompt(context)
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": question},
        ]
        try:
            self._stats.total_ai_calls += 1
            result = await self._groq.generate_visitor_completion(
                messages=messages,
                model=getattr(self._config, 'visitor_primary_model', 'llama-3.3-70b-versatile'),
                max_tokens=getattr(self._config, 'visitor_max_output_tokens', 600),
                temperature=getattr(self._config, 'visitor_temperature', 0.5),
                user_query=question,
            )
            # Format response for better readability
            if result:
                result = _format_visitor_response(result)
            return result
        except Exception as exc:
            LOGGER.warning("quick_ai_error: %s", exc)
            return None

    # ========================
    # TEXT HANDLER â€” THE PIPELINE
    # ========================

    async def handle_text(
        self,
        user_id: int,
        text: str,
        username: str | None = None,
        first_name: str | None = None,
    ) -> tuple[str, "InlineKeyboardMarkup | None"]:
        """Pipeline: classify â†’ route â†’ resolve â†’ respond.
        Returns (text, optional_markup).
        """
        self._stats.total_messages += 1

        # Quiet mode
        if self._admin.quiet_mode:
            return QUIET_MODE_MESSAGE, None

        moderation_reply = await self.moderate_text(
            user_id,
            text,
            username=username,
            first_name=first_name,
            source="visitor",
        )
        if moderation_reply is not None:
            return moderation_reply, None

        # Step 0b: Inbox - user is answering "ask owner" flow.
        # This must work even without an active consultation session.
        if await self._inbox.is_awaiting_question(user_id):
            if len(text) > MAX_MESSAGE_LENGTH:
                return (
                    f"DÂ­D_D_DÃ±Â¥%DÃ¦DÂ«D,DÃ¦ Â¥?DÂ¯D,Â¥^DÂ§D_DÂ¬ D'DÂ¯D,DÂ«DÂ«D_DÃ¦ (DÂ¬DÃ¸DÂ§Â¥?D,DÂ¬Â¥Å¸DÂ¬ {MAX_MESSAGE_LENGTH} Â¥?D,DÂ¬DÃ½D_DÂ¯D_DÃ½).",
                    None,
                )
            if text.lower() in ("/cancel", "D_Â¥,DÂ¬DÃ¦DÂ«DÃ¸", "cancel"):
                await self._inbox.cancel_question(user_id)
                return "DzÂ¥,DÂ¬DÃ¦DÂ«DÃ¦DÂ«D_.", None

            stored_ctx = await self._sessions.update_identity(
                user_id,
                username=username,
                first_name=first_name,
            )

            effective_username = username or getattr(stored_ctx, "username", None)
            effective_first_name = first_name or getattr(stored_ctx, "first_name", None)

            msg = await self._inbox.submit_question(
                user_id,
                text,
                username=effective_username,
                first_name=effective_first_name,
            )
            owner_id = getattr(self._config, 'owner_user_id', None)
            if owner_id and self._notify_owner_fn:
                try:
                    await self._notify_owner_fn(owner_id, format_owner_notification(msg))
                except Exception as exc:
                    LOGGER.warning("inbox_notify_error: %s", exc)
            return QUESTION_SENT_MESSAGE, None

        # Session check
        if not await self._sessions.is_active(user_id):
            restriction = await self.get_restriction_message(user_id)
            if restriction is not None:
                return restriction, None
            return NO_SESSION_MESSAGE, None

        # Message length check
        if len(text) > MAX_MESSAGE_LENGTH:
            return f"Ð¡Ð¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ ÑÐ»Ð¸ÑˆÐºÐ¾Ð¼ Ð´Ð»Ð¸Ð½Ð½Ð¾Ðµ (Ð¼Ð°ÐºÑÐ¸Ð¼ÑƒÐ¼ {MAX_MESSAGE_LENGTH} ÑÐ¸Ð¼Ð²Ð¾Ð»Ð¾Ð²).", None

        # Rate limiting
        if await self._sessions.check_rate_limit(user_id, max_per_minute=10):
            self._stats.total_rate_limited += 1
            ctx = await self._sessions.set_temporary_block(
                user_id,
                seconds=TEMPORARY_BLOCK_SECONDS,
                reason="rate_limit",
                text=text,
            )
            await self.reset_user_state(user_id)
            await self._notify_moderation_event(
                user_id=user_id,
                text=text,
                reason_label="ÑÐ¿Ð°Ð¼ / rate limit",
                strikes=max(ctx.abuse_strikes, 1),
                blocked_now=True,
                source="visitor",
                username=username or ctx.username,
                first_name=first_name or ctx.first_name,
            )
            return RATE_LIMIT_BLOCK_MESSAGE, None

        # Update user metadata
        if username or first_name:
            await self._sessions.update_identity(
                user_id,
                username=username,
                first_name=first_name,
            )

        ctx = await self._sessions.get_or_create(user_id)
        if _looks_like_friend_chat_request(text) or (
            ctx.boundary_streak > 0 and _looks_like_boundary_followup(text)
        ):
            streak = await self._sessions.register_boundary_attempt(user_id)
            boundary_reply, should_end = _build_boundary_response(streak)
            await self._sessions.add_exchange(
                user_id,
                user_text=text,
                assistant_text=_history_safe_text(boundary_reply),
            )
            if should_end:
                cooldown_minutes = max(
                    5,
                    int(
                        getattr(
                            self._config,
                            "visitor_restart_cooldown_minutes",
                            RESTART_COOLDOWN_MINUTES,
                        )
                    ),
                )
                await self._sessions.end_session_with_cooldown(
                    user_id,
                    seconds=cooldown_minutes * 60,
                )
            return boundary_reply, None

        await self._sessions.reset_boundary_streak(user_id)

        # Step 1: Route
        decision = route_query(text)
        small_talk = _build_small_talk_response(text)

        meaningful_turn = _looks_like_meaningful_consultation_turn(
            text,
            decision,
            ctx,
            small_talk_reply=small_talk,
        )
        low_signal_turn = _should_track_low_signal_turn(
            text,
            decision,
            ctx,
            small_talk_reply=small_talk,
        )

        if meaningful_turn:
            await self._sessions.reset_low_signal_streak(user_id)

        if low_signal_turn:
            streak = await self._sessions.register_low_signal(
                user_id,
                reset_window_seconds=LOW_SIGNAL_RESET_WINDOW_SECONDS,
            )
            low_signal_reply, should_end = _build_low_signal_response(streak)
            final_reply = low_signal_reply or small_talk
            if final_reply is not None:
                await self._sessions.add_exchange(
                    user_id,
                    user_text=text,
                    assistant_text=_history_safe_text(final_reply),
                )
                if should_end:
                    cooldown_minutes = max(
                        5,
                        int(
                            getattr(
                                self._config,
                                "visitor_restart_cooldown_minutes",
                                RESTART_COOLDOWN_MINUTES,
                            )
                        ),
                    )
                    await self._sessions.end_session_with_cooldown(
                        user_id,
                        seconds=cooldown_minutes * 60,
                    )
                return final_reply, None
        else:
            await self._sessions.reset_low_signal_streak(user_id)

        if small_talk:
            await self._sessions.add_exchange(
                user_id,
                user_text=text,
                assistant_text=_history_safe_text(small_talk),
            )
            return small_talk, None

        # Step 0a: Easter egg check (before anything)
        egg = check_easter_egg(text)
        if egg:
            await self._sessions.add_exchange(
                user_id,
                user_text=text,
                assistant_text=_history_safe_text(egg),
            )
            return egg, None

        # Step 0c: FAQ cache check (fast, no AI cost)
        faq_answer = await self._faq.match(text)
        if faq_answer:
            await self._sessions.add_exchange(
                user_id,
                user_text=text,
                assistant_text=_history_safe_text(faq_answer),
            )
            return faq_answer, None

        # Step 2: Track topic
        await self._sessions.record_topic(user_id, decision.category.value)

        # Step 3: Handle rejections
        if decision.redirect_message:
            self._stats.total_redirects += 1
            await self._sessions.add_exchange(
                user_id,
                user_text=text,
                assistant_text=_history_safe_text(decision.redirect_message),
            )
            return decision.redirect_message, None

        # Step 4: Resolve
        answer = await self._resolve(user_id, text, decision)

        # Step 5: Format and handle AI end suggestion
        markup = None
        if "[END_SUGGESTION]" in answer:
            answer = answer.replace("[END_SUGGESTION]", "").strip()
            from .visitor_keyboards import visitor_end_suggestion_menu
            markup = visitor_end_suggestion_menu()
            await self._sessions.set_ai_offered_end(user_id)

        # Format response for better readability
        answer = _format_visitor_response(answer)
        await self._sessions.add_exchange(
            user_id,
            user_text=text,
            assistant_text=_history_safe_text(answer),
        )

        self._spawn_background_task(
            self._review_and_notify_owner(
                user_id=user_id,
                user_text=text,
                answer=answer,
                decision=decision,
            )
        )

        return answer, markup

    # ========================
    # RESOLUTION ENGINE
    # ========================

    async def _resolve(self, user_id: int, text: str, decision: RouteDecision) -> str:
        """Source hierarchy: knowledge â†’ local â†’ search â†’ AI."""

        prompt_knowledge = await self._knowledge.get_prompt_block()
        safe_knowledge = build_safe_visitor_context(prompt_knowledge)
        raw_public_knowledge = await self._knowledge.get_raw_public_knowledge()

        local_data = self._get_local_data(decision.route)

        search_result = None
        source_guidance = None
        if decision.needs_search or should_try_allowed_sources(
            text, decision.category.value
        ):
            search_result = await self._do_search(text, decision, raw_public_knowledge)
            source_guidance = build_source_guidance(raw_public_knowledge, text)

        if decision.needs_ai:
            return await self._ai_resolve(
                user_id,
                text,
                decision,
                safe_knowledge,
                local_data,
                search_result,
                source_guidance,
            )

        # No AI needed
        if search_result:
            return search_result
        if source_guidance:
            return source_guidance
        if safe_knowledge:
            return safe_knowledge
        if local_data:
            return local_data
        return "Ð˜Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸Ñ Ð½ÐµÐ´Ð¾ÑÑ‚ÑƒÐ¿Ð½Ð°."

    async def _ai_resolve(
        self,
        user_id: int,
        text: str,
        decision: RouteDecision,
        knowledge: str,
        local_data: str | None,
        search_result: str | None,
        source_guidance: str | None,
    ) -> str:
        context_parts: list[str] = []

        if knowledge:
            context_parts.append(format_knowledge_for_prompt(knowledge))
        elif local_data:
            context_parts.append(format_knowledge_for_prompt(local_data))

        if search_result:
            context_parts.append(f"Ð Ð•Ð—Ð£Ð›Ð¬Ð¢ÐÐ¢Ð« ÐŸÐžÐ˜Ð¡ÐšÐ:\n{search_result}")

        if source_guidance:
            context_parts.append(f"PUBLIC SOURCE MAP:\n{source_guidance}")

        if decision.category.value == "technical_question":
            tech_link = find_tech_connection(text)
            if tech_link:
                context_parts.append(f"TECH SOURCE: {tech_link}")

        context = "\n\n".join(context_parts)

        # Detect language for prompt hint
        language = _detect_language(text)
        lang_hint = ""
        if language == "en":
            lang_hint = "\n\nThe user writes in English. Reply in English."
        elif language == "uk":
            lang_hint = "\n\nÐšÐ¾Ñ€Ð¸ÑÑ‚ÑƒÐ²Ð°Ñ‡ Ð¿Ð¸ÑˆÐµ ÑƒÐºÑ€Ð°Ñ—Ð½ÑÑŒÐºÐ¾ÑŽ. Ð’Ñ–Ð´Ð¿Ð¾Ð²Ñ–Ð´Ð°Ð¹ ÑƒÐºÑ€Ð°Ñ—Ð½ÑÑŒÐºÐ¾ÑŽ."

        prompt = build_visitor_system_prompt(context)
        if lang_hint:
            prompt += lang_hint
        supportive_guidance = _build_supportive_visitor_guidance(text, decision)
        if supportive_guidance:
            prompt += "\n\n" + supportive_guidance
        if search_result or source_guidance:
            prompt += (
                "\n\nPublic-source rules:\n"
                "- Use exact facts from the provided public sources when available.\n"
                "- If the provided sources do not explicitly answer the question, do not guess.\n"
                "- In that case, say that the exact answer is not stated publicly and point the user to the most relevant public source."
            )

        # Add end-suggestion instruction after multiple messages
        ctx = await self._sessions.get_or_create(user_id)
        if ctx.message_count > 3:
            prompt += (
                "\n\nÐ•ÑÐ»Ð¸ Ñ‚ÐµÐ¼Ð° ÐºÐ°Ð¶ÐµÑ‚ÑÑ Ð¸ÑÑ‡ÐµÑ€Ð¿Ð°Ð½Ð½Ð¾Ð¹, Ð´Ð¾Ð±Ð°Ð²ÑŒ Ð² ÐºÐ¾Ð½Ñ†Ðµ: "
                "[END_SUGGESTION]"
            )

        user_message = f"{decision.prefix}\n\nÐ’Ð¾Ð¿Ñ€Ð¾Ñ: {text}" if decision.prefix else text

        self._stats.total_ai_calls += 1
        history = await self._sessions.get_history(user_id)
        messages = [{"role": "system", "content": prompt}]
        for item in history:
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", "")).strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})

        try:
            result = await self._groq.generate_visitor_completion(
                messages=messages,
                model=getattr(self._config, 'visitor_primary_model', 'llama-3.3-70b-versatile'),
                max_tokens=getattr(self._config, 'visitor_max_output_tokens', 600),
                temperature=getattr(self._config, 'visitor_temperature', 0.5),
                user_query=text,
                expected_language=language,
            )
            if result:
                return result if result else _FALLBACK_OWNER
        except Exception as exc:
            self._stats.total_errors += 1
            LOGGER.warning("visitor_ai_error user=%s error=%s", user_id, exc)

        if source_guidance:
            return source_guidance

        # AI failed â€” never return raw knowledge to visitor
        if local_data:
            return local_data
        return _build_visitor_ai_failure_response(text, decision)

    # ========================
    # SEARCH
    # ========================

    async def _do_search(
        self, text: str, decision: RouteDecision, raw_knowledge: str | None = None
    ) -> str | None:
        lowered = text.casefold()
        knowledge_text = raw_knowledge or await self._knowledge.get_raw_public_knowledge()

        def join_sections(parts: list[str]) -> str | None:
            combined = "\n\n".join(part for part in parts if part).strip()
            return combined or None

        parts: list[str] = []
        wants_projects = (
            decision.category.value in {"about_projects", "project_specific_question"}
            or query_mentions_projects(text)
        )
        wants_github = (
            decision.category.value in {"about_projects", "project_specific_question", "links"}
            or query_mentions_code(text)
        )
        wants_channel = query_mentions_channel(text)
        wants_source_map = (
            decision.category.value == "links" or query_mentions_source_request(text)
        )
        wants_portfolio = wants_projects or query_mentions_portfolio_hint(text)

        if wants_portfolio:
            self._stats.total_searches += 1
            portfolio = await search_portfolio(
                self._config,
                knowledge_text,
                text if wants_projects else "portfolio projects",
                limit=4 if wants_projects else 2,
            )
            if portfolio:
                parts.append(f"Portfolio:\n{portfolio}")

        if wants_github:
            github_query = clean_search_query(text)
            if not query_mentions_code(text) and not wants_projects:
                github_query = ""
            if len(github_query.split()) > 4:
                github_query = ""
            self._stats.total_github_searches += 1
            github = await search_github(
                "example",
                github_query,
                limit=4 if wants_projects else 5,
            )
            if github:
                parts.append(f"GitHub:\n{github}")

        if wants_channel and self._public_channel_reader_fn is not None:
            try:
                channel_result = await self._public_channel_reader_fn(text, limit=3)
            except Exception as exc:
                LOGGER.warning("visitor_public_channel_lookup_error error=%s", exc)
                channel_result = None
            if channel_result:
                parts.append(f"Telegram channel:\n{channel_result}")

        if not parts and wants_portfolio:
            self._stats.total_searches += 1
            fallback_query = clean_search_query(text) or "ProjectOwner projects"
            web_result = await search_web(
                self._config,
                f"{fallback_query} site:example.com",
            )
            if web_result:
                parts.append(f"Website:\n{web_result}")

        if not parts and decision.route == Route.SEARCH_GITHUB:
            _github_kw = (
                "github", "Â¥?DÃ¦DÂ¨D_DÃºD,Â¥,D_Â¥?D,", "repo", "DÂ§D_D'", "DÂ¨D_DÂ§DÃ¸DD,",
                "DÂ«DÃ¸D1D'D,", "DÂ¨Â¥?D_DÃ¦DÂ§Â¥,", "D3D'DÃ¦ DÂ¨D_Â¥?DÂ¬D_Â¥,Â¥?DÃ¦Â¥,Â¥O", "where", "find",
            )
            if any(kw in lowered for kw in _github_kw):
                self._stats.total_github_searches += 1
                query = clean_search_query(text)
                result = await search_github("example", query)
                if result:
                    parts.append(result)

        if parts:
            return join_sections(parts)

        if wants_source_map:
            return build_source_guidance(knowledge_text, text)

        return None

        if decision.category.value == "links":
            parts: list[str] = []
            knowledge_text = await get_raw_knowledge()

            self._stats.total_searches += 1
            portfolio = await search_portfolio(
                self._config,
                knowledge_text,
                "portfolio projects contacts",
                limit=2,
            )
            if portfolio:
                parts.append(f"Portfolio:\n{portfolio}")

            self._stats.total_github_searches += 1
            github = await search_github("example", "", limit=5)
            if github:
                parts.append(f"GitHub:\n{github}")

            return join_sections(parts)

        if decision.category.value in {"about_projects", "project_specific_question"}:
            parts: list[str] = []
            knowledge_text = await get_raw_knowledge()

            self._stats.total_searches += 1
            portfolio = await search_portfolio(
                self._config,
                knowledge_text,
                text,
                limit=4,
            )
            if portfolio:
                parts.append(f"Portfolio:\n{portfolio}")

            github_query = clean_search_query(text)
            if len(github_query.split()) > 4:
                github_query = ""

            self._stats.total_github_searches += 1
            github = await search_github("example", github_query, limit=4)
            if github:
                parts.append(f"GitHub:\n{github}")

            if not portfolio:
                self._stats.total_searches += 1
                fallback_query = clean_search_query(text) or "ProjectOwner projects"
                web_result = await search_web(
                    self._config,
                    f"{fallback_query} site:example.com",
                )
                if web_result:
                    parts.insert(0, f"Website:\n{web_result}")

            return join_sections(parts)

        if decision.route == Route.SEARCH_GITHUB:
            _github_kw = (
                "github", "Ñ€ÐµÐ¿Ð¾Ð·Ð¸Ñ‚Ð¾Ñ€Ð¸", "repo", "ÐºÐ¾Ð´", "Ð¿Ð¾ÐºÐ°Ð¶Ð¸",
                "Ð½Ð°Ð¹Ð´Ð¸", "Ð¿Ñ€Ð¾ÐµÐºÑ‚", "Ð³Ð´Ðµ Ð¿Ð¾ÑÐ¼Ð¾Ñ‚Ñ€ÐµÑ‚ÑŒ", "where", "find",
            )
            if any(kw in lowered for kw in _github_kw):
                self._stats.total_github_searches += 1
                query = clean_search_query(text)
                result = await search_github("example", query)
                if result:
                    return result

            if any(kw in lowered for kw in ("ÑÐ°Ð¹Ñ‚", "Ð¿Ð¾Ñ€Ñ‚Ñ„Ð¾Ð»Ð¸Ð¾", "site", "portfolio")):
                self._stats.total_searches += 1
                knowledge_text = await get_raw_knowledge()
                portfolio = await search_portfolio(self._config, knowledge_text, text, limit=3)
                if portfolio:
                    return f"Portfolio:\n{portfolio}"
                return await search_web(self._config, "ProjectOwner site:example.com")

        return None

    # ========================
    # LOCAL DATA
    # ========================

    def _get_local_data(self, route: Route) -> str | None:
        fallbacks = {
            Route.STATIC_OWNER: _FALLBACK_OWNER,
            Route.STATIC_LINKS: _FALLBACK_LINKS,
            Route.STATIC_PROJECTS: _FALLBACK_PROJECTS,
            Route.STATIC_CAPABILITIES: _FALLBACK_CAPABILITIES,
            Route.STATIC_FAQ: _FALLBACK_FAQ,
            Route.STATIC_COLLABORATION: _FALLBACK_COLLABORATION,
        }
        return fallbacks.get(route)

    # ========================
    # ADMIN HELPERS
    # ========================

    async def block_user(self, user_id: int) -> None:
        await self.reset_user_state(user_id)
        await self._sessions.block_user(user_id)

    async def unblock_user(self, user_id: int) -> None:
        await self._sessions.unblock_user(user_id)

    async def cleanup_inactive_sessions(self) -> int:
        return await self._sessions.cleanup_inactive()


