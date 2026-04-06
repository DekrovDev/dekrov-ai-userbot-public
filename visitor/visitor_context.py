from __future__ import annotations

import logging
import re

LOGGER = logging.getLogger("assistant.visitor.context")


# ========================
# SECTION-BASED FILTERING
# For knowledge that uses markdown headers (# Section)
# ========================

_PRIVATE_SECTION_MARKERS = (
    "## about assistant-ai",
    "## private",
    "## owner only",
    "## overview",
    "## command prefixes",
    "## all key files",
    "## environment",
    "## .env variables",
    "## json data files",
)

_PUBLIC_SECTION_MARKERS = (
    "# identity",
    "# websites",
    "# telegram",
    "# contacts",
    "# interests",
    "# technical environment",
    "# development",
    "# internet activity",
    "# personal traits",
)


# ========================
# LINE-BASED FILTERING
# For flat knowledge lists (bullet points without headers)
# Patterns that match lines containing private/internal info
# ========================

_PRIVATE_LINE_PATTERNS = (
    # Bot architecture
    re.compile(r"(?i)(userbot|pyrogram|chatbot|controlbot|systemd|ubuntu\s+vps)"),
    re.compile(r"(?i)(groq\s+api|multi.model|fallback|judge\s+system)"),
    re.compile(r"(?i)(three\s+component|runs\s+simultaneously|bot\s+account)"),
    re.compile(r"(?i)(data/\s+directory|state\.json|user_profile|entity_memory|style_profile)"),
    re.compile(r"(?i)(\.env\s+file|GROQ_API_KEY|OWNER_USER_ID|API_ID|API_HASH|BOT_TOKEN)"),
    re.compile(r"(?i)(command\s+prefix|trigger.*ai|\.[Ð´d]\s+\(or|\.chat|\.talk|\.ask)"),
    re.compile(r"(?i)(dialogue\s+mode|owner\s+only.*refusal|available\s+to.*owner)"),
    re.compile(r"(?i)(powered\s+by\s+groq|python\s+3\.\d|three\s+prefix)"),
    re.compile(r"(?i)assistant.ai\s+is\s+a\s+telegram"),
    re.compile(r"(?i)(config\s+via|stored\s+in\s+data)"),
)


def _is_private_line(line: str) -> bool:
    """Return True if line contains private/internal information."""
    return any(pat.search(line) for pat in _PRIVATE_LINE_PATTERNS)


def build_safe_visitor_context(raw_knowledge: str) -> str:
    """Extract only public-safe data from owner knowledge.

    Handles two knowledge formats:
    1. Section-based (markdown headers) â€” filters by section name
    2. Flat list (bullet points) â€” filters line by line using content patterns

    Always strips internal architecture, config, bot internals.
    """
    if not raw_knowledge or not raw_knowledge.strip():
        return ""

    lines = raw_knowledge.splitlines()
    safe_lines: list[str] = []
    in_private_section = False
    has_section_headers = any(
        line.strip().lower().startswith(("#", "##"))
        for line in lines
        if line.strip()
    )

    for raw_line in lines:
        lower = raw_line.strip().lower()

        if has_section_headers:
            # Section-based filtering
            if any(lower.startswith(s) for s in _PUBLIC_SECTION_MARKERS):
                in_private_section = False
                safe_lines.append(raw_line)
                continue
            if any(lower.startswith(marker) for marker in _PRIVATE_SECTION_MARKERS):
                in_private_section = True
                continue
            if in_private_section:
                continue
            safe_lines.append(raw_line)
        else:
            # Flat list â€” filter line by line
            if _is_private_line(raw_line):
                continue
            safe_lines.append(raw_line)

    result = "\n".join(safe_lines).strip()
    return result


def format_knowledge_for_prompt(knowledge: str) -> str:
    """Format cleaned knowledge for LLM prompt."""
    if not knowledge:
        return ""
    return (
        "Ð”ÐÐÐÐ«Ð• Ðž Ð’Ð›ÐÐ”Ð•Ð›Ð¬Ð¦Ð• (Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐ¹ Ð¢ÐžÐ›Ð¬ÐšÐž ÑÑ‚Ð¾, Ð½Ðµ Ð²Ñ‹Ð´ÑƒÐ¼Ñ‹Ð²Ð°Ð¹):\n\n"
        + knowledge
        + "\n\nÐšÐžÐÐ•Ð¦ Ð”ÐÐÐÐ«Ð¥."
    )

