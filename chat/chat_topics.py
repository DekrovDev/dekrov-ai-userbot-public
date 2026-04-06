from __future__ import annotations

import asyncio
import copy
import json
import re
from collections import Counter
from pathlib import Path

from infra.json_atomic import atomic_write_json

from chat.context_reader import ContextLine


WORD_RE = re.compile(r"[A-Za-z\u0400-\u04FF0-9][A-Za-z\u0400-\u04FF0-9_+-]{2,}")
STOPWORDS = {
    "and",
    "are",
    "but",
    "for",
    "from",
    "have",
    "that",
    "the",
    "this",
    "with",
    "you",
    "your",
    "как",
    "кто",
    "что",
    "это",
    "вот",
    "если",
    "или",
    "для",
    "про",
    "уже",
    "надо",
    "тут",
    "там",
    "она",
    "они",
    "его",
    "еще",
    "ещё",
    "меня",
    "тебя",
    "только",
    "owner",
}


class ChatTopicStore:
    def __init__(self, path: Path, owner_aliases: list[str] | None = None) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._topics: dict[str, list[str]] = {}
        self._stopwords = set(STOPWORDS)
        for alias in owner_aliases or []:
            normalized = " ".join(str(alias).strip().lstrip(".@").split()).casefold()
            if not normalized:
                continue
            self._stopwords.add(normalized)
            self._stopwords.update(
                part for part in normalized.split() if len(part) >= 3
            )

    async def load(self) -> dict[str, list[str]]:
        async with self._lock:
            if not self._path.exists():
                await self._write_locked()
                return copy.deepcopy(self._topics)

            try:
                raw = await asyncio.to_thread(self._path.read_text, encoding="utf-8")
                loaded = json.loads(raw or "{}")
                if isinstance(loaded, dict):
                    self._topics = {
                        str(chat_id): self._normalize_topics(value)
                        for chat_id, value in loaded.items()
                    }
                else:
                    self._topics = {}
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                self._topics = {}

            await self._write_locked()
            return copy.deepcopy(self._topics)

    async def get_topics(self, chat_id: int | str) -> list[str]:
        async with self._lock:
            return list(self._topics.get(str(chat_id), []))

    async def update_from_context(
        self, chat_id: int | str, context_lines: list[ContextLine]
    ) -> list[str]:
        inferred = self._infer_topics(context_lines)
        if not inferred:
            return await self.get_topics(chat_id)

        async with self._lock:
            self._topics[str(chat_id)] = inferred
            await self._write_locked()
            return list(inferred)

    def _infer_topics(self, context_lines: list[ContextLine]) -> list[str]:
        counts: Counter[str] = Counter()
        for line in context_lines[-25:]:
            text = (line.text or "").casefold()
            if not text:
                continue
            for token in WORD_RE.findall(text):
                normalized = token.strip("_+-").casefold()
                if len(normalized) < 3:
                    continue
                if normalized.isdigit():
                    continue
                if normalized in self._stopwords:
                    continue
                counts[normalized] += 1

        topics = [
            token
            for token, _ in sorted(
                counts.items(),
                key=lambda item: (-item[1], -len(item[0]), item[0]),
            )
            if counts[token] >= 2 or len(token) >= 6
        ]
        return topics[:5]

    def _normalize_topics(self, value) -> list[str]:
        if not isinstance(value, list):
            return []
        topics: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = " ".join(str(item).split()).strip()
            if not normalized:
                continue
            lowered = normalized.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            topics.append(normalized[:48])
        return topics[:5]

    async def _write_locked(self) -> None:
        await atomic_write_json(self._path, self._topics, indent=2)
