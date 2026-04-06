from __future__ import annotations

"""
visitor_faq_cache.py â€” Auto-answers for frequent questions.

Owner manages the list via bot command:
  /vfaq add <pattern> | <answer>
  /vfaq list
  /vfaq remove <id>
  /vfaq clear

Checked after easter eggs, before AI.
Uses simple substring/regex matching â€” no AI cost.
"""

import re
import time
import asyncio
import logging
from dataclasses import dataclass, field

LOGGER = logging.getLogger("assistant.visitor.faq_cache")


@dataclass
class FaqEntry:
    id: int
    pattern_raw: str           # what owner typed
    pattern: re.Pattern        # compiled for matching
    answer: str
    hits: int = 0
    created_at: float = field(default_factory=time.time)

    def matches(self, text: str) -> bool:
        return bool(self.pattern.search(text))


class VisitorFaqCache:
    """In-memory FAQ cache. Owner-managed via commands."""

    def __init__(self) -> None:
        self._entries: list[FaqEntry] = []
        self._lock = asyncio.Lock()
        self._next_id = 1
        # Pre-load some sensible defaults
        self._load_defaults()

    def _load_defaults(self) -> None:
        defaults = [
            (r"ÐºÐ°Ðº\s+ÑÐ²ÑÐ·Ð°Ñ‚ÑŒÑÑ|how\s+to\s+contact|Ð½Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ\s+Ñ‚ÐµÐ±Ðµ|Ð½Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ\s+Ð´ÐµÐºÑ€Ð¾Ð²Ñƒ",
             "ÐÐ°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ ProjectOwner Ð¼Ð¾Ð¶Ð½Ð¾ Ð² Telegram: <a href='https://t.me/example_owner'>@example_owner</a>\n"
             "Ð˜Ð»Ð¸ Ð½Ð° email: contact@example.com"),

            (r"ÑÐºÐ¾Ð»ÑŒÐºÐ¾\s+ÑÑ‚Ð¾Ð¸Ñ‚|Ñ†ÐµÐ½Ð°|Ð¿Ñ€Ð°Ð¹Ñ|price|cost|Ñ€Ð°ÑÑ†ÐµÐ½Ðº",
             "Ð¡Ñ‚Ð¾Ð¸Ð¼Ð¾ÑÑ‚ÑŒ Ð·Ð°Ð²Ð¸ÑÐ¸Ñ‚ Ð¾Ñ‚ Ð·Ð°Ð´Ð°Ñ‡Ð¸. ÐÐ°Ð¿Ð¸ÑˆÐ¸Ñ‚Ðµ Ð² Telegram Ð´Ð»Ñ Ð¾Ð±ÑÑƒÐ¶Ð´ÐµÐ½Ð¸Ñ: "
             "<a href='https://t.me/example_owner'>@example_owner</a>"),

            (r"Ð³Ð´Ðµ\s+(Ñ‚Ð²Ð¾Ð¹\s+)?github|Ð²Ð°Ñˆ\s+github|Ð³Ð¸Ñ‚Ñ…Ð°Ð±",
             "GitHub: <a href='https://github.com/example'>github.com/example</a>"),

            (r"Ð³Ð´Ðµ\s+(Ñ‚Ð²Ð¾Ð¹\s+)?ÑÐ°Ð¹Ñ‚|Ñ‚Ð²Ð¾Ð¹\s+Ð²ÐµÐ±ÑÐ°Ð¹Ñ‚|Ð¿Ð¾Ñ€Ñ‚Ñ„Ð¾Ð»Ð¸Ð¾\s+ÑÐ°Ð¹Ñ‚",
             "ÐŸÐ¾Ñ€Ñ‚Ñ„Ð¾Ð»Ð¸Ð¾: <a href='https://example.com'>example.com</a>"),

            (r"Ñ‚Ñ‹\s+Ð±Ð¾Ñ‚|ÑÑ‚Ð¾\s+Ð±Ð¾Ñ‚|ai\s+Ð¸Ð»Ð¸|artificial",
             "Ð”Ð°, Ñ AI-ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ð½Ñ‚. ÐŸÑ€ÐµÐ´ÑÑ‚Ð°Ð²Ð»ÑÑŽ ProjectOwner Ð¸ Ð¾Ñ‚Ð²ÐµÑ‡Ð°ÑŽ Ð½Ð° Ð²Ð¾Ð¿Ñ€Ð¾ÑÑ‹ Ð¾ ÐµÐ³Ð¾ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ… Ð¸ Ñ€Ð°Ð±Ð¾Ñ‚Ðµ."),
        ]
        for pat_raw, answer in defaults:
            try:
                pat = re.compile(pat_raw, re.IGNORECASE)
                entry = FaqEntry(
                    id=self._next_id,
                    pattern_raw=pat_raw,
                    pattern=pat,
                    answer=answer,
                )
                self._entries.append(entry)
                self._next_id += 1
            except re.error:
                pass

    async def match(self, text: str) -> str | None:
        """Check if text matches any FAQ entry. Returns answer or None."""
        async with self._lock:
            for entry in self._entries:
                if entry.matches(text):
                    entry.hits += 1
                    return entry.answer
        return None

    async def add(self, pattern_raw: str, answer: str) -> FaqEntry | str:
        """Add new FAQ entry. Returns entry or error string."""
        try:
            pat = re.compile(pattern_raw, re.IGNORECASE)
        except re.error as e:
            return f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð² Ð¿Ð°Ñ‚Ñ‚ÐµÑ€Ð½Ðµ: {e}"

        async with self._lock:
            entry = FaqEntry(
                id=self._next_id,
                pattern_raw=pattern_raw,
                pattern=pat,
                answer=answer,
            )
            self._entries.append(entry)
            self._next_id += 1
            return entry

    async def remove(self, entry_id: int) -> bool:
        """Remove entry by id. Returns True if found."""
        async with self._lock:
            before = len(self._entries)
            self._entries = [e for e in self._entries if e.id != entry_id]
            return len(self._entries) < before

    async def clear(self) -> int:
        """Remove all entries. Returns count removed."""
        async with self._lock:
            count = len(self._entries)
            self._entries = []
            return count

    async def list_entries(self) -> list[FaqEntry]:
        async with self._lock:
            return list(self._entries)

    async def format_list(self) -> str:
        """Format FAQ list for owner display."""
        entries = await self.list_entries()
        if not entries:
            return "FAQ Ð¿ÑƒÑÑ‚. Ð”Ð¾Ð±Ð°Ð²ÑŒ: /vfaq add Ð¿Ð°Ñ‚Ñ‚ÐµÑ€Ð½ | Ð¾Ñ‚Ð²ÐµÑ‚"

        lines = [f"<b>ðŸ“‹ FAQ Ð°Ð²Ñ‚Ð¾Ð¾Ñ‚Ð²ÐµÑ‚Ñ‹ ({len(entries)})</b>\n"]
        for e in entries:
            hits_str = f" Â· {e.hits} ÑÐ¾Ð²Ð¿Ð°Ð´." if e.hits else ""
            pat_display = e.pattern_raw[:40] + "..." if len(e.pattern_raw) > 40 else e.pattern_raw
            ans_display = e.answer[:60] + "..." if len(e.answer) > 60 else e.answer
            lines.append(
                f"<b>#{e.id}</b> <code>{pat_display}</code>{hits_str}\n"
                f"  â†’ {ans_display}"
            )
        lines.append("\nÐ£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ: /vfaq remove &lt;id&gt;")
        return "\n".join(lines)


