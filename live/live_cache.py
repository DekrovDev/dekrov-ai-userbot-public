from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from infra.json_atomic import atomic_write_json


@dataclass(slots=True)
class LiveCacheEntry:
    value: str
    expires_at: str


class LiveCacheStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._entries: dict[str, LiveCacheEntry] = {}

    async def load(self) -> dict[str, LiveCacheEntry]:
        async with self._lock:
            if not self._path.exists():
                await self._write_locked()
                return copy.deepcopy(self._entries)

            try:
                raw = await asyncio.to_thread(self._path.read_text, encoding="utf-8")
                payload = json.loads(raw or "{}")
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                payload = {}

            self._entries = {
                str(key): LiveCacheEntry(
                    value=str(item.get("value", "")),
                    expires_at=str(item.get("expires_at", "")),
                )
                for key, item in (payload or {}).items()
                if isinstance(item, dict)
            }
            self._purge_expired_locked()
            await self._write_locked()
            return copy.deepcopy(self._entries)

    async def get(
        self, *, kind: str, query: str, language: str, variant: str = ""
    ) -> str | None:
        async with self._lock:
            self._purge_expired_locked()
            entry = self._entries.get(_cache_key(kind, query, language, variant))
            if entry is None:
                return None
            return entry.value

    async def set(
        self,
        *,
        kind: str,
        query: str,
        language: str,
        value: str,
        ttl_seconds: int,
        variant: str = "",
    ) -> None:
        async with self._lock:
            expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=max(1, ttl_seconds)
            )
            self._entries[_cache_key(kind, query, language, variant)] = LiveCacheEntry(
                value=value,
                expires_at=expires_at.isoformat(),
            )
            self._purge_expired_locked()
            await self._write_locked()

    def _purge_expired_locked(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [
            key
            for key, entry in self._entries.items()
            if _parse_iso(entry.expires_at) is None
            or _parse_iso(entry.expires_at) <= now
        ]
        for key in expired:
            self._entries.pop(key, None)

    async def _write_locked(self) -> None:
        await atomic_write_json(
            self._path,
            {key: asdict(entry) for key, entry in self._entries.items()},
            indent=2,
        )


def _cache_key(kind: str, query: str, language: str, variant: str) -> str:
    raw = json.dumps(
        {
            "kind": kind,
            "query": " ".join((query or "").split()).casefold(),
            "language": language.casefold(),
            "variant": variant.casefold(),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
