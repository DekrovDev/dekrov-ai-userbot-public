from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from infra.json_atomic import atomic_write_json

LOGGER = logging.getLogger("assistant.entity_memory")


MAX_FACTS_PER_ENTITY = 20
USER_ID_RE = re.compile(r"(?iu)\b(?:id|user_id|uid|Ð°Ð¹Ð´Ð¸|Ð¸Ð´)\s*[:=]?\s*(-?\d{5,})\b")
USERNAME_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{3,32})")
URL_RE = re.compile(r"(?iu)\b(?:https?://|www\.)[^\s,]+")
AGE_PATTERNS = (
    re.compile(r"(?iu)\b(?:age|years?\s+old)\s*[:=]?\s*(\d{1,3})\b"),
    re.compile(r"(?iu)\b(\d{1,3})\s*(?:Ð»ÐµÑ‚|Ð³Ð¾Ð´Ð°|Ð³Ð¾Ð´)\b"),
    re.compile(r"(?iu)\b(?:ÐµÐ¼Ñƒ|ÐµÐ¹|age is|Ð²Ð¾Ð·Ñ€Ð°ÑÑ‚)\s*(\d{1,3})\b"),
)
NAME_PATTERNS = (
    re.compile(r"(?iu)\b(?:name|full name|Ð¸Ð¼Ñ|Ð·Ð¾Ð²ÑƒÑ‚)\s*[:=-]?\s*([^\n,.;:]{2,80})"),
    re.compile(
        r"(?iu)\b(?:his name is|her name is|ÐµÐ³Ð¾ Ð·Ð¾Ð²ÑƒÑ‚|ÐµÐµ Ð·Ð¾Ð²ÑƒÑ‚|ÐµÑ‘ Ð·Ð¾Ð²ÑƒÑ‚)\s+([^\n,.;:]{2,80})"
    ),
)
LOCATION_PATTERNS = (
    re.compile(r"(?iu)\b(?:lives in|is from|from|Ð¶Ð¸Ð²[ÐµÑ‘]Ñ‚\s+Ð²|Ð¸Ð·)\s+([^\n,.;:]{2,80})"),
)
WEBSITE_PATTERNS = (
    re.compile(r"(?iu)\b(?:website|site|url|ÑÐ°Ð¹Ñ‚)\s*[:=-]?\s*([^\s,;]+)"),
)


@dataclass(slots=True)
class EntityMemoryEntry:
    username: str | None = None
    display_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    age: int | None = None
    website: str | None = None
    location: str | None = None
    bio: str | None = None
    facts: list[str] = field(default_factory=list)
    updated_at: str | None = None


class EntityMemoryStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._by_id: dict[str, EntityMemoryEntry] = {}
        self._by_username: dict[str, EntityMemoryEntry] = {}
        self._encryptor: Any | None = None

        # Ð˜Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð°Ñ†Ð¸Ñ ÑˆÐ¸Ñ„Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ ÐµÑÐ»Ð¸ ÐµÑÑ‚ÑŒ ÐºÐ»ÑŽÑ‡
        if os.environ.get("ENCRYPTION_KEY"):
            from infra.crypto.encryptor import Encryptor
            from infra.crypto.key_manager import KeyManager

            km = KeyManager()
            self._encryptor = Encryptor(km.key)

    def _encrypt_value(self, value: Any) -> Any:
        """Ð—Ð°ÑˆÐ¸Ñ„Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ðµ ÐµÑÐ»Ð¸ ÐµÑÑ‚ÑŒ encryptor."""
        if self._encryptor is None or value is None:
            return value
        if isinstance(value, str) and value.startswith("enc:"):
            return value  # Ð£Ð¶Ðµ Ð·Ð°ÑˆÐ¸Ñ„Ñ€Ð¾Ð²Ð°Ð½Ð¾
        return "enc:" + self._encryptor.encrypt(value)

    def _decrypt_value(self, value: Any) -> Any:
        """Ð Ð°ÑÑˆÐ¸Ñ„Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ðµ ÐµÑÐ»Ð¸ ÐµÑÑ‚ÑŒ encryptor."""
        if self._encryptor is None or value is None:
            return value
        if not isinstance(value, str) or not value.startswith("enc:"):
            return value  # ÐÐµ Ð·Ð°ÑˆÐ¸Ñ„Ñ€Ð¾Ð²Ð°Ð½Ð¾
        return self._encryptor.decrypt(value[4:])  # Remove "enc:" prefix

    def _encrypt_list(self, values: list[str]) -> list[str]:
        """Ð—Ð°ÑˆÐ¸Ñ„Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº ÑÑ‚Ñ€Ð¾Ðº."""
        if self._encryptor is None or not values:
            return values
        return [self._encrypt_value(v) for v in values]

    def _decrypt_list(self, values: list[str]) -> list[str]:
        """Ð Ð°ÑÑˆÐ¸Ñ„Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº ÑÑ‚Ñ€Ð¾Ðº."""
        if self._encryptor is None or not values:
            return values
        return [self._decrypt_value(v) for v in values]

    def _needs_encryption_migration(self, payload: dict) -> bool:
        """Check if encryption migration is needed.

        Returns True if:
        - No _migration.encryption_v1 flag exists, AND
        - At least one sensitive field is plaintext

        Note: age field is NOT checked for migration (type constraints, low sensitivity).
        """
        if not self._encryptor:
            return False  # Encryption not enabled

        # Check migration flag first
        migration = payload.get("_migration", {})
        if isinstance(migration, dict) and migration.get("encryption_v1") is True:
            return False  # Already migrated

        # Scan for plaintext sensitive fields
        for item in (payload.get("by_id") or {}).values():
            if not isinstance(item, dict):
                continue

            # Check string fields (NOT age)
            for field in ("location", "bio", "website"):
                value = item.get(field)
                if (
                    value
                    and isinstance(value, str)
                    and not str(value).startswith("enc:")
                ):
                    return True

            # Check facts
            for fact in item.get("facts") or []:
                if isinstance(fact, str) and not fact.startswith("enc:"):
                    return True

        return False

    async def _migrate_encryption(self) -> int:
        """Migrate all plaintext sensitive fields to encrypted.

        Must be called with self._lock held.

        Returns:
            Number of fields encrypted (0 if nothing changed)

        Note: age field is NOT encrypted (type constraints, low sensitivity).
        Note: updated_at is NOT updated (system operation, not user action).
        """
        if not self._encryptor:
            return 0  # Encryption not enabled

        migrated_count = 0

        for entry in self._by_id.values():
            # Encrypt string fields (NOT age)
            for field_name in ("location", "bio", "website"):
                value = getattr(entry, field_name)
                if (
                    value
                    and isinstance(value, str)
                    and not str(value).startswith("enc:")
                ):
                    setattr(entry, field_name, self._encrypt_value(value))
                    migrated_count += 1

            # Encrypt facts (simplified counting)
            if entry.facts:
                for i, fact in enumerate(entry.facts):
                    if isinstance(fact, str) and not fact.startswith("enc:"):
                        entry.facts[i] = self._encrypt_value(fact)
                        migrated_count += 1

        if migrated_count > 0:
            LOGGER.info(
                "encryption_migrated fields=%d entities=%d",
                migrated_count,
                len(self._by_id),
            )

        return migrated_count

    async def load(self) -> None:
        async with self._lock:
            if not self._path.exists():
                await self._write_locked()
                return

            try:
                raw = await asyncio.to_thread(self._path.read_text, encoding="utf-8")
                payload = json.loads(raw or "{}")
            except json.JSONDecodeError as e:
                LOGGER.error("entity_memory_corrupted path=%s error=%s", self._path, e)
                raise
            except OSError as e:
                LOGGER.error(
                    "entity_memory_read_failed path=%s error=%s", self._path, e
                )
                raise

            # Check if encryption migration is needed
            needs_migration = self._needs_encryption_migration(payload)

            self._by_id = {
                str(user_id): self._entry_from_dict(item)
                for user_id, item in (payload.get("by_id") or {}).items()
                if isinstance(item, dict)
            }
            self._by_username = {}
            for username, item in (payload.get("by_username") or {}).items():
                if not isinstance(item, dict):
                    continue
                normalized_username = self._normalize_username(username)
                if not normalized_username:
                    continue
                self._by_username[normalized_username] = self._entry_from_dict(item)
            self._relink_locked()

            # Migrate plaintext data to encrypted if needed
            migration_completed = False
            if needs_migration and self._encryptor:
                migrated_count = await self._migrate_encryption()
                migration_completed = migrated_count > 0

            # Write with migration flag only if migration actually ran
            await self._write_locked(include_migration_flag=migration_completed)

    async def observe_user(
        self,
        *,
        user_id: int | None = None,
        username: str | None = None,
        display_name: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> None:
        if user_id is None and not username:
            return
        async with self._lock:
            entry = self._resolve_or_create_locked(user_id=user_id, username=username)
            changed = False
            normalized_username = self._normalize_username(username)
            if normalized_username and entry.username != normalized_username:
                entry.username = normalized_username
                changed = True
            normalized_display_name = self._normalize_text(display_name)
            if (
                normalized_display_name
                and entry.display_name != normalized_display_name
            ):
                entry.display_name = normalized_display_name
                changed = True
            normalized_first_name = self._normalize_text(first_name)
            if normalized_first_name and entry.first_name != normalized_first_name:
                entry.first_name = normalized_first_name
                changed = True
            normalized_last_name = self._normalize_text(last_name)
            if normalized_last_name and entry.last_name != normalized_last_name:
                entry.last_name = normalized_last_name
                changed = True
            if changed:
                entry.updated_at = datetime.now(timezone.utc).isoformat()
                self._bind_username_locked(entry)
                await self._write_locked()

    async def remember_fact(
        self,
        *,
        fact: str,
        user_id: int | None = None,
        username: str | None = None,
        display_name: str | None = None,
    ) -> EntityMemoryEntry:
        normalized_fact = self._normalize_fact(fact)
        if not normalized_fact:
            raise ValueError("fact_required")
        async with self._lock:
            entry = self._resolve_or_create_locked(user_id=user_id, username=username)
            if display_name:
                entry.display_name = (
                    self._normalize_text(display_name) or entry.display_name
                )
            if username:
                entry.username = self._normalize_username(username) or entry.username
            self._apply_fact_to_entry_locked(entry, normalized_fact)
            entry.updated_at = datetime.now(timezone.utc).isoformat()
            self._bind_username_locked(entry)
            await self._write_locked()
            return copy.deepcopy(entry)

    async def build_context_for_query(self, query: str) -> str:
        references = self.extract_references(query)
        if not references:
            return ""
        async with self._lock:
            lines: list[str] = []
            used: set[int] = set()
            for entry, fallback in self._iter_entries_for_references_locked(references):
                entry_key = id(entry)
                if entry_key in used:
                    continue
                used.add(entry_key)
                profile_lines = self._render_entry_lines(
                    self._label_for_entry(entry, fallback), entry
                )
                if profile_lines:
                    lines.extend(profile_lines)
            if not lines:
                return ""
            return "Known profile info about mentioned people:\n" + "\n".join(lines)

    async def get_entries_for_query(self, query: str) -> list[tuple[str, list[str]]]:
        references = self.extract_references(query)
        if not references:
            return []
        async with self._lock:
            results: list[tuple[str, list[str]]] = []
            used: set[int] = set()
            for entry, fallback in self._iter_entries_for_references_locked(references):
                entry_key = id(entry)
                if entry_key in used:
                    continue
                used.add(entry_key)
                label = self._label_for_entry(entry, fallback)
                # Use all available info, not just facts
                details = self._render_profile_details(entry)
                if not details:
                    # Entry exists but has no rendered details â€” show at least the label
                    details = (
                        [f"username: @{entry.username.lstrip('@')}"]
                        if entry.username
                        else [f"ID: {fallback}"]
                    )
                results.append((label, details))
            return results

    async def build_context_for_target(
        self,
        *,
        user_id: int | None = None,
        username: str | None = None,
    ) -> str:
        async with self._lock:
            entry = None
            fallback = None
            if user_id is not None:
                entry = self._by_id.get(str(user_id))
                fallback = f"user_id {user_id}"
            if entry is None and username:
                normalized_username = self._normalize_username(username)
                if normalized_username:
                    entry = self._by_username.get(normalized_username)
                fallback = f"@{username}"
            if entry is None:
                return ""
            label = self._label_for_entry(entry, fallback or "this person")
            lines = self._render_entry_lines(label, entry)
            if not lines:
                return ""
            return "Known profile info about the current person:\n" + "\n".join(lines)

    async def get_all_entries(self) -> list[tuple[str, list[str]]]:
        """Return all known people with their facts. Used for memory export."""
        async with self._lock:
            results: list[tuple[str, list[str]]] = []
            seen: set[str] = set()
            for entry in list(self._by_id.values()) + list(self._by_username.values()):
                key = id(entry)
                key_str = str(key)
                if key_str in seen:
                    continue
                seen.add(key_str)
                label = self._label_for_entry(entry, "unknown")
                details = self._render_profile_details(entry)
                if details:
                    results.append((label, details))
            return results

    async def get_all_entries_raw(self) -> dict[str, EntityMemoryEntry]:
        """Return all entries keyed by user_id string. Used for user panel."""
        async with self._lock:
            return {uid: copy.deepcopy(entry) for uid, entry in self._by_id.items()}

    async def cleanup_stale_entries(self, *, max_age_days: int = 30) -> int:
        """Remove entries with only username and no interaction for max_age_days. Returns count removed."""
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        async with self._lock:
            to_remove_ids: list[str] = []
            to_remove_usernames: list[str] = []
            for uid, entry in self._by_id.items():
                details = self._render_profile_details(entry)
                username_only = len(details) <= 1 and (
                    not details or details[0].startswith("username:")
                )
                if not username_only:
                    continue
                updated = entry.updated_at
                if updated:
                    try:
                        upd_dt = datetime.fromisoformat(updated)
                        if upd_dt.tzinfo is None:
                            upd_dt = upd_dt.replace(tzinfo=timezone.utc)
                        if upd_dt > cutoff:
                            continue
                    except Exception:
                        pass
                to_remove_ids.append(uid)
                if entry.username:
                    norm = self._normalize_username(entry.username)
                    if norm:
                        to_remove_usernames.append(norm)
            for uid in to_remove_ids:
                self._by_id.pop(uid, None)
            for uname in to_remove_usernames:
                self._by_username.pop(uname, None)
            if to_remove_ids:
                await self._write_locked()
        return len(to_remove_ids)

    async def clear_all(self) -> bool:
        async with self._lock:
            had_anything = bool(self._by_id or self._by_username)
            self._by_id = {}
            self._by_username = {}
            if had_anything:
                await self._write_locked()
            return had_anything

    @staticmethod
    def extract_references(text: str | None) -> dict[str, list]:
        sample = str(text or "")
        user_ids: list[int] = []
        seen_ids: set[int] = set()
        for match in USER_ID_RE.finditer(sample):
            try:
                user_id = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if user_id in seen_ids:
                continue
            seen_ids.add(user_id)
            user_ids.append(user_id)
        usernames: list[str] = []
        seen_usernames: set[str] = set()
        for match in USERNAME_RE.finditer(sample):
            username = match.group(1)
            if not username:
                continue
            normalized = username.casefold()
            if normalized in seen_usernames:
                continue
            seen_usernames.add(normalized)
            usernames.append(username)
        return {"user_ids": user_ids, "usernames": usernames}

    def _iter_entries_for_references_locked(self, references: dict[str, list]):
        for user_id in references["user_ids"]:
            entry = self._by_id.get(str(user_id))
            if entry is not None:
                yield entry, f"user_id {user_id}"
        for username in references["usernames"]:
            normalized_username = self._normalize_username(username)
            if not normalized_username:
                continue
            entry = self._by_username.get(normalized_username)
            if entry is not None:
                yield entry, f"@{username}"

    def _resolve_or_create_locked(
        self, *, user_id: int | None, username: str | None
    ) -> EntityMemoryEntry:
        normalized_username = self._normalize_username(username)
        entry = None
        if user_id is not None:
            entry = self._by_id.get(str(user_id))
        if entry is None and normalized_username:
            entry = self._by_username.get(normalized_username)
        if entry is None:
            entry = EntityMemoryEntry()
        if user_id is not None:
            self._by_id[str(user_id)] = entry
        if normalized_username:
            self._by_username[normalized_username] = entry
        return entry

    def _bind_username_locked(self, entry: EntityMemoryEntry) -> None:
        normalized_username = self._normalize_username(entry.username)
        if normalized_username:
            self._by_username[normalized_username] = entry

    def _apply_fact_to_entry_locked(self, entry: EntityMemoryEntry, fact: str) -> None:
        website = self._extract_website(fact)
        if website:
            entry.website = self._encrypt_value(website)
        age = self._extract_age(fact)
        if age is not None:
            entry.age = self._encrypt_value(str(age))
        name = self._extract_name(fact)
        if name:
            if not entry.display_name:
                entry.display_name = name
            full_name_parts = name.split()
            if full_name_parts and not entry.first_name:
                entry.first_name = full_name_parts[0]
            if len(full_name_parts) > 1 and not entry.last_name:
                entry.last_name = " ".join(full_name_parts[1:])
        username = self._extract_username(fact)
        if username:
            entry.username = username
        location = self._extract_location(fact)
        if location:
            entry.location = self._encrypt_value(location)

        cleaned_fact = fact
        if website:
            cleaned_fact = cleaned_fact.replace(website, " ").strip()
        if name and len(name) >= 3:
            cleaned_fact = re.sub(
                re.escape(name), " ", cleaned_fact, flags=re.IGNORECASE
            )
        cleaned_fact = " ".join(cleaned_fact.split()).strip(" ,.;:-")
        if cleaned_fact and not self._looks_like_bare_profile_field(cleaned_fact):
            entry.facts = self._append_fact(
                entry.facts, self._encrypt_value(cleaned_fact)
            )

    def _looks_like_bare_profile_field(self, text: str) -> bool:
        lowered = text.casefold()
        markers = (
            "name",
            "username",
            "user name",
            "site",
            "website",
            "url",
            "Ð²Ð¾Ð·Ñ€Ð°ÑÑ‚",
            "Ð¸Ð¼Ñ",
            "Ð·Ð¾Ð²ÑƒÑ‚",
            "ÑÐ°Ð¹Ñ‚",
            "Ð»ÐµÑ‚",
            "Ð³Ð¾Ð´",
            "age",
            "Ð¶Ð¸Ð²ÐµÑ‚",
            "Ð¶Ð¸Ð²ÐµÑ‚",
            "from",
            "lives in",
            "Ð¸Ð·",
        )
        return (
            any(marker in lowered for marker in markers) and len(lowered.split()) <= 6
        )

    def _extract_age(self, text: str) -> int | None:
        for pattern in AGE_PATTERNS:
            match = pattern.search(text)
            if match is None:
                continue
            try:
                age = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if 1 <= age <= 120:
                return age
        return None

    def _extract_name(self, text: str) -> str | None:
        for pattern in NAME_PATTERNS:
            match = pattern.search(text)
            if match is None:
                continue
            value = self._normalize_text(match.group(1))
            if value and len(value) >= 2:
                return value
        return None

    def _extract_username(self, text: str) -> str | None:
        match = USERNAME_RE.search(text)
        if match is None:
            return None
        return self._normalize_username(match.group(1))

    def _extract_website(self, text: str) -> str | None:
        for pattern in WEBSITE_PATTERNS:
            match = pattern.search(text)
            if match is None:
                continue
            value = self._normalize_website(match.group(1))
            if value:
                return value
        match = URL_RE.search(text)
        if match is None:
            return None
        return self._normalize_website(match.group(0))

    def _extract_location(self, text: str) -> str | None:
        for pattern in LOCATION_PATTERNS:
            match = pattern.search(text)
            if match is None:
                continue
            value = self._normalize_text(match.group(1))
            if value:
                return value
        return None

    def _append_fact(self, current: list[str], fact: str) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in [*(current or []), fact]:
            cleaned = self._normalize_fact(item)
            if not cleaned:
                continue
            lowered = cleaned.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(cleaned)
        if len(normalized) > MAX_FACTS_PER_ENTITY:
            normalized = normalized[-MAX_FACTS_PER_ENTITY:]
        return normalized

    def _render_entry_lines(self, label: str, entry: EntityMemoryEntry) -> list[str]:
        details = self._render_profile_details(entry)
        if not details:
            return []
        return [f"{label}:"] + [f"- {item}" for item in details]

    def _render_profile_details(self, entry: EntityMemoryEntry) -> list[str]:
        details: list[str] = []
        full_name = self._full_name(entry)
        if full_name and (
            not entry.display_name
            or full_name.casefold() != entry.display_name.casefold()
        ):
            details.append(f"name: {full_name}")
        if entry.username:
            details.append(f"username: @{entry.username.lstrip('@')}")
        if entry.age is not None:
            details.append(f"age: {entry.age}")
        if entry.website:
            details.append(f"website: {entry.website}")
        if entry.location:
            details.append(f"location: {entry.location}")
        if entry.bio:
            details.append(f"bio: {entry.bio}")
        for fact in entry.facts[-6:]:
            details.append(f"note: {fact}")
        return details

    def _label_for_entry(self, entry: EntityMemoryEntry, fallback: str) -> str:
        if entry.display_name and entry.username:
            return f"{entry.display_name} (@{entry.username.lstrip('@')})"
        if entry.display_name:
            return entry.display_name
        full_name = self._full_name(entry)
        if full_name:
            return full_name
        if entry.username:
            return f"@{entry.username.lstrip('@')}"
        return fallback

    def _full_name(self, entry: EntityMemoryEntry) -> str | None:
        full_name = " ".join(
            part for part in [entry.first_name, entry.last_name] if part
        ).strip()
        return full_name or None

    def _normalize_fact(self, text: str) -> str:
        return " ".join(str(text or "").split()).strip()

    def _normalize_text(self, text: str | None) -> str | None:
        cleaned = " ".join(str(text or "").split()).strip(" ,.;:-")
        return cleaned or None

    def _normalize_username(self, username: str | None) -> str | None:
        if not username:
            return None
        cleaned = str(username).strip().lstrip("@").casefold()
        return cleaned or None

    def _normalize_website(self, website: str | None) -> str | None:
        cleaned = self._normalize_text(website)
        if not cleaned:
            return None
        if cleaned.lower().startswith("www."):
            return f"https://{cleaned}"
        return cleaned

    def _entry_from_dict(self, data: dict) -> EntityMemoryEntry:
        # Ð Ð°ÑÑˆÐ¸Ñ„Ñ€Ð¾Ð²ÐºÐ° Ñ‡ÑƒÐ²ÑÑ‚Ð²Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ñ‹Ñ… Ð¿Ð¾Ð»ÐµÐ¹ Ð¿Ñ€Ð¸ Ñ‡Ñ‚ÐµÐ½Ð¸Ð¸
        location = self._decrypt_value(data.get("location"))
        bio = self._decrypt_value(data.get("bio"))
        website = self._decrypt_value(data.get("website"))
        age = self._decrypt_value(data.get("age"))
        facts = self._decrypt_list(data.get("facts") or [])

        return EntityMemoryEntry(
            username=self._normalize_username(data.get("username")),
            display_name=self._normalize_text(data.get("display_name")),
            first_name=self._normalize_text(data.get("first_name")),
            last_name=self._normalize_text(data.get("last_name")),
            age=self._coerce_age(age),
            website=self._normalize_website(website),
            location=self._normalize_text(location),
            bio=self._normalize_text(bio),
            facts=[
                self._normalize_fact(item)
                for item in facts
                if self._normalize_fact(item)
            ],
            updated_at=data.get("updated_at"),
        )

    def _coerce_age(self, value) -> int | None:
        try:
            age = int(value)
        except (TypeError, ValueError):
            return None
        return age if 1 <= age <= 120 else None

    def _relink_locked(self) -> None:
        by_username: dict[str, EntityMemoryEntry] = {}
        for entry in self._by_id.values():
            normalized_username = self._normalize_username(entry.username)
            if normalized_username:
                by_username[normalized_username] = entry
        for username, entry in list(self._by_username.items()):
            normalized_username = self._normalize_username(
                username
            ) or self._normalize_username(entry.username)
            if not normalized_username:
                continue
            if normalized_username not in by_username:
                by_username[normalized_username] = entry
        self._by_username = by_username

    async def _write_locked(self, include_migration_flag: bool = False) -> None:
        """Write data to disk.

        Args:
            include_migration_flag: If True, add _migration.encryption_v1 flag.
                                   Only set when migration actually completed.
        """
        payload = {
            "by_id": {key: asdict(value) for key, value in self._by_id.items()},
            "by_username": {
                key: asdict(value) for key, value in self._by_username.items()
            },
        }

        # Preserve existing _migration flag if it exists in the file
        if self._path.exists():
            try:
                existing_raw = await asyncio.to_thread(
                    self._path.read_text, encoding="utf-8"
                )
                existing = json.loads(existing_raw or "{}")
                if "_migration" in existing:
                    payload["_migration"] = existing["_migration"]
            except (json.JSONDecodeError, OSError):
                pass  # If we can't read existing file, just don't preserve

        # Add migration flag if migration just completed
        if include_migration_flag:
            payload["_migration"] = {
                "encryption_v1": True,
                "migrated_at": datetime.now(timezone.utc).isoformat(),
            }

        await atomic_write_json(self._path, payload, indent=2)

