from __future__ import annotations

import re
from dataclasses import dataclass

from infra.language_tools import detect_language, tr

SAFETY_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "explosives": (
        re.compile(
            r"(?:\u043a\u0430\u043a|how|make|build|create|\u0441\u0434\u0435\u043b\u0430\u0442\u044c|\u0441\u043e\u0431\u0440\u0430\u0442\u044c|\u0441\u043e\u0437\u0434\u0430\u0442\u044c)[^\n]{0,40}"
            r"(?:\u0431\u043e\u043c\u0431|\u0432\u0437\u0440\u044b\u0432\u0447\u0430\u0442|\u0434\u0438\u043d\u0430\u043c\u0438\u0442|bomb|explosive|molotov)",
            re.IGNORECASE,
        ),
    ),
    "weapons": (
        re.compile(
            r"(?:\u043a\u0430\u043a|how|make|build|\u0441\u0434\u0435\u043b\u0430\u0442\u044c|\u0441\u043e\u0431\u0440\u0430\u0442\u044c)[^\n]{0,40}"
            r"(?:\u043e\u0440\u0443\u0436|\u043f\u0438\u0441\u0442\u043e\u043b\u0435\u0442|\u0440\u0443\u0436\u044c|\u043d\u043e\u0436 weapon|gun|rifle|weapon)",
            re.IGNORECASE,
        ),
    ),
    "harm_people": (
        re.compile(
            r"(?:\u043a\u0430\u043a|how|instructions|step by step|\u0438\u043d\u0441\u0442\u0440\u0443\u043a\u0446)[^\n]{0,50}"
            r"(?:\u0443\u0431\u0438\u0442|\u043e\u0442\u0440\u0430\u0432\u0438\u0442|\u0440\u0430\u043d\u0438\u0442|\u043d\u0430\u043f\u0430\u0441\u0442\u044c|kill|poison|hurt|attack)",
            re.IGNORECASE,
        ),
    ),
    "malware": (
        re.compile(
            r"(?:\u043a\u0430\u043a|how|write|create|make|\u043d\u0430\u043f\u0438\u0441\u0430\u0442\u044c|\u0441\u043e\u0437\u0434\u0430\u0442\u044c)[^\n]{0,50}"
            r"(?:\u0432\u0438\u0440\u0443\u0441|\u0442\u0440\u043e\u044f\u043d|\u043c\u0430\u043b\u0432\u0430\u0440|\u0448\u0438\u0444\u0440\u043e\u0432\u0430\u043b\u044c\u0449\u0438\u043a|virus|trojan|malware|ransomware|keylogger)",
            re.IGNORECASE,
        ),
    ),
    "credential_theft": (
        re.compile(
            r"(?:\u0443\u043a\u0440\u0430\u0441\u0442\u044c|\u0432\u044b\u0442\u044f\u043d\u0443\u0442\u044c|\u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c|\u0441\u043d\u044f\u0442\u044c|steal|grab|get)[^\n]{0,50}"
            r"(?:\u043f\u0430\u0440\u043e\u043b|\u043a\u0440\u0435\u0434\u0438\u0442\u043a|\u043a\u0443\u043a\u0438|\u0442\u043e\u043a\u0435\u043d|password|credentials|cookie|token)",
            re.IGNORECASE,
        ),
    ),
    "illegal_hacking": (
        re.compile(
            r"(?:\u0432\u0437\u043b\u043e\u043c|\u0432\u0437\u043b\u043e\u043c\u0430\u0442\u044c|\u043e\u0431\u043e\u0439\u0442\u0438|\u043e\u0431\u0445\u043e\u0434|hack|bypass|crack|exploit)"
            r"[^\n]{0,60}(?:\u0430\u043a\u043a\u0430\u0443\u043d\u0442|\u0441\u0438\u0441\u0442\u0435\u043c|\u0437\u0430\u0449\u0438\u0442|\u043f\u0430\u0440\u043e\u043b|account|system|security|password|wifi|router)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:sql injection|xss|ddos|phishing|\u0444\u0438\u0448\u0438\u043d\u0433|\u0434\u0434\u043e\u0441)[^\n]{0,50}"
            r"(?:\u043a\u0430\u043a|how|\u0441\u0434\u0435\u043b\u0430\u0442\u044c|\u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c|run|launch)?",
            re.IGNORECASE,
        ),
    ),
    "violent_wrongdoing": (
        re.compile(
            r"(?:\u043a\u0430\u043a|how|plan|\u0441\u043f\u043b\u0430\u043d\u0438\u0440\u043e\u0432\u0430\u0442\u044c|\u043e\u0440\u0433\u0430\u043d\u0438\u0437\u043e\u0432\u0430\u0442\u044c)[^\n]{0,60}"
            r"(?:\u043d\u0430\u043f\u0430\u0434\u0435\u043d\u0438\u0435|\u0443\u0431\u0438\u0439\u0441\u0442\u0432|\u0442\u0435\u0440\u0430\u043a\u0442|attack|murder|terror)",
            re.IGNORECASE,
        ),
    ),
}


@dataclass(slots=True)
class SafetyClassification:
    is_safe: bool
    category: str
    matched_pattern: str | None
    refusal_text: str


def classify_request_safety(prompt: str) -> SafetyClassification:
    text = (prompt or "").strip()
    refusal_text = tr("safety_refusal", detect_language(text))
    if not text:
        return SafetyClassification(is_safe=True, category="empty", matched_pattern=None, refusal_text=refusal_text)

    for category, patterns in SAFETY_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(text):
                return SafetyClassification(
                    is_safe=False,
                    category=category,
                    matched_pattern=pattern.pattern,
                    refusal_text=refusal_text,
                )

    return SafetyClassification(is_safe=True, category="safe", matched_pattern=None, refusal_text=refusal_text)
