from __future__ import annotations

import re
import unicodedata
from .visitor_models import TopicCategory, PolicyDecision


def _normalize_unicode(text: str) -> str:
    """Normalize unicode to prevent homoglyph/lookalike injection bypasses.
    Maps confusable characters to ASCII equivalents."""
    # NFKD decomposition + strip combining marks
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(
        ch for ch in decomposed if unicodedata.category(ch) != "Mn"
    )
    # Map common Cyrillic lookalikes to Latin
    cyrillic_to_latin = str.maketrans(
        "\u0430\u0410\u0435\u0415\u0456\u0406\u043e\u041e\u0440\u0420\u0441\u0421\u0443\u0423\u0445\u0425",
        "aAeEiIoOpPcCyyxX",
    )
    return stripped.translate(cyrillic_to_latin).casefold()


# ========================
# SAFETY / INJECTION
# ========================

_INJECTION_PATTERNS = (
    re.compile(r"(?i)ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|prompts|rules)"),
    re.compile(r"(?i)you\s+are\s+now\s+(a|an)\s+"),
    re.compile(r"(?i)forget\s+(your|all|the)\s+(instructions|rules|system|prompt)"),
    re.compile(r"(?i)act\s+as\s+(a|an|if)\s+"),
    re.compile(r"(?i)system\s*prompt"),
    re.compile(r"(?i)reveal\s+(your|the)\s+(prompt|instructions|system)"),
    re.compile(r"(?i)show\s+(me\s+)?(your|the)\s+(prompt|instructions|system)"),
    re.compile(r"(?i)what\s+(is|are)\s+your\s+(system|instructions|prompt)"),
    re.compile(r"(?i)pretend\s+(you|to\s+be)\s+"),
    re.compile(r"(?i)jailbreak"),
    re.compile(r"(?i)DAN\s+mode"),
    re.compile(r"(?i)developer\s+mode"),
)

_INTERNAL_PATTERNS = (
    re.compile(r"(?i)(owner|admin|Ð°Ð´Ð¼Ð¸Ð½)\s*(mode|Ñ€ÐµÐ¶Ð¸Ð¼|Ñ„ÑƒÐ½ÐºÑ†Ð¸Ð¸|ÐºÐ¾Ð¼Ð°Ð½Ð´Ñ‹)"),
    re.compile(r"(?i)(Ð²ÐºÐ»ÑŽÑ‡Ð¸|enable|activate)\s+(owner|admin|Ð°Ð´Ð¼Ð¸Ð½)"),
    re.compile(r"(?i)(Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸|settings|config|ÐºÐ¾Ð½Ñ„Ð¸Ð³)"),
    re.compile(r"(?i)(Ð¼Ð¾Ð´ÐµÐ»ÑŒ|model)\s+(judge|ÑÑƒÐ´ÑŒÑ|Ð¿ÐµÑ€ÐµÐºÐ»ÑŽÑ‡ÐµÐ½)"),
    re.compile(r"(?i)(whitelist|allowlist|Ð±ÐµÐ»Ñ‹Ð¹\s*ÑÐ¿Ð¸ÑÐ¾Ðº)"),
    re.compile(r"(?i)(api[_\s]?key|token|secret|Ð¿Ð°Ñ€Ð¾Ð»ÑŒ|password)"),
    re.compile(r"(?i)(Ð²Ð½ÑƒÑ‚Ñ€ÐµÐ½Ð½|internal|hidden|ÑÐºÑ€Ñ‹Ñ‚)"),
    re.compile(r"(?i)(rate\s*limit|rate_limit|Ð»Ð¸Ð¼Ð¸Ñ‚|quota)"),
    re.compile(r"(?i)(groq|openai|llama|qwen)\s*(api|ÐºÐ»ÑŽÑ‡|key)"),
)

# ========================
# TOPIC DETECTION
# ========================

