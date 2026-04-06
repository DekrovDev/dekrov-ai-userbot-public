"""SQLite-хранилище для entity_memory и user_profiles.

Заменяет entity_memory.json и user_profiles.json.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from infra.sqlite_store import SQLiteStore


class ProfilesSQLite(SQLiteStore):
    """SQLite-бэкенд для профилей пользователей и сущностей."""

    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path)
        self._create_tables()

    def _create_tables(self) -> None:
        """Создать таблицы схемы."""
        # Entity memory
        self._execute("""
            CREATE TABLE IF NOT EXISTS entity_memory (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                display_name TEXT,
                first_name TEXT,
                last_name TEXT,
                age INTEGER,
                website TEXT,
                location TEXT,
                bio TEXT,
                updated_at TEXT
            )
        """)

        # Entity facts
        self._execute("""
            CREATE TABLE IF NOT EXISTS entity_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                fact TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES entity_memory(user_id)
            )
        """)

        # User profiles
        self._execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                avg_message_length REAL,
                tone TEXT,
                verbosity TEXT,
                profanity_tolerance TEXT,
                humor_level TEXT,
                formality TEXT,
                punctuation_style TEXT,
                emoji_usage TEXT,
                common_topics JSON DEFAULT '[]',
                last_updated TEXT,
                sample_size INTEGER DEFAULT 0
            )
        """)

        # User stats
        self._execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id TEXT PRIMARY KEY,
                message_count INTEGER DEFAULT 0,
                avg_message_length REAL,
                typical_tone TEXT,
                interaction_frequency REAL,
                last_interaction_at TEXT
            )
        """)

        # Metadata
        self._execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Индексы
        self._execute("""
            CREATE INDEX IF NOT EXISTS idx_entity_facts_user 
            ON entity_facts(user_id)
        """)
        self._execute("""
            CREATE INDEX IF NOT EXISTS idx_user_profiles_tone 
            ON user_profiles(tone)
        """)
        self._execute("""
            CREATE INDEX IF NOT EXISTS idx_user_stats_last_interaction 
            ON user_stats(last_interaction_at)
        """)

    # ──────────────────────────────────────────────────────────────────────
    # Entity memory
    # ──────────────────────────────────────────────────────────────────────

    def get_entity(self, user_id: str) -> dict[str, Any] | None:
        """Получить сущность пользователя."""
        row = self._fetchone(
            "SELECT * FROM entity_memory WHERE user_id = ?", (user_id,)
        )
        if row is None:
            return None

        return {
            'username': row['username'],
            'display_name': row['display_name'],
            'first_name': row['first_name'],
            'last_name': row['last_name'],
            'age': row['age'],
            'website': row['website'],
            'location': row['location'],
            'bio': row['bio'],
            'updated_at': row['updated_at'],
        }

    def set_entity(self, user_id: str, data: dict[str, Any]) -> None:
        """Установить сущность пользователя."""
        self._upsert(
            'entity_memory',
            'user_id',
            user_id,
            {
                'username': data.get('username'),
                'display_name': data.get('display_name'),
                'first_name': data.get('first_name'),
                'last_name': data.get('last_name'),
                'age': data.get('age'),
                'website': data.get('website'),
                'location': data.get('location'),
                'bio': data.get('bio'),
                'updated_at': data.get('updated_at', _now_iso()),
            },
        )

    def get_all_entities(self) -> dict[str, dict[str, Any]]:
        """Получить все сущности."""
        rows = self._fetchall("SELECT * FROM entity_memory")
        return {
            row['user_id']: {
                'username': row['username'],
                'display_name': row['display_name'],
                'first_name': row['first_name'],
                'last_name': row['last_name'],
                'age': row['age'],
                'website': row['website'],
                'location': row['location'],
                'bio': row['bio'],
                'updated_at': row['updated_at'],
            }
            for row in rows
        }

    # ──────────────────────────────────────────────────────────────────────
    # Entity facts
    # ──────────────────────────────────────────────────────────────────────

    def get_entity_facts(self, user_id: str) -> list[str]:
        """Получить факты сущности."""
        rows = self._fetchall(
            "SELECT fact FROM entity_facts WHERE user_id = ? ORDER BY id",
            (user_id,),
        )
        return [row['fact'] for row in rows]

    def add_entity_fact(self, user_id: str, fact: str) -> None:
        """Добавить факт сущности."""
        self._execute(
            "INSERT INTO entity_facts (user_id, fact) VALUES (?, ?)",
            (user_id, fact),
        )
        self._conn.commit()

    def set_entity_facts(self, user_id: str, facts: list[str]) -> None:
        """Установить факты сущности (замена всех)."""
        self._execute("DELETE FROM entity_facts WHERE user_id = ?", (user_id,))
        for fact in facts:
            self._execute(
                "INSERT INTO entity_facts (user_id, fact) VALUES (?, ?)",
                (user_id, fact),
            )
        self._conn.commit()

    def get_all_entity_facts(self) -> dict[str, list[str]]:
        """Получить все факты по пользователям."""
        rows = self._fetchall(
            "SELECT user_id, fact FROM entity_facts ORDER BY user_id, id"
        )
        result: dict[str, list[str]] = {}
        for row in rows:
            result.setdefault(row['user_id'], []).append(row['fact'])
        return result

    # ──────────────────────────────────────────────────────────────────────
    # User profiles
    # ──────────────────────────────────────────────────────────────────────

    def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        """Получить профиль пользователя."""
        row = self._fetchone(
            "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
        )
        if row is None:
            return None

        return {
            'user_id': user_id,
            'username': row['username'],
            'avg_message_length': row['avg_message_length'],
            'tone': row['tone'],
            'verbosity': row['verbosity'],
            'profanity_tolerance': row['profanity_tolerance'],
            'humor_level': row['humor_level'],
            'formality': row['formality'],
            'punctuation_style': row['punctuation_style'],
            'emoji_usage': row['emoji_usage'],
            'common_topics': json.loads(row['common_topics'] or '[]'),
            'last_updated': row['last_updated'],
            'sample_size': row['sample_size'] or 0,
        }

    def set_user_profile(self, user_id: str, data: dict[str, Any]) -> None:
        """Установить профиль пользователя."""
        self._upsert(
            'user_profiles',
            'user_id',
            user_id,
            {
                'username': data.get('username'),
                'avg_message_length': data.get('avg_message_length'),
                'tone': data.get('tone'),
                'verbosity': data.get('verbosity'),
                'profanity_tolerance': data.get('profanity_tolerance'),
                'humor_level': data.get('humor_level'),
                'formality': data.get('formality'),
                'punctuation_style': data.get('punctuation_style'),
                'emoji_usage': data.get('emoji_usage'),
                'common_topics': json.dumps(data.get('common_topics', [])),
                'last_updated': data.get('last_updated', _now_iso()),
                'sample_size': data.get('sample_size', 0),
            },
        )

    def get_all_user_profiles(self) -> dict[str, dict[str, Any]]:
        """Получить все профили пользователей."""
        rows = self._fetchall("SELECT * FROM user_profiles")
        return {
            row['user_id']: {
                'user_id': row['user_id'],
                'username': row['username'],
                'avg_message_length': row['avg_message_length'],
                'tone': row['tone'],
                'verbosity': row['verbosity'],
                'profanity_tolerance': row['profanity_tolerance'],
                'humor_level': row['humor_level'],
                'formality': row['formality'],
                'punctuation_style': row['punctuation_style'],
                'emoji_usage': row['emoji_usage'],
                'common_topics': json.loads(row['common_topics'] or '[]'),
                'last_updated': row['last_updated'],
                'sample_size': row['sample_size'] or 0,
            }
            for row in rows
        }

    # ──────────────────────────────────────────────────────────────────────
    # User stats
    # ──────────────────────────────────────────────────────────────────────

    def get_user_stats(self, user_id: str) -> dict[str, Any] | None:
        """Получить статистику пользователя."""
        row = self._fetchone(
            "SELECT * FROM user_stats WHERE user_id = ?", (user_id,)
        )
        if row is None:
            return None

        return {
            'message_count': row['message_count'] or 0,
            'avg_message_length': row['avg_message_length'],
            'typical_tone': row['typical_tone'],
            'interaction_frequency': row['interaction_frequency'],
            'last_interaction_at': row['last_interaction_at'],
        }

    def set_user_stats(self, user_id: str, data: dict[str, Any]) -> None:
        """Установить статистику пользователя."""
        self._upsert(
            'user_stats',
            'user_id',
            user_id,
            {
                'message_count': data.get('message_count', 0),
                'avg_message_length': data.get('avg_message_length'),
                'typical_tone': data.get('typical_tone'),
                'interaction_frequency': data.get('interaction_frequency'),
                'last_interaction_at': data.get('last_interaction_at'),
            },
        )

    def get_all_user_stats(self) -> dict[str, dict[str, Any]]:
        """Получить всю статистику пользователей."""
        rows = self._fetchall("SELECT * FROM user_stats")
        return {
            row['user_id']: {
                'message_count': row['message_count'] or 0,
                'avg_message_length': row['avg_message_length'],
                'typical_tone': row['typical_tone'],
                'interaction_frequency': row['interaction_frequency'],
                'last_interaction_at': row['last_interaction_at'],
            }
            for row in rows
        }

    # ──────────────────────────────────────────────────────────────────────
    # Metadata
    # ──────────────────────────────────────────────────────────────────────

    def get_metadata(self, key: str) -> str | None:
        """Получить метаданные."""
        row = self._fetchone(
            "SELECT value FROM metadata WHERE key = ?", (key,)
        )
        return row['value'] if row else None

    def set_metadata(self, key: str, value: str) -> None:
        """Установить метаданные."""
        self._upsert('metadata', 'key', key, {'value': value, 'updated_at': _now_iso()})


def _now_iso() -> str:
    """Вернуть текущее время в ISO-формате."""
    return datetime.now(timezone.utc).isoformat()
