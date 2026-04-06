"""ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚Ñ‡Ð¸Ðº ÐºÐ¾Ð¼Ð°Ð½Ð´ Ð²ÐµÐ±-Ð¿Ð¾Ð¸ÑÐºÐ° Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ð°.

ÐšÐ¾Ð¼Ð°Ð½Ð´Ñ‹: .Ð± Ð½Ð°Ð¹Ð´Ð¸ Ð² Ð¸Ð½Ñ‚ÐµÑ€Ð½ÐµÑ‚Ðµ ..., .search, .find
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from infra.language_tools import detect_language

from ..utils.patterns import OWNER_WEB_SEARCH_MARKERS, OWNER_WEB_SEARCH_FOLLOWUPS

if TYPE_CHECKING:
    from live.live_router import LiveDataRouter


# ÐŸÐ¾Ð¸ÑÐºÐ¾Ð²Ñ‹Ðµ Ð³Ð»Ð°Ð³Ð¾Ð»Ñ‹
SEARCH_VERBS = {
    "Ð½Ð°Ð¹Ð´Ð¸",
    "Ð¿Ð¾Ð¸Ñ‰Ð¸",
    "Ð¸Ñ‰Ð¸",
    "Ð·Ð°Ð³ÑƒÐ³Ð»Ð¸",
    "search",
    "find",
    "look up",
}

# Ð’ÐµÐ±-ÑÐºÐ¾ÑƒÐ¿ (Ð¾Ð±Ð»Ð°ÑÑ‚ÑŒ Ð¿Ð¾Ð¸ÑÐºÐ°)
WEB_SCOPE = {
    "Ð³ÑƒÐ³Ð»",
    "Ð¸Ð½Ñ‚ÐµÑ€Ð½ÐµÑ‚",
    "Ð¾Ð½Ð»Ð°Ð¹Ð½",
    "google",
    "internet",
    "web",
    "online",
    "social",
}

# ÐŸÐ°Ñ‚Ñ‚ÐµÑ€Ð½Ñ‹ Ð´Ð»Ñ Ð¾Ñ‡Ð¸ÑÑ‚ÐºÐ¸ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ° Ð¾Ñ‚ Ð¿Ñ€ÐµÑ„Ð¸ÐºÑÐ¾Ð²
SEARCH_PREFIX_PATTERNS = (
    r"(?iu)^(?:Ð½Ð°Ð¹Ð´Ð¸|Ð¿Ð¾Ð¸Ñ‰Ð¸|Ð·Ð°Ð³ÑƒÐ³Ð»Ð¸)\s+(?:Ð²\s+Ð¸Ð½Ñ‚ÐµÑ€Ð½ÐµÑ‚Ðµ|Ð²\s+Ð³ÑƒÐ³Ð»Ðµ|Ð¾Ð½Ð»Ð°Ð¹Ð½)\s+",
    r"(?iu)^(?:search|find|look up)\s+(?:on(?:\s+the)?\s+internet|online|on\s+the\s+web)\s+",
)

RAW_SEARCH_COMMAND_PATTERNS = (
    r"(?iu)^(?:\.search|/search|\.find|/find)\s+",
)


class WebSearchHandler:
    """ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚Ñ‡Ð¸Ðº ÐºÐ¾Ð¼Ð°Ð½Ð´ Ð²ÐµÐ±-Ð¿Ð¾Ð¸ÑÐºÐ°."""

    def __init__(self, live_router: LiveDataRouter) -> None:
        self._live_router = live_router
        self._recent_queries: dict[int, str] = {}

    async def handle_owner_web_search_command(
        self, chat_id: int, prompt: str, *, response_style_mode: str
    ) -> str | None:
        """ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚Ð°Ñ‚ÑŒ ÐºÐ¾Ð¼Ð°Ð½Ð´Ñƒ Ð²ÐµÐ±-Ð¿Ð¾Ð¸ÑÐºÐ° Ð¾Ñ‚ Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ð°.

        Args:
            chat_id: ID Ñ‡Ð°Ñ‚Ð°
            prompt: Ð¢ÐµÐºÑÑ‚ ÐºÐ¾Ð¼Ð°Ð½Ð´Ñ‹
            response_style_mode: Ð ÐµÐ¶Ð¸Ð¼ ÑÑ‚Ð¸Ð»Ñ Ð¾Ñ‚Ð²ÐµÑ‚Ð°

        Returns:
            Ð ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚ Ð¿Ð¾Ð¸ÑÐºÐ° Ð¸Ð»Ð¸ None
        """
        normalized = " ".join((prompt or "").strip().split())
        if not normalized:
            return None
        lowered = normalized.casefold().lstrip("\\/ ").strip()

        if _looks_like_owner_raw_web_search_command(normalized):
            query = _extract_owner_web_search_query(normalized)
            if not query:
                query = normalized.lstrip("\\/ ").strip()
            self._recent_queries[chat_id] = query
        else:
            query = _resolve_owner_web_search_followup(
                chat_id, lowered, self._recent_queries
            )
            if not query:
                return None

        return await self._live_router.search_web_query(
            query, response_style_mode=response_style_mode
        )

    def get_recent_query(self, chat_id: int) -> str | None:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ð¹ Ð¿Ð¾Ð¸ÑÐºÐ¾Ð²Ñ‹Ð¹ Ð·Ð°Ð¿Ñ€Ð¾Ñ Ð´Ð»Ñ Ñ‡Ð°Ñ‚Ð°."""
        return self._recent_queries.get(chat_id)

    def clear_recent_query(self, chat_id: int) -> None:
        """ÐžÑ‡Ð¸ÑÑ‚Ð¸Ñ‚ÑŒ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ð¹ Ð¿Ð¾Ð¸ÑÐºÐ¾Ð²Ñ‹Ð¹ Ð·Ð°Ð¿Ñ€Ð¾Ñ Ð´Ð»Ñ Ñ‡Ð°Ñ‚Ð°."""
        self._recent_queries.pop(chat_id, None)


