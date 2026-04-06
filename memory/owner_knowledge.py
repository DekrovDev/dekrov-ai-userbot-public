from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from infra.json_atomic import atomic_write_text_sync


DEFAULT_OWNER_KNOWLEDGE = """# Owner Knowledge

Put persistent facts here that Project Assistant should always consider.

Examples:
- Portfolio: https://example.com
- This is the project owner's public portfolio site.
- Preferred nickname: Project Owner
- Main Telegram channel: https://t.me/example_channel

Notes:
- Keep only stable useful information here.
- One fact per line is best.
- Lines starting with # are ignored.
"""

OWNER_PROMPT_MAX_LINES = 420
OWNER_PROMPT_MAX_CHARS = 32000
OWNER_SELECTIVE_BASE_MAX_LINES = 80
OWNER_SELECTIVE_BASE_MAX_CHARS = 2200
OWNER_SELECTIVE_TOPIC_MAX_LINES = 220
OWNER_SELECTIVE_TOPIC_MAX_CHARS = 9000
OWNER_SELECTIVE_DEEP_MAX_LINES = 320
OWNER_SELECTIVE_DEEP_MAX_CHARS = 14000
INTERNAL_PATH_PATTERNS = (
    "c:\\",
    "/opt/",
    ".py",
    ".json",
    ".env",
    ".session",
    "app/",
    "ai/",
    "live/",
    "memory/",
    "state/",
    "visitor/",
    "infra/",
    "data/",
)

