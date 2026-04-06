from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from infra.json_atomic import atomic_write_json


@dataclass(slots=True)
class OwnerActionLogEntry:
    action_id: str
    kind: str
    summary: str
    created_at: str
    undo_kind: str | None = None
    undo_payload: dict[str, Any] | None = None


class OwnerActionLogStore:
    def __init__(self, path: Path, *, max_entries: int = 200) -> None:
        self._path = path
        self._max_entries = max(20, int(max_entries))
        self._lock = asyncio.Lock()
        self._entries: list[OwnerActionLogEntry] = []

    async def load(self) -> None:
        async with self._lock:
            if not self._path.exists():
                await self._write_locked()
                return
            try:
                raw = await asyncio.to_thread(self._path.read_text, encoding="utf-8")
                data = json.loads(raw or "{}")
            except Exception:
                data = {}
            self._entries = []
            for item in (data.get("entries") or []):
                try:
                    self._entries.append(
                        OwnerActionLogEntry(
                            action_id=str(item.get("action_id", "")),
                            kind=str(item.get("kind", "")),
                            summary=str(item.get("summary", "")),
                            created_at=str(item.get("created_at", "")),
                            undo_kind=(
                                str(item.get("undo_kind"))
                                if item.get("undo_kind") is not None
                                else None
                            ),
                            undo_payload=item.get("undo_payload"),
                        )
                    )
                except Exception:
                    continue
            self._entries = self._entries[-self._max_entries :]
            await self._write_locked()

    async def append(self, entry: OwnerActionLogEntry) -> None:
        async with self._lock:
            self._entries.append(entry)
            self._entries = self._entries[-self._max_entries :]
            await self._write_locked()

    async def list_recent(self, limit: int = 5) -> list[OwnerActionLogEntry]:
        async with self._lock:
            items = list(self._entries[-max(1, limit) :])
        items.reverse()
        return items

    async def find_recent(self, query: str, *, limit: int = 25) -> tuple[OwnerActionLogEntry | None, list[OwnerActionLogEntry]]:
        normalized = " ".join((query or "").casefold().split()).strip()
        recent = await self.list_recent(limit)
        if not normalized:
            return None, []
        matches = [
            entry
            for entry in recent
            if normalized in " ".join(entry.summary.casefold().split())
            or normalized in entry.kind.casefold()
            or normalized == entry.action_id.casefold()
        ]
        return (matches[0] if len(matches) == 1 else None, matches)

    async def _write_locked(self) -> None:
        await atomic_write_json(
            self._path,
            {"entries": [asdict(entry) for entry in self._entries]},
            indent=2,
        )


def new_action_id() -> str:
    return datetime.now(timezone.utc).strftime("act_%Y%m%d%H%M%S%f")