_OWNER_PATTERNS = (
    re.compile(r"(?i)(ÐºÑ‚Ð¾\s+(Ñ‚Ð°ÐºÐ¾Ð¹|ÑÑ‚Ð¾)|who\s+(is|this))\s*(Ñ…Ð¾Ð·ÑÐ¸Ð½|Ð²Ð»Ð°Ð´ÐµÐ»ÐµÑ†|owner|author|Ð°Ð²Ñ‚Ð¾Ñ€|ÑÐ¾Ð·Ð´Ð°Ñ‚ÐµÐ»ÑŒ|developer|assistant)"),
    re.compile(r"(?i)\b(Ð²Ð»Ð°Ð´ÐµÐ»ÐµÑ†|Ñ…Ð¾Ð·ÑÐ¸Ð½|owner|author|Ð°Ð²Ñ‚Ð¾Ñ€|ÑÐ¾Ð·Ð´Ð°Ñ‚ÐµÐ»ÑŒ|developer|Ñ€Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚Ñ‡Ð¸Ðº|creator)\b"),
    re.compile(r"(?i)(about|Ð¾Ð±)\s+(Ð½ÐµÐ³Ð¾|Ð½Ñ‘Ð¼|ÑÐµÐ±Ðµ|owner|Ñ…Ð¾Ð·ÑÐ¸Ð½|Ð°Ð²Ñ‚Ð¾Ñ€|assistant)"),
    re.compile(r"(?i)(Ñ€Ð°ÑÑÐºÐ°Ð¶Ð¸|tell|info)\s+(about|Ð¾Ð±|Ð¿Ñ€Ð¾)\s*(Ð½ÐµÐ³Ð¾|Ð½ÐµÐ³Ð¾|owner|Ð½ÐµÐ³Ð¾|Ð°Ð²Ñ‚Ð¾Ñ€|assistant|ÑÐ²Ð¾ÐµÐ³Ð¾|ÑÐ¾Ð·Ð´Ð°Ñ‚ÐµÐ»Ñ)"),
    re.compile(r"(?i)(ÐºÐ°Ðº\s+Ð·Ð¾Ð²ÑƒÑ‚|Ð¸Ð¼Ñ|nickname|Ð¿ÑÐµÐ²Ð´Ð¾Ð½Ð¸Ð¼)\s*(Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†|Ñ…Ð¾Ð·ÑÐ¸Ð½|ÑÐ¾Ð·Ð´Ð°Ñ‚ÐµÐ»|author)?"),
    re.compile(r"(?i)(ÐºÑ‚Ð¾\s+(Ñ‚ÐµÐ±Ñ|Ð²Ð°Ñ)\s+(ÑÐ¾Ð·Ð´Ð°Ð»|ÑÐ´ÐµÐ»Ð°Ð»|Ñ€Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚Ð°Ð»))"),
    re.compile(r"(?i)(ÐºÑ‚Ð¾\s+Ñ‚Ð²Ð¾Ð¹\s+ÑÐ¾Ð·Ð´Ð°Ñ‚ÐµÐ»ÑŒ|who\s+(created|made|built)\s+(you|Ñƒ))"),
    re.compile(r"(?i)(Ñ€Ð°ÑÑÐºÐ°Ð¶Ð¸\s+Ð¿Ñ€Ð¾\s+(ÑÐ²Ð¾ÐµÐ³Ð¾\s+)?(ÑÐ¾Ð·Ð´Ð°Ñ‚ÐµÐ»|owner|Ñ…Ð¾Ð·ÑÐ¸Ð½|Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†|Ð°Ð²Ñ‚Ð¾Ñ€))"),
    re.compile(r"(?i)(Ð¿Ñ€Ð¾\s+(Ð½ÐµÐ³Ð¾|Ð½ÐµÐ³Ð¾|ÑÐ²Ð¾ÐµÐ³Ð¾\s+ÑÐ¾Ð·Ð´Ð°Ñ‚ÐµÐ»|ÑÐµÐ±Ñ|Ð½ÐµÐ³Ð¾|Ð½ÐµÐ³Ð¾))"),
    re.compile(r"(?i)(ÐºÑ‚Ð¾\s+Ñ‚Ñ‹\s+Ñ‚Ð°Ðº(Ð¾Ð¹|Ð°Ñ)|Ñ‡Ñ‚Ð¾\s+Ñ‚Ñ‹\s+Ð·Ð°)"),
)

