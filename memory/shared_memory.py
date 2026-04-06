from __future__ import annotations

import asyncio
import copy
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from infra.json_atomic import atomic_write_json


WORD_RE = re.compile(
    r"[A-Za-z\u0400-\u04FF0-9][A-Za-z\u0400-\u04FF0-9_+-]{2,}", re.UNICODE
)
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
    "about",
    "just",
    "what",
    "when",
    "where",
    "will",
    "would",
    "could",
    "как",
    "что",
    "это",
    "тут",
    "там",
    "для",
    "или",
    "если",
    "потому",
    "только",
    "короче",
    "типа",
    "просто",
    "owner",
}


@dataclass(slots=True)
class SharedMemoryEntry:
    text: str
    chat_id: int
    author: str
    topic_key: str
    keywords: list[str]
    observed_at: str


class SharedMemoryStore:
    def __init__(self, path: Path, ttl_hours: int = 6, max_entries: int = 160) -> None:
        self._path = path
        self._ttl = timedelta(hours=max(1, ttl_hours))
        self._max_entries = max(40, max_entries)
        self._lock = asyncio.Lock()
        self._entries: list[SharedMemoryEntry] = []

    async def load(self) -> list[SharedMemoryEntry]:
        async with self._lock:
            if not self._path.exists():
                await self._write_locked()
                return copy.deepcopy(self._entries)

            try:
                raw = await asyncio.to_thread(self._path.read_text, encoding="utf-8")
                payload = json.loads(raw or "[]")
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                payload = []

            loaded: list[SharedMemoryEntry] = []
            if isinstance(payload, list):
                for item in payload:
                    entry = self._entry_from_dict(item)
                    if entry is not None:
                        loaded.append(entry)
            self._entries = loaded
            self._prune_locked()
            await self._write_locked()
            return copy.deepcopy(self._entries)

    async def observe(
        self, *, chat_id: int, author: str, text: str, at: datetime | None = None
    ) -> None:
        normalized = " ".join((text or "").split()).strip()
        if not normalized:
            return
        keywords = self._extract_keywords(normalized)
        if not keywords:
            return
        observed_at = (at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        entry = SharedMemoryEntry(
            text=normalized[:280],
            chat_id=int(chat_id),
            author=(author or "Unknown")[:48],
            topic_key=" ".join(keywords[:3]),
            keywords=keywords[:6],
            observed_at=observed_at.isoformat(),
        )
        async with self._lock:
            self._prune_locked(now=observed_at)
            self._entries.append(entry)
            self._dedupe_locked()
            self._entries.sort(key=lambda item: item.observed_at)
            self._entries = self._entries[-self._max_entries :]
            await self._write_locked()

    async def build_relevant_context(
        self,
        *,
        query: str,
        current_chat_id: int | None = None,
        max_items: int = 4,
    ) -> str:
        query_keywords = self._extract_keywords(query or "")
        if not query_keywords:
            return ""
        async with self._lock:
            self._prune_locked()
            candidates = list(self._entries)
            await self._write_locked()

        scored: list[tuple[int, SharedMemoryEntry]] = []
        query_set = set(query_keywords)
        for entry in candidates:
            if current_chat_id is not None and entry.chat_id == current_chat_id:
                continue
            overlap = len(query_set & set(entry.keywords))
            if overlap <= 0:
                continue
            scored.append((overlap, entry))

        if not scored:
            return ""

        scored.sort(key=lambda item: (item[0], item[1].observed_at), reverse=True)
        lines = ["Short-lived memory from other chats in the last 6 hours:"]
        seen: set[tuple[int, str]] = set()
        for _, entry in scored:
            key = (entry.chat_id, entry.text.casefold())
            if key in seen:
                continue
            seen.add(key)
            lines.append(
                f"- chat {entry.chat_id} | {entry.author} | topic: {entry.topic_key} | {entry.text}"
            )
            if len(lines) >= max_items + 1:
                break
        return "\n".join(lines) if len(lines) > 1 else ""

    async def clear_all(self) -> bool:
        async with self._lock:
            had_anything = bool(self._entries)
            self._entries = []
            if had_anything:
                await self._write_locked()
            return had_anything

    def _extract_keywords(self, text: str) -> list[str]:
        tokens: list[str] = []
        seen: set[str] = set()
        for raw in WORD_RE.findall((text or "").casefold()):
            token = raw.strip("_+-")
            if len(token) < 3 or token.isdigit() or token in STOPWORDS:
                continue
            if token in seen:
                continue
            seen.add(token)
            tokens.append(token)
            if len(tokens) >= 6:
                break
        return tokens

    def _entry_from_dict(self, payload: object) -> SharedMemoryEntry | None:
        if not isinstance(payload, dict):
            return None
        text = " ".join(str(payload.get("text", "")).split()).strip()
        observed_at = str(payload.get("observed_at", "")).strip()
        if not text or not observed_at:
            return None
        try:
            chat_id = int(payload.get("chat_id"))
        except (TypeError, ValueError):
            return None
        keywords = [
            str(item).strip().casefold()
            for item in (payload.get("keywords") or [])
            if str(item).strip()
        ][:6]
        if not keywords:
            keywords = self._extract_keywords(text)
        if not keywords:
            return None
        return SharedMemoryEntry(
            text=text[:280],
            chat_id=chat_id,
            author=str(payload.get("author", "Unknown"))[:48],
            topic_key=str(payload.get("topic_key") or " ".join(keywords[:3]))[:96],
            keywords=keywords,
            observed_at=observed_at,
        )

    def _dedupe_locked(self) -> None:
        deduped: list[SharedMemoryEntry] = []
        seen: set[tuple[int, str, str]] = set()
        for entry in reversed(self._entries):
            key = (entry.chat_id, entry.author.casefold(), entry.text.casefold())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(entry)
        deduped.reverse()
        self._entries = deduped

    def _prune_locked(self, now: datetime | None = None) -> None:
        current = now or datetime.now(timezone.utc)
        kept: list[SharedMemoryEntry] = []
        for entry in self._entries:
            observed_at = self._parse_iso(entry.observed_at)
            if observed_at is None:
                continue
            if current - observed_at > self._ttl:
                continue
            kept.append(entry)
        self._entries = kept[-self._max_entries :]

    def _parse_iso(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    async def _write_locked(self) -> None:
        await atomic_write_json(
            self._path, [asdict(entry) for entry in self._entries], indent=2
        )