def _extract_owner_web_search_query(prompt: str) -> str:
    """Ð˜Ð·Ð²Ð»ÐµÑ‡ÑŒ Ð·Ð°Ð¿Ñ€Ð¾Ñ Ð½Ð° Ð¿Ð¾Ð¸ÑÐº Ð¸Ð· ÐºÐ¾Ð¼Ð°Ð½Ð´Ñ‹.

    Args:
        prompt: Ð¢ÐµÐºÑÑ‚ ÐºÐ¾Ð¼Ð°Ð½Ð´Ñ‹

    Returns:
        ÐžÑ‡Ð¸Ñ‰ÐµÐ½Ð½Ñ‹Ð¹ Ð·Ð°Ð¿Ñ€Ð¾Ñ
    """
    cleaned = " ".join((prompt or "").strip().split()).lstrip("\\\\/ ").strip()
    for pattern in SEARCH_PREFIX_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned).strip()
    return cleaned


def _looks_like_owner_web_search_request(lowered: str) -> bool:
    """ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ, Ð¿Ð¾Ñ…Ð¾Ð¶Ðµ Ð»Ð¸ Ð½Ð° Ð·Ð°Ð¿Ñ€Ð¾Ñ Ð²ÐµÐ±-Ð¿Ð¾Ð¸ÑÐºÐ°.

    Args:
        lowered: Ð¢ÐµÐºÑÑ‚ Ð² Ð½Ð¸Ð¶Ð½ÐµÐ¼ Ñ€ÐµÐ³Ð¸ÑÑ‚Ñ€Ðµ

    Returns:
        True ÐµÑÐ»Ð¸ Ð¿Ð¾Ñ…Ð¾Ð¶Ðµ Ð½Ð° Ð·Ð°Ð¿Ñ€Ð¾Ñ Ð¿Ð¾Ð¸ÑÐºÐ°
    """
    if not lowered:
        return False
    if any(marker in lowered for marker in OWNER_WEB_SEARCH_MARKERS):
        return True

    has_search_verb = any(token in lowered for token in SEARCH_VERBS)
    has_web_scope = any(token in lowered for token in WEB_SCOPE)

    return has_search_verb and has_web_scope


def _looks_like_owner_raw_web_search_command(prompt: str) -> bool:
    normalized = " ".join((prompt or "").strip().split())
    if not normalized:
        return False
    return any(re.search(pattern, normalized) for pattern in RAW_SEARCH_COMMAND_PATTERNS)