_PROJECTS_PATTERNS = (
    re.compile(r"(?i)\b(Ð¿Ñ€Ð¾ÐµÐºÑ‚|project|Ñ€Ð°Ð±Ð¾Ñ‚|portfolio|Ð¿Ð¾Ñ€Ñ‚Ñ„ÐµÐ»|Ñ€ÐµÐ¿Ð¾Ð·Ð¸Ñ‚Ð¾Ñ€|repo|github)\b"),
    re.compile(r"(?i)(Ñ‡Ñ‚Ð¾\s+(ÑÐ´ÐµÐ»Ð°Ð»|Ð´ÐµÐ»Ð°ÐµÑ‚|Ð¼Ð¾Ð¶ÐµÑ‚|ÑÐ¾Ð·Ð´Ð°Ð»|Ð½Ð°Ð¿Ð¸ÑÐ°Ð»))"),
    re.compile(r"(?i)(Ð³Ð´Ðµ\s+Ð¿Ð¾ÑÐ¼Ð¾Ñ‚Ñ€ÐµÑ‚ÑŒ|where\s+to\s+(see|find|look))"),
    re.compile(r"(?i)(Ð¿Ð¾ÐºÐ°Ð¶Ð¸|Ð¿Ð¾ÑÐ¼Ð¾Ñ‚Ñ€Ð¸|Ð½Ð°Ð¹Ð´Ð¸)\s+(Ð¿Ñ€Ð¾ÐµÐºÑ‚|ÐºÐ¾Ð´|Ñ€ÐµÐ¿Ð¾Ð·Ð¸Ñ‚Ð¾Ñ€Ð¸|repo|github)"),
    re.compile(r"(?i)(assistant[- ]?ai|assistantbot|Ð±Ð¾Ñ‚|userbot|ÑŽÐ·ÐµÑ€Ð±Ð¾Ñ‚)"),
    re.compile(r"(?i)(Ñ‡Ñ‚Ð¾\s+(Ñƒ\s+Ð½ÐµÐ³Ð¾|Ñƒ\s+Ð½ÐµÐ³Ð¾|Ñƒ\s+Ð½ÐµÐ³Ð¾)\s+Ð·Ð°\s+Ð¿Ñ€Ð¾ÐµÐºÑ‚)"),
    re.compile(r"(?i)(Ñ‡Ñ‚Ð¾\s+Ð·Ð°\s+Ð¿Ñ€Ð¾ÐµÐºÑ‚)"),
    re.compile(r"(?i)(ÐµÐ³Ð¾\s+Ð¿Ñ€Ð¾ÐµÐºÑ‚)"),
    re.compile(r"(?i)(ÐºÐ°ÐºÐ¸Ðµ\s+Ð¿Ñ€Ð¾ÐµÐºÑ‚)"),
)

_PROJECT_SPECIFIC_PATTERNS = (
    re.compile(r"(?i)(Ñ‡Ñ‚Ð¾\s+Ð´ÐµÐ»Ð°ÐµÑ‚|ÐºÐ°Ðº\s+Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÑ‚|ÐºÐ°Ðº\s+Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·Ñƒ)\s+(sql|python|api|ai|ml|Ð±Ð¾Ñ‚|ai|Ð±Ð°Ð·[Ð°Ñ‹]\s*Ð´Ð°Ð½Ð½)"),
    re.compile(r"(?i)(Ð²\s+(ÑÑ‚Ð¾Ð¼|Ñ‚Ð²Ð¾Ñ‘Ð¼|Ñ‚Ð²Ð¾ÐµÐ¼|Ð´Ð°Ð½Ð½Ð¾Ð¼))\s*(Ð¿Ñ€Ð¾ÐµÐºÑ‚|Ð±Ð¾Ñ‚|ÑÐ¸ÑÑ‚ÐµÐ¼)"),
    re.compile(r"(?i)(Ð²\s+Ð¿Ñ€Ð¾ÐµÐºÑ‚Ðµ|Ð²\s+Ð±Ð¾Ñ‚Ðµ|Ð²\s+ÑÐ¸ÑÑ‚ÐµÐ¼Ðµ)\s+(Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·Ñƒ|Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÑ‚|ÑÑ‚Ð¾Ð¸Ñ‚)"),
    re.compile(r"(?i)(ÐºÐ°Ðº\s+ÑƒÑÑ‚Ñ€Ð¾ÐµÐ½|ÐºÐ°Ðº\s+ÑƒÑÑ‚Ñ€Ð¾ÐµÐ½|Ð°Ñ€Ñ…Ð¸Ñ‚ÐµÐºÑ‚ÑƒÑ€|ÑÑ‚Ñ€ÑƒÐºÑ‚ÑƒÑ€Ð°)\s*(Ð¿Ñ€Ð¾ÐµÐºÑ‚|Ð±Ð¾Ñ‚|ÑÐ¸ÑÑ‚ÐµÐ¼|assistant)?"),
    re.compile(r"(?i)(ÐºÐ°Ðº\s+Ñ‚Ñ‹\s+Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÑˆÑŒ|ÐºÐ°Ðº\s+Ð±Ð¾Ñ‚\s+Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÑ‚|ÐºÐ°Ðº\s+ÑÑ‚Ð¾\s+Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÑ‚)"),
)