PUBLIC_PROFILE_HEADINGS = {
    "identity",
    "websites",
    "telegram",
    "contacts",
    "technical environment",
    "development",
    "public positioning",
    "internet activity",
    "personal traits",
}
OWNER_FOUNDATION_HEADINGS = {
    "owner quick reference for .b mode",
    "mode map for the owner",
    "what .b should know about itself",
    'how to answer "how do i do this in the bot?"',
    "common owner questions and best paths",
    "transcription quick reference",
    "answer style inside .b",
    "where to change things",
    "how .b should answer deep internal questions",
}
TOPIC_HEADING_MAP = {
    "commands": {
        "mode map for the owner",
        "command prefixes",
        "telegram actions (.Ðº commands)",
        "cross-chat actions (.Ðº cross_chat_request)",
        "how to do common things",
        "common owner questions and best paths",
    },
    "architecture": {
        "internal architecture map",
        "service wiring and startup",
        "component map by responsibility",
        "action execution stack",
        "overview",
        "message processing flow (owner)",
        "message processing flow (auto-reply)",
    },
    "auto_reply": {
        "auto-reply system map",
        "auto-reply system",
        "special targets, close contacts, and directives",
        "special targets",
        "close contacts",
        "owner directives",
        "silence engine",
        "response modes",
        "response style modes",
    },
    "chat_bot": {
        "chat bot access and visitor relationship",
        "chat bot (separate bot account)",
        "control bot panel",
        "control bot panel map",
        "control bot panel (detailed)",
    },
    "visitor": {
        "visitor system map",
        "chat bot access and visitor relationship",
        "chat bot (separate bot account)",
    },
    "models": {
        "model, fallback, and judge system",
        "groq api & model system",
        "judge system",
        "model stats & performance tracking",
        "validator (output quality)",
    },
    "memory": {
        "memory and profile systems",
        "memory systems",
        "history search",
        "memory commands",
        "draft system",
        "style mirroring",
    },
    "media": {
        "transcription quick reference",
        "media, transcription, and vision",
        "vision",
        "formatting",
    },
    "live_tools": {
        "live tools and grounding",
        "web search & live data",
        "web grounding (auto)",
        "live data tools",
    },
    "monitoring": {
        "scheduler and monitoring",
        "monitoring (keyword monitor)",
        "scheduler (persistent timers)",
    },
    "storage": {
        "global state and what it controls",
        "storage and important data files",
        "environment & deployment",
        ".env variables",
        "json data files",
    },
    "debug": {
        'how to debug "why did the bot do that?"',
        "where to change things",
        "validator (output quality)",
        "model stats & performance tracking",
    },
    "owner_profile": PUBLIC_PROFILE_HEADINGS,
}
TOPIC_QUERY_MARKERS = {
    "commands": (
        ".Ð±",
        ".Ðº",
        ".Ð´",
        "ÐºÐ¾Ð¼Ð°Ð½Ð´",
        "Ñ€ÐµÐ¶Ð¸Ð¼",
        "prefix",
        "Ð¿Ñ€ÐµÑ„Ð¸ÐºÑ",
        "ÐºÐ°Ðº Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÑŒÑÑ",
        "Ñ‡ÐµÐ¼ Ð¾Ñ‚Ð»Ð¸Ñ‡Ð°ÐµÑ‚ÑÑ",
    ),
    "architecture": (
        "ÐºÐ°Ðº ÑƒÑÑ‚Ñ€Ð¾ÐµÐ½",
        "ÐºÐ°Ðº Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÑ‚",
        "Ð¸Ð· Ñ‡ÐµÐ³Ð¾ ÑÐ¾ÑÑ‚Ð¾Ð¸Ñ‚",
        "Ð°Ñ€Ñ…Ð¸Ñ‚ÐµÐºÑ‚ÑƒÑ€",
        "pipeline",
        "flow",
        "wiring",
        "routing",
        "service",
    ),
    "auto_reply": (
        "auto-reply",
        "auto reply",
        "Ð°Ð²Ñ‚Ð¾Ð¾Ñ‚Ð²ÐµÑ‚",
        "Ð°Ð²Ñ‚Ð¾-Ð¾Ñ‚Ð²ÐµÑ‚",
        "cooldown",
        "reply_probability",
        "special target",
        "owner directive",
    ),
    "chat_bot": (
        "chat bot",
        "chatbot",
        "Ñ‡Ð°Ñ‚ Ð±Ð¾Ñ‚",
        "whitelist",
        "visitor mode",
        "control bot",
        "ÐºÐ¾Ð½Ñ‚Ñ€Ð¾Ð» Ð±Ð¾Ñ‚",
        "Ð°Ð´Ð¼Ð¸Ð½",
        "Ð°Ð´Ð¼Ð¸Ð½ÐºÐ°",
    ),
    "visitor": (
        "visitor",
        "Ð²Ð¸Ð·Ð¸Ñ‚Ð¾Ñ€",
        "ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†",
        "Ð¿Ð¾ÑÐµÑ‚Ð¸Ñ‚ÐµÐ»",
        "public bot",
    ),
    "models": (
        "judge",
        "ÑÑƒÐ´ÑŒÑ",
        "fallback",
        "model",
        "Ð¼Ð¾Ð´ÐµÐ»",
        "groq",
        "validator",
        "latency",
        "Ð·Ð°Ð´ÐµÑ€Ð¶",
        "Ð´Ð¾Ð»Ð³Ð¾ Ð¾Ñ‚Ð²ÐµÑ‡Ð°ÐµÑ‚",
    ),
    "memory": (
        "memory",
        "Ð¿Ð°Ð¼ÑÑ‚ÑŒ",
        "entity memory",
        "shared memory",
        "history",
        "Ð¸ÑÑ‚Ð¾Ñ€Ð¸",
        "draft",
        "profile",
        "ÐºÐ¾Ð½Ñ‚ÐµÐºÑÑ‚",
    ),
    "media": (
        "transcription",
        "Ñ‚Ñ€Ð°Ð½ÑÐºÑ€Ð¸Ð¿",
        "voice",
        "Ð³Ð¾Ð»Ð¾ÑÐ¾Ð²",
        "vision",
        "photo",
        "Ð¸Ð·Ð¾Ð±Ñ€Ð°Ð¶ÐµÐ½",
        "Ð°ÑƒÐ´Ð¸Ð¾",
    ),
    "live_tools": (
        "Ð¸Ð½Ñ‚ÐµÑ€Ð½ÐµÑ‚",
        "web",
        "search",
        "Ð¿Ð¾Ð¸ÑÐº",
        "live data",
        "grounding",
        "fresh",
        "ÑÐ²ÐµÐ¶",
        "Ð°ÐºÑ‚ÑƒÐ°Ð»",
    ),
    "monitoring": (
        "monitor",
        "Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€",
        "scheduler",
        "Ñ€Ð°ÑÐ¿Ð¸ÑÐ°Ð½",
        "Ñ‚Ð°Ð¹Ð¼ÐµÑ€",
        "Ð½Ð°Ð¿Ð¾Ð¼Ð¸Ð½Ð°Ð½",
    ),
    "storage": (
        "storage",
        "state",
        "config",
        "Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹",
        "Ð¿ÐµÑ€ÐµÐ¼ÐµÐ½Ð½",
        "json",
        "env",
        "Ð´Ð°Ð½Ð½Ñ‹",
    ),
    "debug": (
        "Ð¿Ð¾Ñ‡ÐµÐ¼Ñƒ",
        "why",
        "Ð½Ðµ Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÑ‚",
        "Ð¾ÑˆÐ¸Ð±Ðº",
        "debug",
        "Ð»Ð¾Ð³",
        "Ñ‡Ñ‚Ð¾ Ð¾Ñ‚Ð²ÐµÑ‡Ð°ÐµÑ‚",
        "Ð³Ð´Ðµ Ð¼ÐµÐ½ÑÑ‚ÑŒ",
    ),
    "owner_profile": (
        "assistant",
        "Ð²Ð»Ð°Ð´ÐµÐ»",
        "ÑÐ¾Ð·Ð´Ð°Ñ‚ÐµÐ»",
        "creator",
        "owner",
        "ÐºÐ¾Ð½Ñ‚Ð°ÐºÑ‚",
        "portfolio",
        "Ð¿Ð¾Ñ€Ñ‚Ñ„Ð¾Ð»Ð¸Ð¾",
        "github",
        "telegram",
    ),
}
INTERNAL_HARD_MARKERS = (
    "Ð² ÑÑ‚Ð¾Ð¼ Ð±Ð¾Ñ‚Ðµ",
    "Ð² ÑÑ‚Ð¾Ð¼ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ðµ",
    "ÑÑ‚Ð¾Ñ‚ Ð±Ð¾Ñ‚",
    "ÑÑ‚Ð¾Ñ‚ Ð¿Ñ€Ð¾ÐµÐºÑ‚",
    "inside the bot",
    "inside this bot",
    "inside this project",
    "how does the bot work",
    "ÐºÐ°Ðº ÑƒÑÑ‚Ñ€Ð¾ÐµÐ½",
    "ÐºÐ°Ðº Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÑ‚",
    "Ð¸Ð· Ñ‡ÐµÐ³Ð¾ ÑÐ¾ÑÑ‚Ð¾Ð¸Ñ‚",
    ".Ð±",
    ".Ðº",
    ".Ð´",
    "userbot",
    "visitor",
    "chat bot",
    "chatbot",
    "control bot",
    "auto-reply",
    "auto reply",
    "Ð°Ð²Ñ‚Ð¾Ð¾Ñ‚Ð²ÐµÑ‚",
    "judge",
    "ÑÑƒÐ´ÑŒÑ",
)
DEEP_INTERNAL_MARKERS = (
    "pipeline",
    "flow",
    "wiring",
    "architecture",
    "Ð°Ñ€Ñ…Ð¸Ñ‚ÐµÐºÑ‚ÑƒÑ€",
    "message processing",
    "Ð¿Ð¾Ñ‡ÐµÐ¼Ñƒ Ð±Ð¾Ñ‚",
    "Ð¿Ð¾Ñ‡ÐµÐ¼Ñƒ Ð¾Ñ‚Ð²ÐµÑ‡Ð°ÐµÑ‚ Ð´Ð¾Ð»Ð³Ð¾",
    "where to change",
    "Ð³Ð´Ðµ Ð¼ÐµÐ½ÑÑ‚ÑŒ",
    "what controls",
)
SIMPLE_TASK_MARKERS = (
    "Ð½Ð°Ð¿Ð¸ÑˆÐ¸",
    "Ð¿ÐµÑ€ÐµÐ²ÐµÐ´Ð¸",
    "translate",
    "rewrite",
    "Ð¿ÐµÑ€ÐµÐ¿Ð¸ÑˆÐ¸",
    "ÑÑ„Ð¾Ñ€Ð¼ÑƒÐ»Ð¸Ñ€ÑƒÐ¹",
    "ÑÐ´ÐµÐ»Ð°Ð¹ ÐºÐ¾Ñ€Ð¾Ñ‡Ðµ",
    "ÑÐ¾ÐºÑ€Ð°Ñ‚Ð¸",
    "summarize",
    "Ñ€ÐµÐ·ÑŽÐ¼Ð¸Ñ€ÑƒÐ¹",
    "ÑÐ´ÐµÐ»Ð°Ð¹ Ñ‚ÐµÐºÑÑ‚",
    "Ð¿Ñ€Ð¸Ð´ÑƒÐ¼Ð°Ð¹",
    "Ð¿Ð¾Ð·Ð´Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ",
    "ÑˆÑƒÑ‚Ðº",
)


