from __future__ import annotations

import re
from dataclasses import dataclass


WORD_RE = re.compile(r"[A-Za-z\u0400-\u04FF0-9]+", re.UNICODE)
REACTION_WORDS = {
    "ok", "okay", "kk", "k", "lol", "lmao", "ага", "ок", "окей", "ясно",
    "пон", "понял", "спс", "thanks", "thx", "nice", "понятно", "мм", "угу",
    "ладно", "хорошо", "норм", "отлично", "пойдёт", "пойдет", "збс",
    "го", "ясн", "ясненько", "understood", "got it", "cool", "sure", "yep", "nope",
}
QUESTION_STARTS = (
    "кто",
    "что",
    "где",
    "когда",
    "зачем",
    "почему",
    "как",
    "можешь",
    "можно",
    "подскажи",
    "скажи",
    "объясни",
    "помоги",
    "думаешь",
    "стоит ли",
    "глянь",
    "посмотри",
    "can you",
    "could you",
    "would you",
    "how",
    "what",
    "why",
    "when",
    "where",
    "who",
    "help",
    "tell me",
    "look",
    "check",
    "кто",
    "что",
    "как",
    "зачем",
    "почему",
    "сколько",
    "помоги",
    "объясни",
    "подскажи",
    "расскажи",
    "что такое",
    "что значит",
    "что подразумеваешь",
    "как разработчик",
    "хто",
    "що",
    "як",
    "скільки",
    "поясни",
    "розкажи",
)
REQUEST_MARKERS = (
    "пожалуйста",
    "помоги",
    "подскажи",
    "скинь",
    "посмотри",
    "ответь",
    "глянь",
    "что скажешь",
    "как думаешь",
    "стоит ли",
    "please",
    "send",
    "tell me",
    "check",
    "look up",
    "explain",
    "объясни",
    "обьясни",
    "подскажи",
    "расскажи",
    "помоги",
    "помощь нужна",
    "нужна помощь",
    "что такое",
    "что значит",
    "что подразумеваешь",
    "что имеешь в виду",
    "как работает",
    "как сделать",
    "как настроить",
    "как исправить",
    "как решить",
    "как разработчик",
    "define",
    "clarify",
    "what do you mean",
    "how does it work",
    "help me",
    "could you explain",
    "можешь помочь",
    "можешь объяснить",
    "нужен совет",
    "поясни",
    "розкажи",
    "допоможи",
)
COMMAND_MARKERS = (
    "сделай", "найди", "отправь", "перешли", "summarize", "rewrite", "extract", "find", "send",
    "удали", "сотри", "убери", "скинь", "перекинь", "закинь", "кинь", "пошли", "отошли",
    "архивируй", "разархивируй", "заблокируй", "разблокируй", "закрепи", "открепи",
    "вступи", "покинь", "выйди", "подпишись", "отпишись", "забань", "кикни", "выгони",
    "прочитай чат", "отметь", "переименуй", "назови", "создай группу",
    "покажи историю", "forward", "copy", "delete", "archive", "block",
)


@dataclass(slots=True)
class IntentResult:
    kind: str
    confidence: float
    is_question_like: bool
    is_request_like: bool


def classify_message_intent(text: str, *, command_like: bool = False) -> IntentResult:
    normalized = " ".join((text or "").split()).strip()
    lowered = normalized.casefold()
    tokens = WORD_RE.findall(lowered)

    if not normalized:
        return IntentResult(kind="unclear", confidence=0.0, is_question_like=False, is_request_like=False)

    if command_like or lowered.startswith(COMMAND_MARKERS):
        return IntentResult(kind="command", confidence=0.95, is_question_like=False, is_request_like=True)

    question_like = "?" in normalized or lowered.startswith(QUESTION_STARTS) or _contains_question_phrase(lowered)
    request_like = any(marker in lowered for marker in REQUEST_MARKERS)

    if question_like:
        return IntentResult(kind="question", confidence=0.92, is_question_like=True, is_request_like=request_like)

    if request_like:
        return IntentResult(kind="request", confidence=0.84, is_question_like=True, is_request_like=True)

    if _looks_like_reaction(normalized, tokens):
        return IntentResult(kind="reaction", confidence=0.9, is_question_like=False, is_request_like=False)

    if len(tokens) <= 1 and len(normalized) <= 12:
        return IntentResult(kind="reaction", confidence=0.6, is_question_like=False, is_request_like=False)

    return IntentResult(kind="unclear", confidence=0.45, is_question_like=False, is_request_like=False)


def _looks_like_reaction(text: str, tokens: list[str]) -> bool:
    if not text:
        return False
    stripped = text.strip()
    if stripped and all(not char.isalnum() for char in stripped):
        return True
    if len(tokens) <= 2 and all(token in REACTION_WORDS for token in tokens):
        return True
    return len(tokens) <= 2 and len(stripped) <= 10 and stripped.casefold() in REACTION_WORDS


def _contains_question_phrase(lowered: str) -> bool:
    question_phrases = (
        "что такое",
        "что значит",
        "что подразумеваешь",
        "что имеешь в виду",
        "как работает",
        "как сделать",
        "как настроить",
        "как исправить",
        "как решить",
        "как думаешь",
        "нужна помощь",
        "помощь нужна",
        "подскажи",
        "объясни",
        "расскажи",
        "поясни",
        "розкажи",
        "поясни",
        "what do you mean",
        "how does it work",
        "can you help",
        "could you explain",
        "tell me",
    )
    return any(phrase in lowered for phrase in question_phrases)