_TECHNICAL_PATTERNS = (
    re.compile(r"(?i)(Ñ‡Ñ‚Ð¾\s+Ñ‚Ð°ÐºÐ¾Ðµ|what\s+is|Ð¾Ð±ÑŠÑÑÐ½Ð¸|explain|define|Ð¾Ð¿Ñ€ÐµÐ´ÐµÐ»Ð¸)\s+"),
    re.compile(r"(?i)(Ñ‡ÐµÐ¼\s+Ð¾Ñ‚Ð»Ð¸Ñ‡|difference|Ñ€Ð°Ð·Ð½Ð¸Ñ†)\s+"),
    re.compile(r"(?i)(ÐºÐ°Ðº\s+Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÑ‚|how\s+does\s+\w+\s+work)\s+"),
    re.compile(r"(?i)\b(sql|api|rest|http|tcp|udp|dns|ssl|tls|ssh|xss|csrf|sqli|jwt|oauth|docker|nginx|linux|bash|python|javascript|html|css|json|xml|yaml|git|ci\s*cd|agile|scrum|microservice|kubernetes|websocket|webhook|lambda|regex|algorithm|database|cache|encrypt|hash|token|session|cookie|firewall|vpn|proxy|load\s*balancer|cdn|dns|certificate)\b"),
    re.compile(r"(?i)(ÑÐ·Ñ‹Ðº\s+Ð¿Ñ€Ð¾Ð³Ñ€Ð°Ð¼Ð¼Ð¸Ñ€|programming\s+language|framework|Ð±Ð¸Ð±Ð»Ð¸Ð¾Ñ‚ÐµÐº|library|Ñ„Ñ€ÐµÐ¹Ð¼Ð²Ð¾Ñ€Ðº)"),
    re.compile(r"(?i)(Ð¿Ñ€Ð¾Ñ‚Ð¾ÐºÐ¾Ð»|protocol|ÑÑ‚Ð°Ð½Ð´Ð°Ñ€Ñ‚|standard|Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚|format|Ð°Ð»Ð³Ð¾Ñ€Ð¸Ñ‚Ð¼|algorithm)"),
)

_FAQ_PATTERNS = (
    re.compile(r"(?i)\b(faq|Ñ‡Ð°ÑÑ‚Ð¾|Ð²Ð¾Ð¿Ñ€Ð¾Ñ|question|Ð¾Ñ‚Ð²ÐµÑ‚)\b"),
    re.compile(r"(?i)(ÐºÐ°Ðº\s+(ÑÐ²ÑÐ·Ð°Ñ‚ÑŒÑÑ|ÐºÐ¾Ð½Ñ‚Ð°ÐºÑ‚Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ|Ð½Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ))"),
    re.compile(r"(?i)(how\s+to\s+(contact|reach|connect))"),
)

_COLLABORATION_PATTERNS = (
    re.compile(r"(?i)(ÑÐ¾Ñ‚Ñ€ÑƒÐ´Ð½Ð¸Ñ‡ÐµÑÑ‚Ð²|collaborat|Ñ€Ð°Ð±Ð¾Ñ‚Ð°\s+Ð²Ð¼ÐµÑÑ‚Ðµ|partnership|Ð·Ð°ÐºÐ°Ð·|order|ÑƒÑÐ»ÑƒÐ³|service)"),
    re.compile(r"(?i)(Ð½Ð°Ð½ÑÑ‚ÑŒ|hire|Ð¿Ñ€ÐµÐ´Ð»Ð¾Ð¶|offer|ÑÑ‚Ð¾Ð¸Ð¼|price|Ñ€Ð°ÑÑ†ÐµÐ½Ðº|Ð±ÑŽÐ´Ð¶ÐµÑ‚|budget)"),
    re.compile(r"(?i)(Ð¼Ð¾Ð¶ÐµÑˆÑŒ\s+ÑÐ´ÐµÐ»Ð°Ñ‚ÑŒ|can\s+you\s+(build|make|create|develop))"),
)

_LINKS_PATTERNS = (
    re.compile(r"(?i)\b(ÑÑÑ‹Ð»Ðº|link|url|github|telegram|Ñ‚Ð³|ÑÐ°Ð¹Ñ‚|site|website|ÑÑ‚Ñ€Ð°Ð½Ð¸Ñ†|Ð¿Ð¾Ñ€Ñ‚Ñ„Ð¾Ð»Ð¸Ð¾|portfolio)\b"),
    re.compile(r"(?i)(t\.me|github\.com|http)"),
)