def _resolve_owner_web_search_followup(
    chat_id: int, lowered: str, recent_queries: dict[int, str]
) -> str | None:
    """Ð Ð°Ð·Ñ€ÐµÑˆÐ¸Ñ‚ÑŒ Ð·Ð°Ð¿Ñ€Ð¾Ñ Ð¿Ñ€Ð¾Ð´Ð¾Ð»Ð¶ÐµÐ½Ð¸Ñ Ð¿Ð¾Ð¸ÑÐºÐ°.

    Args:
        chat_id: ID Ñ‡Ð°Ñ‚Ð°
        lowered: Ð¢ÐµÐºÑÑ‚ Ð² Ð½Ð¸Ð¶Ð½ÐµÐ¼ Ñ€ÐµÐ³Ð¸ÑÑ‚Ñ€Ðµ
        recent_queries: ÐŸÐ¾ÑÐ»ÐµÐ´Ð½Ð¸Ðµ Ð¿Ð¾Ð¸ÑÐºÐ¾Ð²Ñ‹Ðµ Ð·Ð°Ð¿Ñ€Ð¾ÑÑ‹

    Returns:
        Ð—Ð°Ð¿Ñ€Ð¾Ñ Ð´Ð»Ñ Ð¿Ð¾Ð¸ÑÐºÐ° Ð¸Ð»Ð¸ None
    """
    normalized = " ".join((lowered or "").split()).strip(" .,!?:;")
    if normalized not in OWNER_WEB_SEARCH_FOLLOWUPS:
        return None
    return recent_queries.get(chat_id)


def build_non_owner_web_search_refusal(prompt: str) -> str | None:
    """ÐŸÐ¾ÑÑ‚Ñ€Ð¾Ð¸Ñ‚ÑŒ Ð¾Ñ‚ÐºÐ°Ð· Ð´Ð»Ñ Ð½Ðµ-Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ð° Ð½Ð° Ð·Ð°Ð¿Ñ€Ð¾Ñ Ð¿Ð¾Ð¸ÑÐºÐ°.

    Args:
        prompt: Ð¢ÐµÐºÑÑ‚ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ°

    Returns:
        Ð¢ÐµÐºÑÑ‚ Ð¾Ñ‚ÐºÐ°Ð·Ð° Ð¸Ð»Ð¸ None
    """
    normalized = " ".join((prompt or "").strip().split())
    if not normalized:
        return None
    lowered = normalized.casefold().lstrip("\\/ ").strip()

    if not _looks_like_owner_web_search_request(lowered):
        return None

    language = detect_language(normalized)

    refusals = {
        "en": "I do not perform internet or Google-style searches at the request of other users. Only ProjectOwner can ask me to search the web.",
        "it": "Non eseguo ricerche su internet o in stile Google su richiesta di altri utenti. Solo ProjectOwner puo chiedermelo.",
        "es": "No hago busquedas en internet o tipo Google por peticion de otros usuarios. Solo ProjectOwner puede pedirmelo.",
        "fr": "Je n'effectue pas de recherches sur internet ou de type Google a la demande d'autres utilisateurs. Seul ProjectOwner peut me le demander.",
        "de": "Ich fuehre keine Internet- oder Google-aehnlichen Suchen auf Wunsch anderer Nutzer aus. Nur ProjectOwner kann mich darum bitten.",
    }

    return refusals.get(language, "Ð¯ Ð½Ðµ Ð²Ñ‹Ð¿Ð¾Ð»Ð½ÑÑŽ Ð¸Ð½Ñ‚ÐµÑ€Ð½ÐµÑ‚-Ð¿Ð¾Ð¸ÑÐº Ð¸Ð»Ð¸ Google-Ð¿Ð¾Ð¸ÑÐº Ð¿Ð¾ Ð¿Ñ€Ð¾ÑÑŒÐ±Ðµ Ð´Ñ€ÑƒÐ³Ð¸Ñ… Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÐµÐ¹. Ð¢Ð¾Ð»ÑŒÐºÐ¾ ProjectOwner Ð¼Ð¾Ð¶ÐµÑ‚ Ð¿Ð¾Ð¿Ñ€Ð¾ÑÐ¸Ñ‚ÑŒ Ð¼ÐµÐ½Ñ Ð¸ÑÐºÐ°Ñ‚ÑŒ Ð² Ð¸Ð½Ñ‚ÐµÑ€Ð½ÐµÑ‚Ðµ.")