@dataclass(frozen=True)
class KnowledgeSection:
    heading: str
    normalized_heading: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class OwnerKnowledgeRoute:
    kind: str
    tags: tuple[str, ...]
    confidence: int


def _normalize_heading_value(raw_line: str) -> str:
    stripped = raw_line.strip()
    if stripped.startswith("#"):
        stripped = stripped.lstrip("#").strip()
    return stripped.casefold()


def _is_private_section_marker(raw_line: str) -> bool:
    normalized = _normalize_heading_value(raw_line)
    return normalized.startswith("about assistant-ai") or normalized.startswith(
        "owner quick reference"
    ) or normalized in {
        "private",
        "owner only",
    }


def _contains_internal_path_reference(raw_line: str) -> bool:
    lowered = raw_line.strip().casefold()
    return any(pattern in lowered for pattern in INTERNAL_PATH_PATTERNS)


def _clean_section_line(raw_line: str) -> str | None:
    stripped = raw_line.strip()
    if not stripped:
        return None
    if _contains_internal_path_reference(stripped):
        return None
    if stripped.startswith("-"):
        return stripped
    return f"- {stripped}"


def _parse_knowledge_sections(content: str) -> list[KnowledgeSection]:
    sections: list[KnowledgeSection] = []
    current_heading = ""
    current_normalized = ""
    current_lines: list[str] = []
    for raw_line in str(content or "").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            if current_heading:
                sections.append(
                    KnowledgeSection(
                        heading=current_heading,
                        normalized_heading=current_normalized,
                        lines=tuple(current_lines),
                    )
                )
            current_heading = stripped.lstrip("#").strip()
            current_normalized = _normalize_heading_value(stripped)
            current_lines = []
            continue
        line = _clean_section_line(stripped)
        if line is None:
            continue
        current_lines.append(line)
    if current_heading:
        sections.append(
            KnowledgeSection(
                heading=current_heading,
                normalized_heading=current_normalized,
                lines=tuple(current_lines),
            )
        )
    return sections