_ASSISTANT_PATTERNS = (
    re.compile(r"(?i)(Ñ‡Ñ‚Ð¾\s+(Ñ‚Ñ‹|Ð²Ñ‹)\s+ÑƒÐ¼ÐµÐµÑ‚|what\s+(can|do)\s+(you|Ñƒ))"),
    re.compile(r"(?i)(Ð¿Ð¾Ð¼Ð¾Ñ‰Ð½Ð¸Ðº|assistant|Ñ‡Ñ‚Ð¾\s+Ð¼Ð¾Ð¶ÐµÑˆÑŒ|capabilities|Ð²Ð¾Ð·Ð¼Ð¾Ð¶Ð½Ð¾ÑÑ‚|Ñ„ÑƒÐ½ÐºÑ†Ð¸Ð¸\s+Ð¿Ð¾Ð¼Ð¾Ñ‰Ð½Ð¸ÐºÐ°)"),
    re.compile(r"(?i)(Ð·Ð°Ñ‡ÐµÐ¼\s+Ñ‚Ñ‹|Ð´Ð»Ñ\s+Ñ‡ÐµÐ³Ð¾|why\s+(do|are)\s+you)"),
    re.compile(r"(?i)(ÐºÐ°Ðº\s+(Ñ‚Ñ‹|Ð²Ñ‹)\s+Ð¼Ð¾Ð¶ÐµÑˆÑŒ\s+Ð¿Ð¾Ð¼Ð¾Ñ‡|Ñ‡ÐµÐ¼\s+Ð¼Ð¾Ð¶ÐµÑˆÑŒ\s+Ð¿Ð¾Ð¼Ð¾Ñ‡)"),
    re.compile(r"(?i)^ÐºÑ‚Ð¾\s+(Ñ‚Ñ‹|Ð²Ñ‹)\s*[?.!]*\s*$"),
    re.compile(r"(?i)^Ñ‡Ñ‚Ð¾\s+(Ñ‚Ñ‹|Ð²Ñ‹)\s+(Ñ‚Ð°ÐºÐ¾Ðµ|Ð¸Ð·\s+ÑÐµÐ±Ñ\s+Ð¿Ñ€ÐµÐ´ÑÑ‚Ð°Ð²Ð»ÑÐµÑˆÑŒ)\s*[?.!]*\s*$"),
    re.compile(r"(?i)(ÐºÑ‚Ð¾\s+Ñ‚Ñ‹|Ñ‡Ñ‚Ð¾\s+Ñ‚Ñ‹)\s*[?.!]*\s*$"),
)

_GREETING_PATTERNS = (
    re.compile(r"(?i)^(Ð¿Ñ€Ð¸Ð²ÐµÑ‚|hello|hi|Ñ…Ð°Ð¹|Ñ…ÐµÐ»Ð»Ð¾|Ñ…ÐµÐ¹|Ð·Ð´Ð¾Ñ€Ð¾Ð²Ð¾|Ð·Ð´Ð°Ñ€Ð¾Ð²|Ð¹Ð¾|Ð¹Ð¾Ñƒ|hey)\s*[!.?]*\s*$"),
    re.compile(r"(?i)^(Ð´Ð¾Ð±Ñ€Ñ‹Ð¹\s+(Ð´ÐµÐ½ÑŒ|Ð²ÐµÑ‡ÐµÑ€|ÑƒÑ‚Ñ€Ð¾|Ð½Ð¾Ñ‡ÑŒ))\s*[!.?]*\s*$"),
    re.compile(r"(?i)^(Ð´Ð¾Ð±Ñ€Ð¾Ðµ\s+ÑƒÑ‚Ñ€Ð¾)\s*[!.?]*\s*$"),
    re.compile(r"(?i)^(good\s+(morning|afternoon|evening|night|day))\s*[!.?]*\s*$"),
    re.compile(r"(?i)^(ÑÐ°Ð»ÑŽÑ‚|salut|Ð±Ð¾Ð½Ð¶ÑƒÑ€|Ð±Ð¾Ð½Ð´Ð¶Ð¾Ñ€Ð½Ð¾|Ð³uten)\s*[!.?]*\s*$"),
)

