from __future__ import annotations

import re
from dataclasses import dataclass

from config.identity import enforce_identity_answer, is_identity_question
from infra.language_tools import detect_language, is_text_in_language, normalize_language


AI_PREFIX = "AI:"

REASONING_BLOCK_RE = re.compile(r"<(think|analysis)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
OPEN_REASONING_BLOCK_RE = re.compile(r"<(?:think|analysis)\b[^>]*>.*$", re.IGNORECASE | re.DOTALL)
SELF_CLOSING_REASONING_TAG_RE = re.compile(r"<(?:think|analysis)\b[^>]*/\s*>", re.IGNORECASE)
LEFTOVER_REASONING_TAG_RE = re.compile(r"</?(?:think|analysis)\b[^>]*>", re.IGNORECASE)
REASONING_PREFIX_LINE_RE = re.compile(
    r"(?im)^\s*(?:thinking|reasoning|analysis|internal thoughts?|internal reasoning|thought process)\s*:.*$"
)
REASONING_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")
QUESTION_LINE_RE = re.compile(r"(?im)^\s*(?:question|Ð²Ð¾Ð¿Ñ€Ð¾Ñ)\s*:\s*(.+)$")
ANSWER_LINE_RE = re.compile(r"(?im)^\s*(?:answer|Ð¾Ñ‚Ð²ÐµÑ‚)\s*:\s*(.+)$")
AI_LINE_RE = re.compile(r"(?im)^\s*ai\s*:\s*(.+)$")
INLINE_LEGACY_PREFIX_RE = re.compile(
    r"(?i)(?:(?<=^)|(?<=[\s(\[{])|(?<=[.!?]\s))(?:ai|answer|response|final answer|final|q|a|assistant-ai)\s*:\s*"
)
LEGACY_PREFIX_RE = re.compile(
    r"(?im)^\s*(?:ai|answer|response|final answer|final|q|a|assistant-ai)\s*:\s*"
)
TRIGGER_PREFIX_RE = re.compile(r"^\s*\.(?:assistant|Ð´ÐµÐºÑ€Ð¾Ð²|d|Ð´)\b[\s:,-]*", re.IGNORECASE)
WORD_RE = re.compile(r"[A-Za-z\u0400-\u04FF][A-Za-z\u0400-\u04FF0-9'-]{1,}")
NON_TOPIC_RE = re.compile(r"[^A-Za-z\u0400-\u04FF0-9\s'-]+")
HTMLISH_TAG_RE = re.compile(r"</?[A-Za-z][^>]{0,80}>")
BROKEN_ENDING_RE = re.compile(r"[,:;(\[/\-]$")
UNFINISHED_WORD_RE = re.compile(r"[A-Za-z\u0400-\u04FF]{1,3}$")
CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
LATIN_RE = re.compile(r"[A-Za-z]")

REASONING_PREAMBLE_MARKERS = (
    "the user",
    "user greeted",
    "user asked",
    "user wants",
    "question",
    "answer should",
    "answer must",
    "final answer",
    "reply should",
    "reply must",
    "i need to",
    "i should",
    "i will",
    "let me",
    "need to",
    "must be",
    "should be",
    "check the data",
    "check the instructions",
    "follow the instructions",
    "formatting",
    "telegram html",
    "1-2 sentences",
    "1-2 sentence",
    "briefly answer",
    "\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b",
    "\u0432\u043e\u043f\u0440\u043e\u0441",
    "\u043e\u0442\u0432\u0435\u0442",
    "\u0438\u0442\u043e\u0433\u043e\u0432\u044b\u0439 \u043e\u0442\u0432\u0435\u0442",
    "\u043d\u0443\u0436\u043d\u043e",
    "\u043d\u0430\u0434\u043e",
    "\u0441\u043d\u0430\u0447\u0430\u043b\u0430",
    "\u043f\u0440\u043e\u0432\u0435\u0440\u044e",
    "\u043f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c",
    "\u0443\u0431\u0435\u0434\u0438\u0442\u044c\u0441\u044f",
    "\u0441\u043b\u0435\u0434\u0443\u044f \u0438\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u044f\u043c",
    "\u0444\u043e\u0440\u043c\u0430\u0442\u0438\u0440\u043e\u0432",
    "\u0432 \u043a\u043e\u043d\u0446\u0435 \u0434\u043e\u0431\u0430\u0432",
    "\u043a\u0440\u0430\u0442\u043a\u043e",
)
REASONING_PREAMBLE_STRONG_MARKERS = (
    "user greeted",
    "user asked",
    "user wants",
    "final answer",
    "telegram html",
    "formatting",
    "follow the instructions",
    "check the data",
    "\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b",
    "\u0438\u0442\u043e\u0433\u043e\u0432\u044b\u0439 \u043e\u0442\u0432\u0435\u0442",
    "\u0441\u043b\u0435\u0434\u0443\u044f \u0438\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u044f\u043c",
    "\u0444\u043e\u0440\u043c\u0430\u0442\u0438\u0440\u043e\u0432",
    "\u0432 \u043a\u043e\u043d\u0446\u0435 \u0434\u043e\u0431\u0430\u0432",
)
REASONING_PREAMBLE_STARTERS = (
    "okay",
    "ok",
    "alright",
    "well",
    "good",
    "first",
    "let me",
    "i need to",
    "i should",
    "i will",
    "need to",
    "must",
    "should",
    "\u0445\u043e\u0440\u043e\u0448\u043e",
    "\u043b\u0430\u0434\u043d\u043e",
    "\u0441\u043d\u0430\u0447\u0430\u043b\u0430",
    "\u043d\u0443\u0436\u043d\u043e",
    "\u043d\u0430\u0434\u043e",
    "\u043f\u0440\u043e\u0432\u0435\u0440\u044e",
    "\u0438\u0442\u043e\u0433\u043e\u0432\u044b\u0439 \u043e\u0442\u0432\u0435\u0442",
)

MOJIBAKE_MARKERS = (
    "Ãƒ",
    "Ã‚",
    "Ã…",
    "Ã",
    "Ã‘",
    "Ã¢",
    "â‚¬",
    "â„¢",
    "Å“",
    "Å¾",
    "Â¤",
    "ï¿½",
)

USELESS_EXACT = {
    "",
    "i could not build a useful answer",
    "no useful answer",
    "error generating response",
    "something went wrong",
    "Ð½Ðµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¿Ð¾Ð´Ð¾Ð±Ñ€Ð°Ñ‚ÑŒ Ð½Ð¾Ñ€Ð¼Ð°Ð»ÑŒÐ½Ñ‹Ð¹ Ð¾Ñ‚Ð²ÐµÑ‚",
    "Ð½Ðµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¿Ð¾Ð´Ð¾Ð±Ñ€Ð°Ñ‚ÑŒ Ð½Ð¾Ñ€Ð¼Ð°Ð»ÑŒÐ½Ñ‹Ð¹ Ð¾Ñ‚Ð²ÐµÑ‚.",
}

USELESS_SUBSTRINGS = (
    "i could not build a useful answer",
    "no useful answer",
    "error generating response",
    "something went wrong",
    "couldn't answer",
    "could not answer",
    "Ð½Ðµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¿Ð¾Ð´Ð¾Ð±Ñ€Ð°Ñ‚ÑŒ",
    "Ð¾ÑˆÐ¸Ð±ÐºÐ° Ð³ÐµÐ½ÐµÑ€Ð°Ñ†Ð¸Ð¸ Ð¾Ñ‚Ð²ÐµÑ‚Ð°",
)

REFUSAL_SUBSTRINGS = (
    "i can't help",
    "i cannot help",
    "i can't assist",
    "i cannot assist",
    "Ñ Ð½Ðµ Ð¼Ð¾Ð³Ñƒ Ð¿Ð¾Ð¼Ð¾Ñ‡ÑŒ",
    "Ñ Ð½Ðµ Ð¼Ð¾Ð³Ñƒ Ñ ÑÑ‚Ð¸Ð¼ Ð¿Ð¾Ð¼Ð¾Ñ‡ÑŒ",
    "Ð½Ðµ Ð¼Ð¾Ð³Ñƒ Ð¿Ð¾Ð¼Ð¾Ñ‡ÑŒ",
    "non posso aiutare",
    "no puedo ayudar",
    "je ne peux pas aider",
    "ich kann nicht helfen",
)

UNCLEAR_SUBSTRINGS = (
    "don't understand",
    "do not understand",
    "not sure what you mean",
    "Ñ Ð½Ðµ Ð¿Ð¾Ð½ÑÐ»",
    "Ñ Ð½Ðµ Ð´Ð¾ ÐºÐ¾Ð½Ñ†Ð° Ð¿Ð¾Ð½ÑÐ»",
    "Ð½Ðµ Ð¿Ð¾Ð½ÑÐ»",
    "Ð½Ðµ Ð¿Ð¾Ð½Ð¸Ð¼Ð°ÑŽ, Ð¾ Ñ‡ÐµÐ¼",
    "Ð½ÐµÑÑÐ½Ð¾",
    "non capisco",
    "non ho capito",
    "no entiendo",
    "je ne comprends pas",
    "je n'ai pas compris",
    "ich verstehe nicht",
)

SUSPICIOUS_SUBSTRINGS = (
    "as an ai",
    "possibly",
    "maybe",
    "perhaps",
    "ÐºÐ°Ðº Ð¸Ð¸",
    "Ð²Ð¾Ð·Ð¼Ð¾Ð¶Ð½Ð¾",
    "Ð¼Ð¾Ð¶ÐµÑ‚ Ð±Ñ‹Ñ‚ÑŒ",
    "forse",
    "quizÃ¡",
    "peut-Ãªtre",
    "vielleicht",
)

STOPWORDS = {
    "a",
    "about",
    "and",
    "are",
    "can",
    "ÐºÐ°Ðº",
    "Ñ‡Ñ‚Ð¾",
    "ÑÑ‚Ð¾",
    "this",
    "that",
    "the",
    "Ð´Ð»Ñ",
    "with",
    "you",
    "your",
    "who",
    "what",
    "why",
    "how",
    "Ð¼Ð¾Ð¶ÐµÑˆÑŒ",
    "please",
    "could",
    "would",
    "ÐµÑÐ»Ð¸",
}

FAILURE_BY_LANGUAGE = {
    "ru": "Ð½Ð° ÑÑ‚Ð¾Ñ‚ Ð²Ð¾Ð¿Ñ€Ð¾Ñ ÑÐµÐ¹Ñ‡Ð°Ñ Ð½Ð¾Ñ€Ð¼Ð°Ð»ÑŒÐ½Ð¾ Ð¾Ñ‚Ð²ÐµÑ‚Ð¸Ñ‚ÑŒ Ð½Ðµ Ð¿Ð¾Ð»ÑƒÑ‡Ð¸Ð»Ð¾ÑÑŒ.",
    "uk": "Ð¯ Ð·Ð°Ñ€Ð°Ð· Ð½Ðµ Ð·Ð¼Ñ–Ð³ Ð²Ñ–Ð´Ð¿Ð¾Ð²Ñ–ÑÑ‚Ð¸ Ð½Ð° Ñ†Ðµ ÑÐº ÑÐ»Ñ–Ð´.",
    "en": "I couldn't answer that properly right now.",
    "it": "Su questa richiesta non sono riuscito a rispondere bene in questo momento.",
    "es": "No pude responder bien a esa solicitud en este momento.",
    "fr": "Je n'ai pas rÃ©ussi Ã  rÃ©pondre correctement Ã  cette demande pour le moment.",
    "de": "Ich konnte darauf im Moment nicht ordentlich antworten.",
}

UNCLEAR_BY_LANGUAGE = {
    "ru": "Ñ Ð½Ðµ Ð´Ð¾ ÐºÐ¾Ð½Ñ†Ð° Ð¿Ð¾Ð½ÑÐ», Ñ‡Ñ‚Ð¾ Ð¸Ð¼ÐµÐ½Ð½Ð¾ Ð²Ñ‹ Ð¸Ð¼ÐµÐµÑ‚Ðµ Ð² Ð²Ð¸Ð´Ñƒ.",
    "uk": "Ð¯ Ð½Ðµ Ð·Ð¾Ð²ÑÑ–Ð¼ Ð·Ñ€Ð¾Ð·ÑƒÐ¼Ñ–Ð², Ñ‰Ð¾ Ñ‚Ð¸ Ð¼Ð°Ñ”Ñˆ Ð½Ð° ÑƒÐ²Ð°Ð·Ñ–.",
    "en": "I didn't quite understand what you mean.",
    "it": "Non ho capito bene cosa intendi.",
    "es": "No entendÃ­ bien quÃ© quieres decir.",
    "fr": "Je n'ai pas bien compris ce que vous voulez dire.",
    "de": "Ich habe nicht ganz verstanden, was du meinst.",
}

GENERIC_TOPIC_BY_LANGUAGE = {
    "ru": "ÑÑ‚Ð¾Ð¼Ñƒ Ð²Ð¾Ð¿Ñ€Ð¾ÑÑƒ",
    "uk": "Ñ†ÐµÐ¹ Ð·Ð°Ð¿Ð¸Ñ‚",
    "en": "that question",
    "it": "questa richiesta",
    "es": "esa solicitud",
    "fr": "cette demande",
    "de": "dieser Frage",
}

TOPIC_REFERENCE_BY_LANGUAGE = {
    "ru": "Ð½Ð°ÑÑ‡ÐµÑ‚ {topic} â€” {answer}",
    "uk": "Ð©Ð¾Ð´Ð¾ {topic}: {answer}",
    "en": "About {topic}: {answer}",
    "it": "Su {topic}: {answer}",
    "es": "Sobre {topic}: {answer}",
    "fr": "Pour {topic} : {answer}",
    "de": "Zu {topic}: {answer}",
}

GENERIC_REFUSALS = {
    "ru": {
        "Ñ Ð½Ðµ Ð¼Ð¾Ð³Ñƒ Ð¿Ð¾Ð¼Ð¾Ñ‡ÑŒ Ñ Ñ‚Ð°ÐºÐ¸Ð¼ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ¾Ð¼.",
        "Ñ Ð½Ðµ Ð¼Ð¾Ð³Ñƒ Ð¿Ð¾Ð¼Ð¾Ñ‡ÑŒ Ñ ÑÑ‚Ð¸Ð¼ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ¾Ð¼.",
        "Ð½Ðµ Ð¼Ð¾Ð³Ñƒ Ð¿Ð¾Ð¼Ð¾Ñ‡ÑŒ Ñ Ñ‚Ð°ÐºÐ¸Ð¼ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ¾Ð¼.",
    },
    "en": {
        "i can't help with that request.",
        "i cannot help with that request.",
    },
    "it": {"non posso aiutare con questa richiesta."},
    "es": {"no puedo ayudar con esa solicitud."},
    "fr": {"je ne peux pas aider avec cette demande."},
    "de": {"ich kann bei dieser anfrage nicht helfen."},
}


@dataclass(slots=True)
class ValidationResult:
    cleaned_text: str
    answer_text: str
    is_bad: bool
    needs_judge: bool
    reason: str


@dataclass(slots=True)
class CandidateAssessment:
    cleaned_text: str
    answer_text: str
    score: int
    is_bad: bool
    needs_judge: bool
    clearly_acceptable: bool
    usable: bool
    reason: str
    is_refusal: bool
    is_placeholder: bool
    is_truncated: bool
    is_non_russian: bool
    has_reasoning_leak: bool
    is_malformed: bool


def sanitize_ai_output(
    text: str,
    user_query: str | None = None,
    expected_language: str | None = None,
    response_mode: str = "ai_prefixed",
) -> str:
    language = normalize_language(expected_language or detect_language(user_query or text))
    normalized_mode = _normalize_response_mode(response_mode)
    answer_text = normalize_answer_text(text)

    if is_identity_question(user_query):
        answer_text = normalize_answer_text(
            enforce_identity_answer(user_query, answer_text, response_mode=normalized_mode)
        )

    if not answer_text or is_useless_response(answer_text):
        answer_text = build_failure_answer(user_query, expected_language=language)
    elif _looks_like_unclear_response(answer_text.casefold()):
        answer_text = build_unclear_answer(user_query, expected_language=language)
    else:
        answer_text = _contextualize_generic_negative(answer_text, user_query, language)
        answer_text = _collapse_repeated_lead(answer_text)

    return format_visible_response(answer_text, response_mode=normalized_mode)


def format_visible_response(answer_text: str, response_mode: str = "ai_prefixed") -> str:
    clean_answer = repair_visible_text(_clean_answer_text(answer_text))
    if _normalize_response_mode(response_mode) == "human_like_owner":
        return clean_answer
    return f"{AI_PREFIX} {clean_answer}"


def repair_visible_text(text: str | None) -> str:
    candidate = text or ""
    if not candidate:
        return ""

    best = candidate
    best_score = _text_quality_score(candidate)
    current = candidate

    for _ in range(2):
        improved = False
        for encoding in ("latin-1", "cp1252"):
            decoded = _try_redecode_utf8(current, encoding)
            if not decoded:
                continue
            decoded_score = _text_quality_score(decoded)
            if decoded_score > best_score:
                best = decoded
                best_score = decoded_score
                current = decoded
                improved = True
        if not improved:
            break

    return best


def _try_redecode_utf8(text: str, encoding: str) -> str | None:
    try:
        return text.encode(encoding).decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None


def _text_quality_score(text: str) -> int:
    cyrillic_count = len(CYRILLIC_RE.findall(text))
    latin_count = len(LATIN_RE.findall(text))
    whitespace_count = text.count(" ")
    bad_marker_count = sum(text.count(marker) for marker in MOJIBAKE_MARKERS)
    replacement_count = text.count("\ufffd")
    return (cyrillic_count * 4) + latin_count + whitespace_count - (bad_marker_count * 6) - (replacement_count * 8)


def summarize_user_question(user_query: str | None, language: str | None = None) -> str:
    return extract_question_topic(user_query, language=language)


def extract_question_topic(user_query: str | None, language: str | None = None) -> str:
    normalized_language = normalize_language(language or detect_language(user_query))
    query = _extract_user_query_fragment(user_query)
    if not query:
        return GENERIC_TOPIC_BY_LANGUAGE.get(normalized_language, GENERIC_TOPIC_BY_LANGUAGE["en"])

    query = query.strip(" .!?")
    lowered = query.casefold()

    weather_markers = ("weather", "forecast", "meteo", "clima", "wetter", "Ð¿Ð¾Ð³Ð¾Ð´", "Ð¿Ñ€Ð¾Ð³Ð½Ð¾Ð·")
    news_markers = ("news", "notizie", "noticias", "actualitÃ©s", "nachrichten", "Ð½Ð¾Ð²Ð¾ÑÑ‚")
    chat_markers = ("chat", "chats", "messages", "messaggi", "mensajes", "Ñ‡Ð°Ñ‚", "Ñ‡Ð°Ñ‚Ñ‹")
    rate_markers = ("exchange", "currency", "cambio", "divisa", "wechsel", "ÐºÑƒÑ€Ñ", "Ð²Ð°Ð»ÑŽÑ‚")
    price_markers = ("price", "cost", "prezzo", "precio", "prix", "preis", "Ñ†ÐµÐ½")

    if any(marker in lowered for marker in weather_markers):
        return {
            "ru": "Ð¿Ð¾Ð³Ð¾Ð´Ñ‹",
            "en": "the weather",
            "it": "il meteo",
            "es": "el clima",
            "fr": "la mÃ©tÃ©o",
            "de": "das Wetter",
        }.get(normalized_language, "the weather")
    if any(marker in lowered for marker in news_markers):
        return {
            "ru": "Ð½Ð¾Ð²Ð¾ÑÑ‚ÐµÐ¹",
            "en": "the news",
            "it": "le notizie",
            "es": "las noticias",
            "fr": "les actualitÃ©s",
            "de": "die Nachrichten",
        }.get(normalized_language, "the news")
    if any(marker in lowered for marker in chat_markers):
        return {
            "ru": "Ñ‡Ð°Ñ‚Ð¾Ð²",
            "en": "chats",
            "it": "le chat",
            "es": "los chats",
            "fr": "les chats",
            "de": "Chats",
        }.get(normalized_language, "chats")
    if any(marker in lowered for marker in rate_markers):
        return {
            "ru": "ÐºÑƒÑ€ÑÐ° Ð²Ð°Ð»ÑŽÑ‚",
            "en": "exchange rates",
            "it": "il cambio",
            "es": "el tipo de cambio",
            "fr": "le taux de change",
            "de": "den Wechselkurs",
        }.get(normalized_language, "exchange rates")
    if any(marker in lowered for marker in price_markers):
        return {
            "ru": "Ñ†ÐµÐ½Ñ‹",
            "en": "the price",
            "it": "il prezzo",
            "es": "el precio",
            "fr": "le prix",
            "de": "den Preis",
        }.get(normalized_language, "the price")

    if len(query.split()) <= 8 and len(query) <= 72:
        return query

    tokens = [token for token in _keyword_tokens(query) if token not in STOPWORDS]
    if tokens:
        return " ".join(tokens[:4])
    return query[:72]


def build_failure_answer(user_query: str | None, *, expected_language: str | None = None) -> str:
    language = normalize_language(expected_language or detect_language(user_query))
    return FAILURE_BY_LANGUAGE.get(language, FAILURE_BY_LANGUAGE["en"])


def build_unclear_answer(user_query: str | None, *, expected_language: str | None = None) -> str:
    language = normalize_language(expected_language or detect_language(user_query))
    return UNCLEAR_BY_LANGUAGE.get(language, UNCLEAR_BY_LANGUAGE["en"])


def normalize_answer_text(text: str | None) -> str:
    cleaned = text or ""
    cleaned = REASONING_BLOCK_RE.sub(" ", cleaned)
    cleaned = OPEN_REASONING_BLOCK_RE.sub(" ", cleaned)
    cleaned = SELF_CLOSING_REASONING_TAG_RE.sub(" ", cleaned)
    cleaned = LEFTOVER_REASONING_TAG_RE.sub(" ", cleaned)
    cleaned = REASONING_PREFIX_LINE_RE.sub(" ", cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n").strip()

    extracted = _extract_visible_answer(cleaned) or _extract_ai_line(cleaned)
    if extracted:
        cleaned = extracted

    cleaned = _remove_legacy_labels(cleaned)
    cleaned = _strip_reasoning_preamble(cleaned)
    cleaned = re.sub(r"(?im)^\s*(?:question|Ð²Ð¾Ð¿Ñ€Ð¾Ñ)\s*:\s*.+$", "", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"^(?:[-*]\s*)+", "", cleaned.strip())
    cleaned = repair_visible_text(cleaned)
    return cleaned.strip()


def strip_ai_prefix(text: str) -> str:
    return normalize_answer_text(text)


def contains_reasoning_leak(text: str | None) -> bool:
    candidate = text or ""
    return bool(
        REASONING_BLOCK_RE.search(candidate)
        or OPEN_REASONING_BLOCK_RE.search(candidate)
        or SELF_CLOSING_REASONING_TAG_RE.search(candidate)
        or LEFTOVER_REASONING_TAG_RE.search(candidate)
        or REASONING_PREFIX_LINE_RE.search(candidate)
        or _count_reasoning_preamble_paragraphs(candidate)[0] > 0
    )


def is_refusal_response(text: str) -> bool:
    lowered = normalize_answer_text(text).casefold()
    return any(marker in lowered for marker in REFUSAL_SUBSTRINGS)


def is_useless_response(text: str) -> bool:
    lowered = normalize_answer_text(text).casefold()
    if lowered in USELESS_EXACT:
        return True
    return any(marker in lowered for marker in USELESS_SUBSTRINGS)


def is_non_russian_response(text: str, expected_language: str | None = None) -> bool:
    if expected_language is None:
        return False
    language = normalize_language(expected_language)
    return not is_text_in_language(normalize_answer_text(text), language)


def is_wrong_language_response(text: str, expected_language: str | None = None) -> bool:
    return is_non_russian_response(text, expected_language=expected_language)


def is_truncated_response(text: str, finish_reason: str | None) -> bool:
    answer = normalize_answer_text(text).strip()
    lowered_finish_reason = (finish_reason or "").casefold()
    if lowered_finish_reason in {"length", "max_tokens"}:
        return True
    if not answer:
        return False
    if answer.endswith(("...", "\u2026")):
        return True
    if BROKEN_ENDING_RE.search(answer):
        return True
    if len(answer) >= 40 and not answer.endswith((".", "!", "?", "\"", "'", ")", "]")):
        last_token = answer.rsplit(maxsplit=1)[-1]
        if UNFINISHED_WORD_RE.search(last_token):
            return True
    return False


_TG_HTML_TAG_RE = re.compile(
    r"<(?:/?(?:b|i|u|s|code|pre|a|tg-spoiler|blockquote|tg-emoji)\b[^>]{0,120})>",
    re.IGNORECASE,
)

def is_malformed_response(text: str) -> bool:
    answer = normalize_answer_text(text)
    if not HTMLISH_TAG_RE.search(answer):
        return False
    # Strip valid TG HTML tags â€” if unknown tags remain, it's malformed
    stripped = _TG_HTML_TAG_RE.sub("", answer)
    return bool(HTMLISH_TAG_RE.search(stripped))


def assess_candidate_response(
    text: str,
    finish_reason: str | None,
    *,
    prompt: str,
    expected_language: str | None = None,
    allow_refusal: bool = False,
    response_mode: str = "ai_prefixed",
) -> CandidateAssessment:
    raw_text = text or ""
    language = normalize_language(expected_language or detect_language(prompt))
    answer_text = normalize_answer_text(raw_text)
    cleaned_text = sanitize_ai_output(
        answer_text,
        user_query=prompt,
        expected_language=language,
        response_mode=response_mode,
    )

    has_reasoning_leak = contains_reasoning_leak(raw_text)
    is_placeholder = not answer_text or is_useless_response(answer_text)
    is_refusal = is_refusal_response(answer_text)
    is_truncated = is_truncated_response(answer_text, finish_reason)
    is_wrong_language = is_wrong_language_response(answer_text, expected_language=language)
    is_malformed = is_malformed_response(answer_text)
    has_meaningful_text = bool(answer_text and re.search(r"[A-Za-z\u0400-\u04FF0-9]{2,}", answer_text))

    score = 100
    reasons: list[str] = []

    if not answer_text:
        score -= 140
        reasons.append("empty_response")
    if has_reasoning_leak:
        score -= 120
        reasons.append("reasoning_leak")
    if is_placeholder:
        score -= 100
        reasons.append("placeholder_response")
    if is_refusal and not allow_refusal:
        score -= 90
        reasons.append("refusal_on_safe_prompt")
    if is_truncated:
        score -= 60
        reasons.append("truncated_response")
    if is_malformed:
        score -= 70
        reasons.append("malformed_response")
    if is_wrong_language:
        score -= 50
        reasons.append("wrong_language_response")
    if len(answer_text) < 4:
        score -= 45
        reasons.append("too_short")
    elif len(answer_text) < 12:
        score -= 20
        reasons.append("short_response")

    lowered = answer_text.casefold()
    if any(marker in lowered for marker in SUSPICIOUS_SUBSTRINGS):
        score -= 15
        reasons.append("suspicious_wording")

    relevance_bonus = _relevance_bonus(prompt, answer_text)
    score += relevance_bonus
    if relevance_bonus <= 0 and len(answer_text) >= 20:
        score -= 10
        reasons.append("low_relevance")

    if has_meaningful_text and not any((has_reasoning_leak, is_placeholder, is_truncated, is_malformed, is_wrong_language)):
        score += 10
    if answer_text.endswith((".", "!", "?", "\"", "'", ")", "]")):
        score += 5

    usable = has_meaningful_text
    clearly_acceptable = (
        usable
        and score >= 70
        and not has_reasoning_leak
        and not is_placeholder
        and not is_refusal
        and not is_truncated
        and not is_malformed
        and not is_wrong_language
    )
    is_bad = (
        not usable
        or has_reasoning_leak
        or is_placeholder
        or is_truncated
        or is_malformed
        or is_wrong_language
        or (is_refusal and not allow_refusal)
        or score < 25
    )
    needs_judge = usable and not clearly_acceptable and score >= 20
    reason = reasons[0] if reasons else "accepted_locally"

    return CandidateAssessment(
        cleaned_text=cleaned_text,
        answer_text=answer_text,
        score=score,
        is_bad=is_bad,
        needs_judge=needs_judge,
        clearly_acceptable=clearly_acceptable,
        usable=usable,
        reason=reason,
        is_refusal=is_refusal,
        is_placeholder=is_placeholder,
        is_truncated=is_truncated,
        is_non_russian=is_wrong_language,
        has_reasoning_leak=has_reasoning_leak,
        is_malformed=is_malformed,
    )


def choose_best_available_index(assessments: list[CandidateAssessment]) -> int | None:
    if not assessments:
        return None
    usable_indices = [index for index, item in enumerate(assessments) if item.usable]
    if not usable_indices:
        return None
    return max(
        usable_indices,
        key=lambda index: (
            assessments[index].score,
            1 if not assessments[index].is_refusal else 0,
            1 if not assessments[index].is_placeholder else 0,
            1 if not assessments[index].is_truncated else 0,
            len(assessments[index].answer_text),
        ),
    )


def validate_ai_response(
    text: str,
    finish_reason: str | None,
    *,
    require_russian: bool = False,
    expected_language: str | None = None,
    response_mode: str = "ai_prefixed",
) -> ValidationResult:
    language = expected_language or detect_language(text)
    assessment = assess_candidate_response(
        text,
        finish_reason,
        prompt="",
        expected_language=language,
        allow_refusal=False,
        response_mode=response_mode,
    )
    return ValidationResult(
        cleaned_text=assessment.cleaned_text,
        answer_text=assessment.answer_text,
        is_bad=assessment.is_bad,
        needs_judge=assessment.needs_judge,
        reason=assessment.reason,
    )


def _contextualize_generic_negative(answer_text: str, user_query: str | None, language: str) -> str:
    lowered = answer_text.casefold().strip()
    exact_refusals = GENERIC_REFUSALS.get(language, set())
    if lowered not in exact_refusals:
        return answer_text

    topic = extract_question_topic(user_query, language=language)
    generic_topic = GENERIC_TOPIC_BY_LANGUAGE.get(language, GENERIC_TOPIC_BY_LANGUAGE["en"])
    if not topic or topic == generic_topic:
        return answer_text

    template = TOPIC_REFERENCE_BY_LANGUAGE.get(language, TOPIC_REFERENCE_BY_LANGUAGE["en"])
    return template.format(topic=topic, answer=_lowercase_first(answer_text))


def _relevance_bonus(prompt: str, answer_text: str) -> int:
    prompt_tokens = _keyword_tokens(_extract_user_query_fragment(prompt))
    if not prompt_tokens:
        return 0
    answer_tokens = _keyword_tokens(answer_text)
    if not answer_tokens:
        return -10

    overlap = len(prompt_tokens & answer_tokens)
    if overlap >= 3:
        return 18
    if overlap == 2:
        return 12
    if overlap == 1:
        return 6
    return 0


def _keyword_tokens(text: str) -> set[str]:
    tokens = {token.casefold() for token in WORD_RE.findall(text or "")}
    return {token for token in tokens if token not in STOPWORDS and len(token) >= 3}


def _extract_user_query_fragment(user_query: str | None) -> str:
    if not user_query:
        return ""

    text = (user_query or "").strip()
    for marker in ("Owner request:\n", "ProjectOwner request:\n", "Newest incoming message:\n", "Incoming message:\n", "User prompt:\n"):
        if marker in text:
            text = text.split(marker, 1)[1].strip()
    if "\n\n" in text:
        text = text.split("\n\n", 1)[0].strip()
    if "\n" in text:
        first_line = text.split("\n", 1)[0].strip()
        if first_line:
            text = first_line

    text = TRIGGER_PREFIX_RE.sub("", text)
    text = NON_TOPIC_RE.sub(" ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" -,.!?")


def _extract_visible_question(text: str | None) -> str:
    if not text:
        return ""
    match = QUESTION_LINE_RE.search(text)
    return match.group(1).strip() if match else ""


def _extract_visible_answer(text: str | None) -> str:
    if not text:
        return ""
    match = ANSWER_LINE_RE.search(text)
    if not match:
        return ""
    answer_lines = [match.group(1).strip()]
    trailing_raw = text[match.end():]
    trailing = trailing_raw.strip()
    if trailing and not QUESTION_LINE_RE.search(trailing):
        separator = "\n\n" if trailing_raw.startswith("\n\n") else "\n"
        answer_lines.append(f"{separator}{_remove_legacy_labels(trailing)}")
    return "".join(line for line in answer_lines if line).strip()


def _extract_ai_line(text: str | None) -> str:
    if not text:
        return ""
    match = AI_LINE_RE.search(text)
    if not match:
        return ""
    first_line = match.group(1).strip()
    trailing_raw = text[match.end():]
    trailing = trailing_raw.strip()
    if trailing:
        separator = "\n\n" if trailing_raw.startswith("\n\n") else "\n"
        return f"{first_line}{separator}{trailing}".strip()
    return first_line


def _remove_legacy_labels(text: str) -> str:
    cleaned_lines: list[str] = []
    blank_pending = False
    for line in (text or "").splitlines():
        if QUESTION_LINE_RE.match(line):
            continue
        normalized_line = LEGACY_PREFIX_RE.sub("", line)
        normalized_line = INLINE_LEGACY_PREFIX_RE.sub("", normalized_line)
        normalized_line = re.sub(r"\s{2,}", " ", normalized_line).strip()
        if not normalized_line:
            if cleaned_lines:
                blank_pending = True
            continue
        if blank_pending:
            cleaned_lines.append("")
            blank_pending = False
        cleaned_lines.append(normalized_line)
    cleaned = "\n".join(cleaned_lines)
    return cleaned.strip()


def _strip_reasoning_preamble(text: str) -> str:
    count, has_strong_marker = _count_reasoning_preamble_paragraphs(text)
    if count <= 0:
        return text

    paragraphs = [
        paragraph.strip()
        for paragraph in REASONING_PARAGRAPH_SPLIT_RE.split(text or "")
        if paragraph.strip()
    ]
    if count >= len(paragraphs):
        return text
    if count < 2 and not has_strong_marker:
        return text

    remainder = "\n\n".join(paragraphs[count:]).strip()
    if not remainder or _looks_like_reasoning_paragraph(remainder):
        return text
    return remainder


def _count_reasoning_preamble_paragraphs(text: str) -> tuple[int, bool]:
    paragraphs = [
        paragraph.strip()
        for paragraph in REASONING_PARAGRAPH_SPLIT_RE.split(text or "")
        if paragraph.strip()
    ]
    if len(paragraphs) < 2:
        return 0, False

    count = 0
    has_strong_marker = False
    for paragraph in paragraphs[:-1]:
        is_reasoning, is_strong = _classify_reasoning_paragraph(paragraph)
        if not is_reasoning:
            break
        count += 1
        has_strong_marker = has_strong_marker or is_strong
    return count, has_strong_marker


def _looks_like_reasoning_paragraph(paragraph: str) -> bool:
    is_reasoning, _ = _classify_reasoning_paragraph(paragraph)
    return is_reasoning


def _classify_reasoning_paragraph(paragraph: str) -> tuple[bool, bool]:
    normalized = " ".join((paragraph or "").strip().casefold().split())
    if not normalized:
        return False, False
    if len(normalized) < 24:
        return False, False
    if HTMLISH_TAG_RE.search(normalized):
        return False, False

    marker_hits = sum(
        1 for marker in REASONING_PREAMBLE_MARKERS if marker in normalized
    )
    strong_hits = any(
        marker in normalized for marker in REASONING_PREAMBLE_STRONG_MARKERS
    )
    starts_like_reasoning = any(
        normalized.startswith(marker) for marker in REASONING_PREAMBLE_STARTERS
    )

    is_reasoning = marker_hits >= 2 or (starts_like_reasoning and marker_hits >= 1)
    return is_reasoning, strong_hits


def _clean_answer_text(text: str) -> str:
    cleaned = normalize_answer_text(text)
    cleaned = _remove_legacy_labels(cleaned)
    cleaned = _normalize_visible_whitespace(cleaned)
    if cleaned.casefold().startswith("ai:"):
        cleaned = cleaned[3:].strip()
    cleaned = _collapse_repeated_lead(cleaned)
    return cleaned or FAILURE_BY_LANGUAGE["en"]


def _looks_like_unclear_response(lowered_answer: str) -> bool:
    return any(marker in lowered_answer for marker in UNCLEAR_SUBSTRINGS)


def _collapse_repeated_lead(text: str) -> str:
    parts = [part.strip() for part in text.split("â€”")]
    if len(parts) < 3:
        return text
    first = _normalize_segment(parts[0])
    second = _normalize_segment(parts[1])
    if not first or first != second:
        return text
    collapsed = [parts[0], *parts[2:]]
    return " â€” ".join(part for part in collapsed if part).strip()


def _normalize_visible_whitespace(text: str) -> str:
    normalized_lines: list[str] = []
    blank_pending = False
    for raw_line in (text or "").split("\n"):
        normalized_line = re.sub(r"[ \t]{2,}", " ", raw_line).strip()
        if not normalized_line:
            if normalized_lines:
                blank_pending = True
            continue
        if blank_pending:
            normalized_lines.append("")
            blank_pending = False
        normalized_lines.append(normalized_line)
    return "\n".join(normalized_lines).strip()


def _normalize_segment(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip(" .,:;!?-â€”")


def _lowercase_first(text: str) -> str:
    if not text:
        return text
    return text[:1].lower() + text[1:]


def _normalize_response_mode(response_mode: str | None) -> str:
    normalized = (response_mode or "").strip().casefold()
    if normalized in {"human_like", "human_like_owner"}:
        return "human_like_owner"
    return "ai_prefixed"

