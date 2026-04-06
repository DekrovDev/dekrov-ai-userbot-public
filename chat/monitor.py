from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from infra.json_atomic import atomic_write_json


LOGGER = logging.getLogger("assistant.monitor")


@dataclass(slots=True)
class MonitorRule:
    rule_id: str
    keywords: list[str]  # keywords to watch (case-insensitive)
    chat_ids: list[int]  # which chats to monitor (empty = all allowed chats)
    notify_chat_id: int  # where to send notification (usually chat_bot DM)
    label: str = ""  # human label for this rule
    enabled: bool = True
    created_at: str = ""
    last_triggered_at: str | None = None
    cooldown_seconds: int = 300  # don't spam same rule more than once per N seconds
    smart_match: str | None = (
        None  
    )


@dataclass(slots=True)
class MonitorRulePatch:
    keywords: list[str] | None = None
    chat_ids: list[int] | None = None
    enabled: bool | None = None
    label: str | None = None
    cooldown_seconds: int | None = None
    smart_match: str | None = None


class MonitorStore:
    """Stores and evaluates keyword monitoring rules."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._rules: dict[str, MonitorRule] = {}

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
            for rule_id, item in (data.get("rules") or {}).items():
                try:
                    self._rules[rule_id] = self._rule_from_dict(item)
                except Exception:
                    LOGGER.debug(
                        "monitor_load_rule_failed rule_id=%s", rule_id, exc_info=True
                    )
        LOGGER.info("monitor_loaded rules=%d", len(self._rules))

    async def add_rule(self, rule: MonitorRule) -> MonitorRule:
        async with self._lock:
            self._rules[rule.rule_id] = rule
            await self._write_locked()
        return rule

    async def remove_rule(self, rule_id: str) -> bool:
        async with self._lock:
            removed = self._rules.pop(rule_id, None)
            if removed is None:
                return False
            await self._write_locked()
        return True

    async def patch_rule(
        self, rule_id: str, patch: MonitorRulePatch
    ) -> MonitorRule | None:
        async with self._lock:
            rule = self._rules.get(rule_id)
            if rule is None:
                return None
            updated = MonitorRule(
                rule_id=rule.rule_id,
                keywords=patch.keywords
                if patch.keywords is not None
                else rule.keywords,
                chat_ids=patch.chat_ids
                if patch.chat_ids is not None
                else rule.chat_ids,
                notify_chat_id=rule.notify_chat_id,
                label=patch.label if patch.label is not None else rule.label,
                enabled=patch.enabled if patch.enabled is not None else rule.enabled,
                created_at=rule.created_at,
                last_triggered_at=rule.last_triggered_at,
                cooldown_seconds=patch.cooldown_seconds
                if patch.cooldown_seconds is not None
                else rule.cooldown_seconds,
            )
            self._rules[rule_id] = updated
            await self._write_locked()
            return updated

    async def list_rules(self) -> list[MonitorRule]:
        async with self._lock:
            return list(self._rules.values())

    async def check_message(
        self,
        *,
        text: str,
        chat_id: int,
        sender_label: str,
        message_id: int,
    ) -> list[tuple[MonitorRule, list[str]]]:
        """
        Check if message matches any active rule.
        Returns list of (rule, matched_keywords) tuples.
        """
        if not text:
            return []
        lowered = text.casefold()
        now = datetime.now(timezone.utc)
        matches: list[tuple[MonitorRule, list[str]]] = []

        async with self._lock:
            for rule in self._rules.values():
                if not rule.enabled:
                    continue
                # Check chat filter
                if rule.chat_ids and chat_id not in rule.chat_ids:
                    continue
                # Check cooldown
                if rule.last_triggered_at:
                    try:
                        last = datetime.fromisoformat(rule.last_triggered_at)
                        if (now - last).total_seconds() < rule.cooldown_seconds:
                            continue
                    except Exception:
                        pass
                # Check keywords
                matched = [kw for kw in rule.keywords if kw.casefold() in lowered]
                if matched:
                    matches.append((rule, matched))
                    rule.last_triggered_at = now.isoformat()

            if matches:
                await self._write_locked()

        return matches

    def build_notification_text(
        self,
        rule: MonitorRule,
        matched_keywords: list[str],
        *,
        chat_id: int,
        sender_label: str,
        message_text: str,
        message_id: int,
    ) -> str:
        kw_str = ", ".join(f"<code>{kw}</code>" for kw in matched_keywords)
        label = f" <b>{rule.label}</b>" if rule.label else ""
        preview = message_text[:200].replace("<", "&lt;").replace(">", "&gt;")
        return (
            f"ðŸ”” ÐœÐ¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³{label}\n\n"
            f"<b>Ð§Ð°Ñ‚:</b> <code>{chat_id}</code>\n"
            f"<b>ÐžÑ‚:</b> {sender_label}\n"
            f"<b>ÐšÐ»ÑŽÑ‡ÐµÐ²Ñ‹Ðµ ÑÐ»Ð¾Ð²Ð°:</b> {kw_str}\n\n"
            f"<blockquote>{preview}</blockquote>"
        )

    async def _write_locked(self) -> None:
        await atomic_write_json(
            self._path,
            {"rules": {rid: asdict(r) for rid, r in self._rules.items()}},
            indent=2,
        )

    def _rule_from_dict(self, data: dict) -> MonitorRule:
        return MonitorRule(
            rule_id=str(data.get("rule_id", "")),
            keywords=[str(k) for k in (data.get("keywords") or [])],
            chat_ids=[int(c) for c in (data.get("chat_ids") or [])],
            notify_chat_id=int(data.get("notify_chat_id", 0)),
            label=str(data.get("label", "")),
            enabled=bool(data.get("enabled", True)),
            created_at=str(data.get("created_at", "")),
            last_triggered_at=data.get("last_triggered_at"),
            cooldown_seconds=int(data.get("cooldown_seconds", 300)),
            smart_match=data.get("smart_match"),
        )


def parse_monitor_command(prompt: str) -> dict | None:
    """
    Parse monitor add/remove commands from .Ð´
    """
    lowered = " ".join((prompt or "").strip().casefold().split())

    ADD_MARKERS = (
        "Ð´Ð¾Ð±Ð°Ð²ÑŒ Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³",
        "ÑÐ»ÐµÐ´Ð¸ Ð·Ð°",
        "Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€ÑŒ",
        "watch for",
        "monitor",
        "Ð¾Ñ‚ÑÐ»ÐµÐ¶Ð¸Ð²Ð°Ð¹",
        "ÑÐ»ÐµÐ´Ð¸Ñ‚ÑŒ Ð·Ð°",
    )
    REMOVE_MARKERS = (
        "ÑƒÐ±ÐµÑ€Ð¸ Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³",
        "ÑƒÐ´Ð°Ð»Ð¸ Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³",
        "stop monitoring",
        "remove monitor",
        "Ð¾Ñ‚ÐºÐ»ÑŽÑ‡Ð¸ Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³",
    )
    LIST_MARKERS = (
        "ÑÐ¿Ð¸ÑÐ¾Ðº Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³Ð°",
        "Ð¿Ð¾ÐºÐ°Ð¶Ð¸ Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³",
        "list monitors",
        "show monitors",
        "Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³ ÑÐ¿Ð¸ÑÐ¾Ðº",
    )

    if any(m in lowered for m in LIST_MARKERS):
        return {"action": "list"}

    if any(m in lowered for m in REMOVE_MARKERS):
        # Extract keyword or rule label to remove
        for marker in REMOVE_MARKERS:
            if marker in lowered:
                idx = lowered.index(marker) + len(marker)
                rest = prompt[idx:].strip(" .,;:")
                return {"action": "remove", "label": rest}
        return {"action": "remove", "label": ""}

    if any(m in lowered for m in ADD_MARKERS):
        # Extract keywords (comma-separated) and optional chat
        for marker in ADD_MARKERS:
            if marker in lowered:
                idx = lowered.index(marker) + len(marker)
                rest = prompt[idx:].strip()
                break
        else:
            rest = prompt

        # Split off chat reference
        chat_ref: str | int | None = None
        chat_match = re.search(
            r"(?:Ð² Ñ‡Ð°Ñ‚Ðµ?|Ð² Ð³Ñ€ÑƒÐ¿Ð¿Ðµ?|in chat|in group)\s+(@\S+|-?\d{6,})",
            rest,
            re.IGNORECASE,
        )
        if chat_match:
            ref = chat_match.group(1).strip()
            chat_ref = int(ref) if ref.lstrip("-").isdigit() else ref
            rest = rest[: chat_match.start()].strip()

        # Extract keywords
        keywords = [kw.strip() for kw in re.split(r"[,;]", rest) if kw.strip()]
        if not keywords:
            return None

        return {"action": "add", "keywords": keywords, "chat_ref": chat_ref}

    return None