_OFFTOPIC_PATTERNS = (
    re.compile(r"(?i)(ÑˆÑƒÑ‚Ðº|joke|Ð°Ð½ÐµÐºÐ´Ð¾Ñ‚|Ñ€Ð°ÑÑÐ¼ÐµÑˆÐ¸|funny|Ð¿Ð¾ÑÐ¼ÐµÑÑ‚ÑŒÑÑ|Ñ…Ð°Ñ…Ð°Ñ…|ðŸ˜‚|ðŸ¤£|ðŸ˜„)"),
    re.compile(r"(?i)(ÐºÐ°Ðº\s+(Ð´ÐµÐ»Ð°|Ð¶Ð¸Ð·Ð½ÑŒ|Ð½Ð°ÑÑ‚Ñ€Ð¾ÐµÐ½)|how\s+(are\s+you|is\s+it\s+going))"),
    re.compile(r"(?i)(Ð¿Ð¾Ð±Ð¾Ð»Ñ‚Ð°|Ð¿Ð¾Ð³Ð¾Ð²Ð¾Ñ€|Ð´Ð°Ð²Ð°Ð¹\s+Ð¾Ð±Ñ‰Ð°Ñ‚ÑŒ|just\s+chat|small\s+talk)"),
    re.compile(r"(?i)(Ð¿Ð¾Ð¸Ð³Ñ€Ð°|game|Ð¸Ð³Ñ€Ð°Ñ‚ÑŒ|quiz|Ð²Ð¸ÐºÑ‚Ð¾Ñ€Ð¸Ð½)"),
    re.compile(r"(?i)(Ð¿ÐµÑ€ÐµÐ²ÐµÐ´Ð¸|translate|Ð¿ÐµÑ€ÐµÐ²Ð¾Ð´)"),
    re.compile(r"(?i)(Ð½Ð°Ð¿Ð¸ÑˆÐ¸\s+(ÑÑ‚Ð¸Ñ…|Ð¿ÐµÑÐ½|Ð¸ÑÑ‚Ð¾Ñ€Ð¸|Ñ€Ð°ÑÑÐºÐ°Ð·|ÑÑÑÐµ))"),
    re.compile(r"(?i)(write\s+(a\s+)?(poem|song|story|essay))"),
    re.compile(r"(?i)(Ñ€ÐµÑˆÐ¸|solve|Ð¿Ð¾ÑÑ‡Ð¸Ñ‚Ð°Ð¹|calculate|Ð¼Ð°Ñ‚ÐµÐ¼Ð°Ñ‚Ð¸Ðº|math)"),
    re.compile(r"(?i)(Ð¿Ð¾Ñ€ÐµÐºÐ¾Ð¼ÐµÐ½Ð´ÑƒÐ¹|recommend|Ð¿Ð¾ÑÐ¾Ð²ÐµÑ‚ÑƒÐ¹)"),
    re.compile(r"(?i)(Ð¿Ð¾Ð³Ð¾Ð´|weather|ÐºÑƒÑ€Ñ\s+Ð²Ð°Ð»ÑŽÑ‚|exchange\s+rate)"),
    re.compile(r"(?i)(Ñ€Ð°ÑÑÐºÐ°Ð¶Ð¸\s+(Ð¼Ð½Ðµ|Ð½Ð°Ð¼)\s+(Ñ‡Ñ‚Ð¾|Ñ‡Ñ‚Ð¾-Ð½Ð¸Ð±ÑƒÐ´ÑŒ|Ð¸ÑÑ‚Ð¾Ñ€Ð¸ÑŽ))"),
    re.compile(r"(?i)^(Ð¾Ðº|ok|Ð°Ð³Ð°|Ð´Ð°|Ð½ÐµÑ‚|ÑƒÐ³Ñƒ|ÑÐ¿Ð°ÑÐ¸Ð±Ð¾|thanks|ÑÐ¿Ñ|thx)\s*[!.?]*\s*$"),
)


def _matches_any(text: str, patterns: tuple) -> bool:
    for pat in patterns:
        if pat.search(text):
            return True
    return False


def _looks_like_build_request(text: str) -> bool:
    lowered = (text or "").casefold()
    request_markers = (
        "Ð¼Ð½Ðµ Ð½ÑƒÐ¶Ð½Ð¾",
        "Ð¼Ð½Ðµ Ð½Ð°Ð´Ð¾",
        "Ñ…Ð¾Ñ‡Ñƒ ÑÐ´ÐµÐ»Ð°Ñ‚ÑŒ",
        "Ñ…Ð¾Ñ‡Ñƒ ÑÐ¾Ð·Ð´Ð°Ñ‚ÑŒ",
        "Ð½ÑƒÐ¶ÐµÐ½",
        "Ð½ÑƒÐ¶Ð½Ð¾ ÑÐ´ÐµÐ»Ð°Ñ‚ÑŒ",
        "ÑÐ´ÐµÐ»Ð°Ñ‚ÑŒ",
        "ÑÐ¾Ð·Ð´Ð°Ñ‚ÑŒ",
        "Ñ€Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚Ð°Ñ‚ÑŒ",
        "build",
        "make",
        "create",
        "develop",
    )
    target_markers = (
        "ÑÐ°Ð¹Ñ‚",
        "website",
        "bot",
        "Ð±Ð¾Ñ‚",
        "telegram bot",
        "telegram-Ð±Ð¾Ñ‚",
        "telegram bot",
        "Ð»ÐµÐ½Ð´Ð¸Ð½Ð³",
        "landing",
    )
    return any(marker in lowered for marker in request_markers) and any(
        marker in lowered for marker in target_markers
    )


