"""Анализ топиков и контекста чата.

Суммаризация контекста, определение тона и темы разговора.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyrogram import Chat
    from chat.context_reader import ContextLine
    from memory.style_profile import StyleProfileStore


# Импортируем regex из style_profile
def _get_style_regexes():
    """Лениво импортировать regex из style_profile."""
    from memory.style_profile import FORMAL_RE, HUMOR_RE, PROFANITY_RE, SLANG_RE
    return FORMAL_RE, HUMOR_RE, PROFANITY_RE, SLANG_RE


# Слова для исключения из анализа тем
STOPWORDS = {
    "chat",
    "message",
    "messages",
    "что",
    "как",
    "what",
    "this",
    "that",
    "это",
    "как",
    "ты",
    "ты",
    "you",
    "i",
    "we",
    "the",
    "and",
    "is",
    "are",
}


def summarize_chat_context(
    chat: Chat,
    context_lines: list,
    newest_text: str = "",
    style_context_analysis_enabled: bool = True,
) -> str:
    """Суммаризировать контекст чата для промпта.

    Args:
        chat: Объект чата
        context_lines: Линии контекста
        newest_text: Новейший текст сообщения
        style_context_analysis_enabled: Флаг включения анализа

    Returns:
        Строка с описанием контекста чата
    """
    from pyrogram import enums

    if not style_context_analysis_enabled:
        return ""

    FORMAL_RE, HUMOR_RE, PROFANITY_RE, SLANG_RE = _get_style_regexes()

    texts = [
        getattr(line, "text", "")
        for line in context_lines
        if getattr(line, "text", "")
    ]
    if newest_text:
        texts.append(newest_text)

    combined = " ".join(texts).strip()
    normalized = combined.casefold()

    avg_words = 0.0
    if texts:
        avg_words = sum(len((text or "").split()) for text in texts) / max(
            len(texts), 1
        )

    casual_score = len(HUMOR_RE.findall(normalized)) + len(
        SLANG_RE.findall(normalized)
    )
    formal_score = len(FORMAL_RE.findall(normalized))

    emotional_tone = "neutral"
    if combined.count("!") >= 3 or len(PROFANITY_RE.findall(normalized)) >= 2:
        emotional_tone = "heated"
    elif len(HUMOR_RE.findall(normalized)) >= 2:
        emotional_tone = "playful"

    chat_tone = "casual"
    if formal_score > casual_score + 1:
        chat_tone = "formal"
    elif casual_score >= formal_score + 1:
        chat_tone = (
            "playful" if len(HUMOR_RE.findall(normalized)) >= 2 else "casual"
        )

    short_replies = "yes" if avg_words <= 9 or len(texts) <= 4 else "no"
    current_topic = infer_context_topic(texts) or "mixed"
    chat_kind = (
        "private"
        if getattr(chat, "type", None) == enums.ChatType.PRIVATE
        else "group"
    )

    return (
        f"chat_type={chat_kind}; tone={chat_tone}; emotional_tone={emotional_tone}; "
        f"current_topic={current_topic}; short_replies={short_replies}"
    )


def infer_context_topic(texts: list[str]) -> str | None:
    """Определить тему контекста по частоте слов.

    Args:
        texts: Список текстов для анализа

    Returns:
        Наиболее частое слово или None
    """
    counts: dict[str, int] = {}
    word_pattern = re.compile(
        r"[A-Za-zА-Яа-яЁёІіЇїЄєҐґ0-9_-]{2,}",
        re.UNICODE
    )

    for text in texts:
        for word in word_pattern.findall(text or ""):
            normalized = word.casefold()
            if normalized in STOPWORDS:
                continue
            counts[normalized] = counts.get(normalized, 0) + 1

    if not counts:
        return None
    return max(counts.items(), key=lambda item: item[1])[0]
