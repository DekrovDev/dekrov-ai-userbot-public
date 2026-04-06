"""ÐŸÐ°Ñ€ÑÐ¸Ð½Ð³ Ð¸ Ð¿Ñ€Ð¾Ð²ÐµÑ€ÐºÐ° ÐºÐ¾Ð¼Ð°Ð½Ð´ userbot.

ÐžÐ¿Ñ€ÐµÐ´ÐµÐ»ÐµÐ½Ð¸Ðµ Ð¿Ñ€ÐµÑ„Ð¸ÐºÑÐ¾Ð² ÐºÐ¾Ð¼Ð°Ð½Ð´, Ð¿Ð¾Ð´Ñ‚Ð²ÐµÑ€Ð¶Ð´ÐµÐ½Ð¸Ð¹, ÑÑ‚Ð¾Ð¿-ÑÐ¸Ð³Ð½Ð°Ð»Ð¾Ð².
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from state.state import PersistentState


# ÐŸÑ€ÐµÑ„Ð¸ÐºÑÑ‹ ÐºÐ¾Ð¼Ð°Ð½Ð´: Ð¿Ñ€ÐµÑ„Ð¸ÐºÑ â†’ Ñ€ÐµÐ¶Ð¸Ð¼
COMMAND_PREFIXES = {
    ".Ð´": "dialogue",
    ".Ðº": "command",
    ".Ð±": "bot",
    ".d": "dialogue",
    ".k": "command",
    ".b": "bot",
    ".ai": "bot",
    ".bot": "bot",
    ".tg": "command",
    ".cmd": "command",
    ".chat": "dialogue",
    ".talk": "dialogue",
    ".ask": "dialogue",
    ".do": "command",
    ".action": "command",
    ".search": "bot",
    ".find": "bot",
    ".text": "bot",
}

# Ð¡Ñ‚Ð¾Ð¿-ÐºÐ¾Ð¼Ð°Ð½Ð´Ñ‹
STOP_COMMANDS = {
    "ÑÑ‚Ð¾Ð¿",
    ".ÑÑ‚Ð¾Ð¿",
    "stop",
    ".stop",
    "Ð¾Ñ‚Ð¼ÐµÐ½Ð°",
    ".Ð¾Ñ‚Ð¼ÐµÐ½Ð°",
    "cancel",
    ".cancel",
    "Ñ…Ð²Ð°Ñ‚Ð¸Ñ‚",
    ".Ð´ ÑÑ‚Ð¾Ð¿",
    ".d stop",
    ".assistant stop",
    ".assistant ÑÑ‚Ð¾Ð¿",
}

# ÐŸÐ¾Ð´Ñ‚Ð²ÐµÑ€Ð¶Ð´ÐµÐ½Ð¸Ñ
CONFIRM_PHRASES = {"Ð´", "Ð´Ð°", "y", "yes"}
REJECT_PHRASES = {"Ð½", "Ð½ÐµÑ‚", "n", "no"}

# ÐœÐµÑ‚Ð°-Ð²Ð¾Ð¿Ñ€Ð¾ÑÑ‹ Ð¾ Ñ€ÐµÐ¶Ð¸Ð¼Ð°Ñ…
META_QUESTION_PATTERNS = (
    r"(?iu)\b(?:Ñ‡Ñ‚Ð¾|Ñ‡Ñ‚Ð¾\s+Ñ‚Ð°ÐºÐ¾Ðµ|Ñ‡Ñ‚Ð¾\s+Ð·Ð½Ð°Ñ‡Ð¸Ñ‚|Ð·Ð°Ñ‡ÐµÐ¼\s+Ð½ÑƒÐ¶[ÐµÐ½Ð°Ð¾]?)\s+\.(?:Ðº|k)\b",
    r"(?iu)\b(?:Ñ‡Ñ‚Ð¾|Ñ‡Ñ‚Ð¾\s+Ñ‚Ð°ÐºÐ¾Ðµ|Ñ‡Ñ‚Ð¾\s+Ð·Ð½Ð°Ñ‡Ð¸Ñ‚|Ð·Ð°Ñ‡ÐµÐ¼\s+Ð½ÑƒÐ¶[ÐµÐ½Ð°Ð¾]?)\s+\.(?:Ð´|d)\b",
    r"(?iu)\b(?:Ð²\s+Ñ‡ÐµÐ¼\s+Ñ€Ð°Ð·Ð½Ð¸Ñ†Ð°|difference\s+between)\s+\.(?:Ð´|d)\s+(?:Ð¸|and)\s+\.(?:Ðº|k)\b",
    r"(?iu)\bwhat\s+is\s+\.(?:k|d)\b",
    r"(?iu)\bwhat\s+does\s+\.(?:k|d)\s+mean\b",
    r"(?iu)\bwhy\s+do\s+i\s+need\s+\.(?:k|d)\b",
)


def extract_prompt(text: str, snapshot: PersistentState) -> str | None:
    """Ð˜Ð·Ð²Ð»ÐµÑ‡ÑŒ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚ Ð¸Ð· Ñ‚ÐµÐºÑÑ‚Ð° ÐºÐ¾Ð¼Ð°Ð½Ð´Ñ‹.

    Args:
        text: Ð˜ÑÑ…Ð¾Ð´Ð½Ñ‹Ð¹ Ñ‚ÐµÐºÑÑ‚ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ
        snapshot: Ð¢ÐµÐºÑƒÑ‰ÐµÐµ ÑÐ¾ÑÑ‚Ð¾ÑÐ½Ð¸Ðµ ÑÐ¸ÑÑ‚ÐµÐ¼Ñ‹

    Returns:
        ÐŸÑ€Ð¾Ð¼Ð¿Ñ‚ Ð¿Ð¾ÑÐ»Ðµ Ð¿Ñ€ÐµÑ„Ð¸ÐºÑÐ° ÐºÐ¾Ð¼Ð°Ð½Ð´Ñ‹ Ð¸Ð»Ð¸ None
    """
    stripped = text.lstrip()
    lowered = stripped.casefold()

    for alias in snapshot.trigger_aliases:
        variants = [f".{alias}"]
        if not snapshot.dot_prefix_required:
            variants.append(alias)

        for variant in variants:
            candidate = variant.casefold()
            if not lowered.startswith(candidate):
                continue
            if (
                len(stripped) > len(variant)
                and not stripped[len(variant)].isspace()
            ):
                continue
            return stripped[len(variant) :].strip()

    return None


def looks_like_command_trigger(text: str, snapshot: PersistentState) -> bool:
    """ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ, Ð²Ñ‹Ð³Ð»ÑÐ´Ð¸Ñ‚ Ð»Ð¸ Ñ‚ÐµÐºÑÑ‚ ÐºÐ°Ðº ÐºÐ¾Ð¼Ð°Ð½Ð´Ð°.

    Args:
        text: Ð¢ÐµÐºÑÑ‚ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ
        snapshot: Ð¢ÐµÐºÑƒÑ‰ÐµÐµ ÑÐ¾ÑÑ‚Ð¾ÑÐ½Ð¸Ðµ ÑÐ¸ÑÑ‚ÐµÐ¼Ñ‹

    Returns:
        True ÐµÑÐ»Ð¸ Ñ‚ÐµÐºÑÑ‚ Ð¿Ð¾Ñ…Ð¾Ð¶ Ð½Ð° ÐºÐ¾Ð¼Ð°Ð½Ð´Ñƒ
    """
    return extract_prompt(text, snapshot) is not None


def extract_prefixed_mode_prompt(text: str) -> tuple[str, str, bool] | None:
    """Ð˜Ð·Ð²Ð»ÐµÑ‡ÑŒ Ñ€ÐµÐ¶Ð¸Ð¼ Ð¸ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚ Ð¸Ð· Ð¿Ñ€ÐµÑ„Ð¸ÐºÑÐ° ÐºÐ¾Ð¼Ð°Ð½Ð´Ñ‹.

    Args:
        text: Ð¢ÐµÐºÑÑ‚ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ

    Returns:
        ÐšÐ¾Ñ€Ñ‚ÐµÐ¶ (mode, prompt, delete_after) Ð¸Ð»Ð¸ None
    """
    stripped = (text or "").lstrip()
    lowered = stripped.casefold()

    for prefix, mode in COMMAND_PREFIXES.items():
        if not lowered.startswith(prefix):
            continue
        rest = stripped[len(prefix) :]

        # ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ñ„Ð»Ð°Ð³Ð° ÑƒÐ´Ð°Ð»ÐµÐ½Ð¸Ñ (Ð´Ð²Ð¾Ð¹Ð½Ð¾Ð¹ Ð¿Ñ€ÐµÑ„Ð¸ÐºÑ)
        delete_after = False
        if rest and not rest[0].isspace():
            extra = rest[0]
            remainder = rest[1:]
            if extra == "." or extra.casefold() == prefix[-1].casefold():
                if not remainder or remainder[0].isspace():
                    delete_after = True
                    rest = remainder
                else:
                    continue
            else:
                continue
        return mode, rest.strip(), delete_after

    return None


def parse_action_confirmation(text: str) -> tuple[str, str] | None:
    """Ð Ð°ÑÐ¿Ð°Ñ€ÑÐ¸Ñ‚ÑŒ Ð¿Ð¾Ð´Ñ‚Ð²ÐµÑ€Ð¶Ð´ÐµÐ½Ð¸Ðµ Ð´ÐµÐ¹ÑÑ‚Ð²Ð¸Ñ (Ð”/Ð).

    Args:
        text: Ð¢ÐµÐºÑÑ‚ Ð¾Ñ‚Ð²ÐµÑ‚Ð°

    Returns:
        ÐšÐ¾Ñ€Ñ‚ÐµÐ¶ (action, value) Ð¸Ð»Ð¸ None
    """
    normalized = " ".join((text or "").strip().casefold().split())
    if normalized in CONFIRM_PHRASES:
        return "confirm_latest", ""
    if normalized in REJECT_PHRASES:
        return "reject_latest", ""
    return None


def is_owner_stop_request(text: str) -> bool:
    """ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ, ÑÐ²Ð»ÑÐµÑ‚ÑÑ Ð»Ð¸ Ñ‚ÐµÐºÑÑ‚ ÑÑ‚Ð¾Ð¿-ÐºÐ¾Ð¼Ð°Ð½Ð´Ð¾Ð¹ Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ð°.

    Args:
        text: Ð¢ÐµÐºÑÑ‚ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ

    Returns:
        True ÐµÑÐ»Ð¸ ÑÑ‚Ð¾ ÑÑ‚Ð¾Ð¿-ÐºÐ¾Ð¼Ð°Ð½Ð´Ð°
    """
    normalized = " ".join((text or "").strip().casefold().split())
    if not normalized:
        return False
    return normalized in STOP_COMMANDS


def is_mode_meta_question(prompt: str) -> bool:
    """ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ, ÑÐ²Ð»ÑÐµÑ‚ÑÑ Ð»Ð¸ Ð²Ð¾Ð¿Ñ€Ð¾Ñ Ð¼ÐµÑ‚Ð°-Ð²Ð¾Ð¿Ñ€Ð¾ÑÐ¾Ð¼ Ð¾ Ñ€ÐµÐ¶Ð¸Ð¼Ð°Ñ….

    Args:
        prompt: Ð¢ÐµÐºÑÑ‚ Ð¿Ñ€Ð¾Ð¼Ð¿Ñ‚Ð°

    Returns:
        True ÐµÑÐ»Ð¸ ÑÑ‚Ð¾ Ð¼ÐµÑ‚Ð°-Ð²Ð¾Ð¿Ñ€Ð¾Ñ Ð¾ .Ð´/.Ðº
    """
    normalized = " ".join((prompt or "").strip().casefold().split())
    if not normalized:
        return False
    return any(
        re.search(pattern, normalized) for pattern in META_QUESTION_PATTERNS
    )


def looks_like_owner_operational_storage_action(lowered: str) -> bool:
    """ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ, Ð¿Ð¾Ñ…Ð¾Ð¶Ðµ Ð»Ð¸ Ð½Ð° Ð¾Ð¿ÐµÑ€Ð°Ñ†Ð¸ÑŽ Ñ Ñ…Ñ€Ð°Ð½Ð¸Ð»Ð¸Ñ‰ÐµÐ¼.

    Args:
        lowered: Ð¢ÐµÐºÑÑ‚ Ð² Ð½Ð¸Ð¶Ð½ÐµÐ¼ Ñ€ÐµÐ³Ð¸ÑÑ‚Ñ€Ðµ

    Returns:
        True ÐµÑÐ»Ð¸ Ð¿Ð¾Ñ…Ð¾Ð¶Ðµ Ð½Ð° Ð¾Ð¿ÐµÑ€Ð°Ñ†Ð¸ÑŽ Ñ Ñ…Ñ€Ð°Ð½Ð¸Ð»Ð¸Ñ‰ÐµÐ¼
    """
    storage_keywords = (
        "ÑÐ¾Ñ…Ñ€Ð°Ð½Ð¸",
        "Ð·Ð°Ð¿Ð¾Ð¼Ð½Ð¸",
        "Ð·Ð°Ð¿Ð¸ÑˆÐ¸",
        "Ð´Ð¾Ð±Ð°Ð²ÑŒ",
        "ÑƒÐ´Ð°Ð»Ð¸",
        "ÑƒÐ±ÐµÑ€Ð¸",
        "Ð¾Ñ‡Ð¸ÑÑ‚Ð¸",
        "ÑÐ±Ñ€Ð¾Ñ",
        "reset",
        "save",
        "remember",
        "store",
        "add",
        "remove",
        "clear",
    )
    return any(kw in lowered for kw in storage_keywords)


def looks_like_owner_operational_storage_action_modern(lowered: str) -> bool:
    """ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ Ð½Ð° ÑÐ¾Ð²Ñ€ÐµÐ¼ÐµÐ½Ð½ÑƒÑŽ Ð¾Ð¿ÐµÑ€Ð°Ñ†Ð¸ÑŽ Ñ Ñ…Ñ€Ð°Ð½Ð¸Ð»Ð¸Ñ‰ÐµÐ¼.

    Args:
        lowered: Ð¢ÐµÐºÑÑ‚ Ð² Ð½Ð¸Ð¶Ð½ÐµÐ¼ Ñ€ÐµÐ³Ð¸ÑÑ‚Ñ€Ðµ

    Returns:
        True ÐµÑÐ»Ð¸ Ð¿Ð¾Ñ…Ð¾Ð¶Ðµ Ð½Ð° ÑÐ¾Ð²Ñ€ÐµÐ¼ÐµÐ½Ð½ÑƒÑŽ Ð¾Ð¿ÐµÑ€Ð°Ñ†Ð¸ÑŽ
    """
    modern_patterns = (
        r"(?iu)\b(?:ÑÐ¾Ñ…Ñ€Ð°Ð½Ð¸|Ð·Ð°Ð¿Ð¾Ð¼Ð½Ð¸|Ð·Ð°Ð¿Ð¸ÑˆÐ¸)\s+Ð²\s+Ð¿Ð°Ð¼ÑÑ‚ÑŒ\b",
        r"(?iu)\b(?:Ð´Ð¾Ð±Ð°Ð²ÑŒ|ÑÐ¾Ð·Ð´Ð°Ð¹)\s+(?:Ñ„Ð°ÐºÑ‚|Ð·Ð°Ð¿Ð¸ÑÑŒ)\b",
        r"(?iu)\b(?:Ð¾Ñ‡Ð¸ÑÑ‚Ð¸|ÑÐ±Ñ€Ð¾ÑÑŒ|reset)\s+(?:Ð¿Ð°Ð¼ÑÑ‚ÑŒ|ÐºÐµÑˆ|cache)\b",
        r"(?iu)\b(?:show|list|Ð¿Ð¾ÐºÐ°Ð¶Ð¸)\s+(?:facts|memory|Ð¿Ð°Ð¼ÑÑ‚ÑŒ)\b",
    )
    return any(re.search(pattern, lowered) for pattern in modern_patterns)