def _looks_like_explicit_link_request(text: str) -> bool:
    lowered = (text or "").casefold()
    request_markers = (
        "Ð³Ð´Ðµ",
        "Ð¿Ð¾ÐºÐ°Ð¶Ð¸",
        "ÑÑÑ‹Ð»ÐºÐ°",
        "ÑÑÑ‹Ð»ÐºÐ¸",
        "link",
        "links",
        "url",
        "where",
        "show",
        "find",
        "look",
        "read",
    )
    target_markers = (
        "ÑÐ°Ð¹Ñ‚",
        "website",
        "portfolio",
        "Ð¿Ð¾Ñ€Ñ‚Ñ„Ð¾Ð»Ð¸Ð¾",
        "github",
        "telegram",
        "repo",
        "Ñ€ÐµÐ¿Ð¾",
        "ÐºÐ¾Ð´",
        "channel",
        "ÐºÐ°Ð½Ð°Ð»",
    )
    return any(marker in lowered for marker in request_markers) and any(
        marker in lowered for marker in target_markers
    )


def _looks_like_generic_site_mention(text: str) -> bool:
    lowered = (text or "").casefold()
    if not any(marker in lowered for marker in ("ÑÐ°Ð¹Ñ‚", "site", "website")):
        return False
    if _looks_like_build_request(text) or _looks_like_explicit_link_request(text):
        return False
    if any(
        marker in lowered
        for marker in ("github", "telegram", "portfolio", "Ð¿Ð¾Ñ€Ñ‚Ñ„Ð¾Ð»Ð¸Ð¾", "http", "t.me")
    ):
        return False
    return True


def classify_topic(text: str) -> TopicCategory:
    """Classify visitor message into a topic category.
    Order matters â€” more specific patterns first."""
    if not text or not text.strip():
        return TopicCategory.DISALLOWED_OFFTOPIC

    # Use normalized text for safety checks to prevent unicode bypass
    normalized = _normalize_unicode(text)

    # Safety first (check BOTH original and normalized to catch Cyrillic + Latin bypasses)
    if _matches_any(text, _INJECTION_PATTERNS) or _matches_any(normalized, _INJECTION_PATTERNS):
        return TopicCategory.DISALLOWED_INTERNAL

    if _matches_any(text, _INTERNAL_PATTERNS) or _matches_any(normalized, _INTERNAL_PATTERNS):
        return TopicCategory.DISALLOWED_ADMIN

    # Greeting â€” short hello messages
    if _matches_any(text, _GREETING_PATTERNS):
        return TopicCategory.GREETING

    # Project-specific question (before general technical)
    if _matches_any(text, _PROJECT_SPECIFIC_PATTERNS):
        return TopicCategory.PROJECT_SPECIFIC_QUESTION

    # General technical question
    if _matches_any(text, _TECHNICAL_PATTERNS):
        return TopicCategory.TECHNICAL_QUESTION

    # Topic categories
    if _looks_like_build_request(text):
        return TopicCategory.COLLABORATION

    if _matches_any(text, _ASSISTANT_PATTERNS):
        return TopicCategory.ASSISTANT_CAPABILITIES

    if (
        (_matches_any(text, _LINKS_PATTERNS) or _looks_like_explicit_link_request(text))
        and not _looks_like_generic_site_mention(text)
    ):
        return TopicCategory.LINKS

    if _matches_any(text, _COLLABORATION_PATTERNS):
        return TopicCategory.COLLABORATION

    if _matches_any(text, _PROJECTS_PATTERNS):
        return TopicCategory.ABOUT_PROJECTS

    if _matches_any(text, _OWNER_PATTERNS):
        return TopicCategory.ABOUT_OWNER

    if _matches_any(text, _FAQ_PATTERNS):
        return TopicCategory.FAQ

    # Everything else goes to AI â€” AI decides how to handle (answer or redirect)
    return TopicCategory.GENERAL


# Allowed categories
_ALLOWED_CATEGORIES = {
    TopicCategory.ABOUT_OWNER,
    TopicCategory.ABOUT_PROJECTS,
    TopicCategory.TECHNICAL_QUESTION,
    TopicCategory.PROJECT_SPECIFIC_QUESTION,
    TopicCategory.FAQ,
    TopicCategory.COLLABORATION,
    TopicCategory.LINKS,
    TopicCategory.ASSISTANT_CAPABILITIES,
    TopicCategory.GREETING,
    TopicCategory.GENERAL,
}