def _score_topic_tags(query: str) -> dict[str, int]:
    lowered = " ".join((query or "").split()).casefold()
    scores: dict[str, int] = {}
    for tag, markers in TOPIC_QUERY_MARKERS.items():
        score = 0
        for marker in markers:
            marker_lower = marker.casefold()
            if marker_lower and marker_lower in lowered:
                score += 1
        if score:
            scores[tag] = score
    return scores


def _route_owner_query(query: str) -> OwnerKnowledgeRoute:
    lowered = " ".join((query or "").split()).casefold()
    if not lowered:
        return OwnerKnowledgeRoute(kind="general", tags=(), confidence=0)

    tag_scores = _score_topic_tags(lowered)
    internal_score = sum(
        3 for marker in INTERNAL_HARD_MARKERS if marker.casefold() in lowered
    )
    deep_score = sum(
        2 for marker in DEEP_INTERNAL_MARKERS if marker.casefold() in lowered
    )
    profile_score = tag_scores.get("owner_profile", 0)
    simple_score = sum(
        1 for marker in SIMPLE_TASK_MARKERS if marker.casefold() in lowered
    )
    if simple_score and internal_score == 0 and len(tag_scores) <= 1 and profile_score == 0:
        return OwnerKnowledgeRoute(kind="simple", tags=(), confidence=0)

    sorted_tags = tuple(
        tag
        for tag, score in sorted(
            tag_scores.items(),
            key=lambda item: (item[1], item[0] == "owner_profile"),
            reverse=True,
        )
        if tag != "owner_profile"
    )
    confidence = internal_score + deep_score + sum(
        score for tag, score in tag_scores.items() if tag != "owner_profile"
    )
    if deep_score >= 2 or confidence >= 6:
        return OwnerKnowledgeRoute(
            kind="deep_internal",
            tags=sorted_tags[:4] or ("architecture", "debug"),
            confidence=confidence,
        )
    if confidence >= 3:
        return OwnerKnowledgeRoute(
            kind="internal",
            tags=sorted_tags[:3] or ("commands",),
            confidence=confidence,
        )
    if profile_score:
        return OwnerKnowledgeRoute(
            kind="owner_profile",
            tags=("owner_profile",),
            confidence=profile_score,
        )
    return OwnerKnowledgeRoute(kind="general", tags=(), confidence=0)


def _unique_sections_in_order(
    sections: list[KnowledgeSection], normalized_headings: tuple[str, ...]
) -> list[KnowledgeSection]:
    wanted = set(normalized_headings)
    selected: list[KnowledgeSection] = []
    seen: set[str] = set()
    for section in sections:
        normalized = section.normalized_heading
        if normalized not in wanted or normalized in seen:
            continue
        seen.add(normalized)
        selected.append(section)
    return selected


