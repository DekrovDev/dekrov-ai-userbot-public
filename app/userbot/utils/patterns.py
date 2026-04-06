"""Константы и regex-паттерны для userbot.

Используется для идентификации команд, вопросов, и специальных паттернов.
"""

from __future__ import annotations

import re

# ─────────────────────────────────────────────────────────────────────────────
# IDENTITY QUESTIONS
# ─────────────────────────────────────────────────────────────────────────────

SELF_NAME_QUESTION_RE = re.compile(
    r"(?iu)\b(?:кто\s+я|я\s+кто|как\s+меня\s+зовут|меня\s+как\s+зовут|хто\s+я|як\s+мене\s+звати|what\s+is\s+my\s+name|who\s+am\s+i|do\s+you\s+know\s+my\s+name|come\s+mi\s+chiamo|chi\s+sono|como\s+me\s+llamo|quien\s+soy|comment\s+je\s+m'appelle|qui\s+suis[- ]?je|wie\s+hei(?:ss|ß)e\s+ich|wer\s+bin\s+ich)\b"
)
"""Вопросы о имени пользователя."""

SELF_IDENTITY_STATEMENT_RE = re.compile(
    r"(?iu)^\s*(?:я|i am|i'm|im|sono|soy|je suis)\s+([^\n,.!?]{1,40})\s*$"
)
"""Утверждения о личности (я ...)."""

IDENTITY_AMBIGUITY_RE = re.compile(
    r"(?iu)\b(?:может\s+быть\s+друг|я\s+другой|другим\s+[а-яa-z]+|another\s+[a-z]+|could\s+be\s+another|same\s+name|одно\s+имя|same person)\b"
)
"""Паттерны неоднозначности личности."""

CHAT_TITLE_QUESTION_RE = re.compile(
    r"(?iu)\b(?:как\s+называется\s+этот\s+чат|название\s+чата|имя\s+чата|название\s+группы|як\s+називається\s+цей\s+чат|назва\s+чату|назва\s+групи|what\s+is\s+this\s+chat\s+called|what\s+is\s+the\s+name\s+of\s+this\s+chat|chat\s+name|group\s+name|come\s+si\s+chiama\s+questa\s+chat|como\s+se\s+llama\s+este\s+chat|comment\s+s'appelle\s+ce\s+chat|wie\s+heisst\s+dieser\s+chat)\b"
)
"""Вопросы о названии чата."""

CHAT_MEMBER_COUNT_QUESTION_RE = re.compile(
    r"(?iu)\b(?:сколько\s+пользователей\s+в(?:\s+этом)?\s+чате|сколько\s+людей\s+в(?:\s+этом)?\s+чате|количество\s+участников|скільки\s+учасників|скільки\s+людей|how\s+many\s+users\s+are\s+in(?:\s+this)?\s+chat|how\s+many\s+members\s+are\s+in(?:\s+this)?\s+chat|member\s+count|participant\s+count)\b"
)
"""Вопросы о количестве участников чата."""

# ─────────────────────────────────────────────────────────────────────────────
# WEB SEARCH
# ─────────────────────────────────────────────────────────────────────────────

OWNER_WEB_SEARCH_MARKERS = (
    "найди в интернете",
    "поищи в интернете",
    "найди в гугле",
    "поищи в гугле",
    "загугли",
    "найди онлайн",
    "search the web",
    "search online",
    "search the internet",
    "look it up online",
    "find on the internet",
    "find online",
)
"""Маркеры запроса веб-поиска."""

OWNER_WEB_SEARCH_FOLLOWUPS = {
    "ищи",
    "поищи",
    "гугли",
    "загугли",
    "search",
    "search it",
    "look it up",
    "keep searching",
}
"""Слова продолжения поиска."""

# ─────────────────────────────────────────────────────────────────────────────
# BUSINESS-LIKE MARKERS
# ─────────────────────────────────────────────────────────────────────────────

BUSINESS_LIKE_MARKERS = (
    "что такое",
    "что значит",
    "что подразумевает",
    "что ты подразумеваешь",
    "как работает",
    "как делать",
    "как настроить",
    "как решить",
    "как исправить",
    "в чем разница",
    "объясни",
    "расскажи",
    "подскажи",
    "помоги",
    "помощь нужна",
    "нужна помощь",
    "по делу",
    "расшифруй",
    "дешифруй",
    "decode",
    "decrypt",
    "decryption",
    "decipher",
    "explain",
    "tell me",
    "help me",
    "can you help",
    "could you explain",
    "what do you mean",
    "how does it work",
    "define",
    "clarify",
    "bug",
    "error",
    "issue",
    "config",
    "setup",
    "api",
    "code",
)
"""Маркеры делового/технического запроса."""

# ─────────────────────────────────────────────────────────────────────────────
# USER IDENTIFICATION
# ─────────────────────────────────────────────────────────────────────────────

USERNAME_MENTION_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{3,32})")
"""Извлечение @username из текста."""

USER_ID_RE = re.compile(
    r"(?iu)\b(?:id|user_id|uid|айди|ид)\s*[:=]?\s*(-?\d{5,})\b"
)
"""Извлечение user_id из текста."""

# ─────────────────────────────────────────────────────────────────────────────
# PRIVACY PROTECTION
# ─────────────────────────────────────────────────────────────────────────────

OWNER_PRIVACY_KEYWORDS = (
    "личные данные",
    "персональные данные",
    "паспорт",
    "документ",
    "номер",
    "телефон",
    "почта",
    "email",
    "mail",
    "адрес",
    "где жив",
    "пароль",
    "код",
    "логин",
    "session",
    "сессия",
    "api key",
    "api_key",
    "token",
    "токен",
    "файл",
    "files",
    "других чат",
    "другом чате",
    "другие чаты",
    "other chat",
    "other chats",
    "saved messages",
    "избранн",
    "канал",
    "channel",
    "переписк",
    "messages from",
    "сообщение из",
)
"""Ключевые слова приватных данных."""

OWNER_PRIVACY_PATTERNS = (
    re.compile(
        r"(?iu)\b(?:что|какие|какой|где|дай|покажи|скажи)\b.*\b(?:телефон|номер|почта|email|адрес|пароль|код|token|токен)\b"
    ),
    re.compile(
        r"(?iu)\b(?:what|show|tell|give)\b.*\b(?:phone|number|email|address|password|token|session|files?)\b"
    ),
    re.compile(
        r"(?iu)\b(?:что|какие|покажи|скинь|перешли|дай)\b.*\b(?:в других чатах|из других чатов|в избранном|из избранного|в канале|из канала)\b"
    ),
    re.compile(
        r"(?iu)\b(?:show|send|forward|tell)\b.*\b(?:other chats|saved messages|channel|messages from)\b"
    ),
)
"""Паттерны запросов приватных данных."""

# ─────────────────────────────────────────────────────────────────────────────
# AUTO-REPLY DEFAULTS
# ─────────────────────────────────────────────────────────────────────────────

LEGACY_REPLY_PROBABILITY = 0.35
LEGACY_REPLY_COOLDOWN_SECONDS = 900
LEGACY_REPLY_MIN_DELAY_SECONDS = 25
LEGACY_REPLY_MAX_DELAY_SECONDS = 90
LEGACY_REPLY_HOURLY_LIMIT = 4
LEGACY_REPLY_MIN_MESSAGE_LENGTH = 8
"""Настройки автоответов по умолчанию."""