_REDIRECT_MESSAGES = {
    TopicCategory.DISALLOWED_OFFTOPIC: (
        "Ð¯ ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸Ð¾Ð½Ð½Ñ‹Ð¹ Ð¿Ð¾Ð¼Ð¾Ñ‰Ð½Ð¸Ðº Ð¸ Ð¼Ð¾Ð³Ñƒ Ñ€Ð°ÑÑÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð¾ ProjectOwner, "
        "ÐµÐ³Ð¾ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ…, Ñ‚ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸ÑÑ…, ÑÑÑ‹Ð»ÐºÐ°Ñ… Ð¸ ÑÐ¾Ñ‚Ñ€ÑƒÐ´Ð½Ð¸Ñ‡ÐµÑÑ‚Ð²Ðµ.\n"
        "ÐœÐ¾Ð³Ñƒ Ñ‚Ð°ÐºÐ¶Ðµ Ð¾Ð±ÑŠÑÑÐ½Ð¸Ñ‚ÑŒ Ñ‚ÐµÑ…Ð½Ð¸Ñ‡ÐµÑÐºÐ¸Ðµ Ð¿Ð¾Ð½ÑÑ‚Ð¸Ñ. "
        "Ð—Ð°Ð´Ð°Ð¹Ñ‚Ðµ Ð²Ð¾Ð¿Ñ€Ð¾Ñ Ð¿Ð¾ Ð¾Ð´Ð½Ð¾Ð¹ Ð¸Ð· ÑÑ‚Ð¸Ñ… Ñ‚ÐµÐ¼."
    ),
    TopicCategory.DISALLOWED_INTERNAL: (
        "Ð¯ Ð½Ðµ Ð¼Ð¾Ð³Ñƒ Ñ€Ð°ÑÐºÑ€Ñ‹Ð²Ð°Ñ‚ÑŒ Ð²Ð½ÑƒÑ‚Ñ€ÐµÐ½Ð½Ð¸Ðµ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ð¸Ð»Ð¸ ÑÐ¸ÑÑ‚ÐµÐ¼Ð½Ñ‹Ðµ Ð¸Ð½ÑÑ‚Ñ€ÑƒÐºÑ†Ð¸Ð¸. "
        "Ð¡Ð¿Ñ€Ð¾ÑÐ¸Ñ‚Ðµ Ð¾ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ…, Ñ‚ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸ÑÑ… Ð¸Ð»Ð¸ ÑÐ¾Ñ‚Ñ€ÑƒÐ´Ð½Ð¸Ñ‡ÐµÑÑ‚Ð²Ðµ."
    ),
    TopicCategory.DISALLOWED_ADMIN: (
        "Ð£ Ð¼ÐµÐ½Ñ Ð½ÐµÑ‚ Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð° Ðº Ð°Ð´Ð¼Ð¸Ð½-Ñ„ÑƒÐ½ÐºÑ†Ð¸ÑÐ¼. "
        "Ð¯ Ð¿ÑƒÐ±Ð»Ð¸Ñ‡Ð½Ñ‹Ð¹ ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ð½Ñ‚ â€” Ð¼Ð¾Ð³Ñƒ Ñ€Ð°ÑÑÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð¾ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ… Ð¸ Ñ‚ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸ÑÑ…."
    ),
    TopicCategory.DISALLOWED_PRIVATE: (
        "Ð­Ñ‚Ð° Ð¸Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸Ñ Ð¿Ñ€Ð¸Ð²Ð°Ñ‚Ð½Ð°. "
        "Ð¯ Ð¼Ð¾Ð³Ñƒ Ñ€Ð°ÑÑÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð¾ Ð¿ÑƒÐ±Ð»Ð¸Ñ‡Ð½Ñ‹Ñ… Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ… Ð¸ Ñ‚ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸ÑÑ…."
    ),
}


def evaluate_message(text: str) -> PolicyDecision:
    """Evaluate visitor message against policy."""
    category = classify_topic(text)
    allowed = category in _ALLOWED_CATEGORIES
    redirect = _REDIRECT_MESSAGES.get(category) if not allowed else None
    return PolicyDecision(allowed=allowed, category=category, redirect_message=redirect)


def classify_visitor_query(text: str) -> TopicCategory:
    """Public API: classify visitor query into category.
    Used by visitor_service for smart routing."""
    return classify_topic(text)