def _render_section_block(
    sections: list[KnowledgeSection], *, max_lines: int, max_chars: int
) -> str:
    lines: list[str] = []
    total_chars = 0
    for section in sections:
        heading_line = f"Section: {section.normalized_heading}"
        candidate_lines = [heading_line, *section.lines]
        for line in candidate_lines:
            projected_chars = total_chars + len(line)
            if lines and (projected_chars > max_chars or len(lines) >= max_lines):
                return "Persistent owner knowledge:\n" + "\n".join(lines)
            lines.append(line)
            total_chars = projected_chars
    if not lines:
        return ""
    return "Persistent owner knowledge:\n" + "\n".join(lines)


class OwnerKnowledgeStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._content = ""

    async def load(self) -> str:
        async with self._lock:
            if not self._path.exists():
                atomic_write_text_sync(self._path, DEFAULT_OWNER_KNOWLEDGE)
            try:
                self._content = await asyncio.to_thread(
                    self._path.read_text, encoding="utf-8"
                )
            except OSError:
                self._content = DEFAULT_OWNER_KNOWLEDGE
            return self._content

    async def get_prompt_block(self) -> str:
        """Public block shown in prompts that should not see private owner docs."""
        async with self._lock:
            content = self._content
        lines: list[str] = []
        for raw_line in str(content or "").splitlines():
            line = raw_line.strip()
            if _is_private_section_marker(line):
                break
            if not line or line.startswith("#"):
                continue
            lines.append(line)
        if not lines:
            return ""
        return "Persistent owner knowledge:\n" + "\n".join(
            f"- {line}" for line in lines[:40]
        )

    async def get_raw_public_knowledge(self) -> str:
        """Raw markdown block for visitor cards parsing."""
        async with self._lock:
            content = self._content
        lines: list[str] = []
        for raw_line in str(content or "").splitlines():
            line = raw_line.rstrip()
            if _is_private_section_marker(line):
                break
            lines.append(line)
        return "\n".join(lines).strip()

    async def get_owner_prompt_block(self) -> str:
        """Full block shown only in owner prompts."""
        async with self._lock:
            content = self._content
        lines: list[str] = []
        total_chars = 0
        for raw_line in str(content or "").splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            if _contains_internal_path_reference(stripped):
                continue
            if stripped.startswith("#"):
                heading = _normalize_heading_value(stripped)
                if not heading:
                    continue
                line = f"Section: {heading}"
            elif stripped.startswith("-"):
                line = stripped
            else:
                line = f"- {stripped}"
            projected_chars = total_chars + len(line)
            if lines and projected_chars > OWNER_PROMPT_MAX_CHARS:
                break
            lines.append(line)
            total_chars = projected_chars
            if len(lines) >= OWNER_PROMPT_MAX_LINES:
                break
        if not lines:
            return ""
        return "Persistent owner knowledge:\n" + "\n".join(lines)

    async def get_owner_prompt_block_for_query(self, query: str) -> str:
        """Select only the owner knowledge sections that match the current query."""
        async with self._lock:
            content = self._content
        sections = _parse_knowledge_sections(content)
        if not sections:
            return ""

        route = _route_owner_query(query)
        if route.kind == "simple":
            return ""

        if route.kind == "owner_profile":
            selected = _unique_sections_in_order(
                sections, tuple(sorted(PUBLIC_PROFILE_HEADINGS))
            )
            return _render_section_block(
                selected,
                max_lines=OWNER_SELECTIVE_BASE_MAX_LINES,
                max_chars=OWNER_SELECTIVE_BASE_MAX_CHARS,
            )

        if route.kind == "general":
            return ""

        heading_order: list[str] = list(OWNER_FOUNDATION_HEADINGS)
        for tag in route.tags:
            heading_order.extend(sorted(TOPIC_HEADING_MAP.get(tag, ())))
        if route.kind == "deep_internal" and "debug" not in route.tags:
            heading_order.extend(sorted(TOPIC_HEADING_MAP["debug"]))
        selected = _unique_sections_in_order(sections, tuple(heading_order))
        max_lines = (
            OWNER_SELECTIVE_DEEP_MAX_LINES
            if route.kind == "deep_internal"
            else OWNER_SELECTIVE_TOPIC_MAX_LINES
        )
        max_chars = (
            OWNER_SELECTIVE_DEEP_MAX_CHARS
            if route.kind == "deep_internal"
            else OWNER_SELECTIVE_TOPIC_MAX_CHARS
        )
        return _render_section_block(
            selected,
            max_lines=max_lines,
            max_chars=max_chars,
        )


