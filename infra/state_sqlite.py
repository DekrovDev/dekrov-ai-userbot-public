"""SQLite-хранилище состояния.

Заменяет state.json для хранения конфигурации и runtime-данных.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from infra.sqlite_store import SQLiteStore


class StateSQLite(SQLiteStore):
    """SQLite-бэкенд для хранилища состояния."""

    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path)
        self._create_tables()

    def _create_tables(self) -> None:
        """Создать таблицы схемы."""
        self._execute("""
            CREATE TABLE IF NOT EXISTS state_config (
                key TEXT PRIMARY KEY,
                value JSON NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)

        self._execute("""
            CREATE TABLE IF NOT EXISTS chat_runtime (
                chat_id TEXT PRIMARY KEY,
                last_reply_at TEXT,
                last_message_at TEXT,
                last_message_fingerprint TEXT,
                replies_sent_total INTEGER DEFAULT 0,
                consecutive_ai_replies INTEGER DEFAULT 0,
                last_reply_target_user_id TEXT,
                recent_reply_timestamps JSON DEFAULT '[]',
                user_reply_timestamps JSON DEFAULT '{}',
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)

        self._execute("""
            CREATE TABLE IF NOT EXISTS model_limits (
                model_name TEXT PRIMARY KEY,
                remaining_requests INTEGER,
                request_limit INTEGER,
                remaining_tokens INTEGER,
                token_limit INTEGER,
                retry_after TEXT,
                last_updated TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)

        self._execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)

    # ──────────────────────────────────────────────────────────────────────
    # State config (ключ-значение)
    # ──────────────────────────────────────────────────────────────────────

    def get_config(self, key: str) -> Any | None:
        """Получить значение конфигурации."""
        row = self._fetchone(
            "SELECT value FROM state_config WHERE key = ?", (key,)
        )
        if row is None:
            return None
        return json.loads(row['value'])

    def set_config(self, key: str, value: Any) -> None:
        """Установить значение конфигурации."""
        self._upsert(
            'state_config',
            'key',
            key,
            {'value': json.dumps(value), 'updated_at': _now_iso()},
        )

    def get_all_config(self) -> dict[str, Any]:
        """Получить всю конфигурацию."""
        rows = self._fetchall("SELECT key, value FROM state_config")
        return {row['key']: json.loads(row['value']) for row in rows}

    # ──────────────────────────────────────────────────────────────────────
    # Chat runtime
    # ──────────────────────────────────────────────────────────────────────

    def get_chat_runtime(self, chat_id: str) -> dict[str, Any] | None:
        """Получить runtime-данные чата."""
        row = self._fetchone(
            "SELECT * FROM chat_runtime WHERE chat_id = ?", (chat_id,)
        )
        if row is None:
            return None

        return {
            'last_reply_at': row['last_reply_at'],
            'last_message_at': row['last_message_at'],
            'last_message_fingerprint': row['last_message_fingerprint'],
            'replies_sent_total': row['replies_sent_total'] or 0,
            'consecutive_ai_replies': row['consecutive_ai_replies'] or 0,
            'last_reply_target_user_id': row['last_reply_target_user_id'],
            'recent_reply_timestamps': json.loads(
                row['recent_reply_timestamps'] or '[]'
            ),
            'user_reply_timestamps': json.loads(
                row['user_reply_timestamps'] or '{}'
            ),
        }

    def set_chat_runtime(self, chat_id: str, data: dict[str, Any]) -> None:
        """Установить runtime-данные чата."""
        self._upsert(
            'chat_runtime',
            'chat_id',
            chat_id,
            {
                'last_reply_at': data.get('last_reply_at'),
                'last_message_at': data.get('last_message_at'),
                'last_message_fingerprint': data.get('last_message_fingerprint'),
                'replies_sent_total': data.get('replies_sent_total', 0),
                'consecutive_ai_replies': data.get('consecutive_ai_replies', 0),
                'last_reply_target_user_id': data.get('last_reply_target_user_id'),
                'recent_reply_timestamps': json.dumps(
                    data.get('recent_reply_timestamps', [])
                ),
                'user_reply_timestamps': json.dumps(
                    data.get('user_reply_timestamps', {})
                ),
                'updated_at': _now_iso(),
            },
        )

    def get_all_chat_runtime(self) -> dict[str, dict[str, Any]]:
        """Получить все runtime-данные чатов."""
        rows = self._fetchall("SELECT * FROM chat_runtime")
        result = {}
        for row in rows:
            result[row['chat_id']] = {
                'last_reply_at': row['last_reply_at'],
                'last_message_at': row['last_message_at'],
                'last_message_fingerprint': row['last_message_fingerprint'],
                'replies_sent_total': row['replies_sent_total'] or 0,
                'consecutive_ai_replies': row['consecutive_ai_replies'] or 0,
                'last_reply_target_user_id': row['last_reply_target_user_id'],
                'recent_reply_timestamps': json.loads(
                    row['recent_reply_timestamps'] or '[]'
                ),
                'user_reply_timestamps': json.loads(
                    row['user_reply_timestamps'] or '{}'
                ),
            }
        return result

    # ──────────────────────────────────────────────────────────────────────
    # Model limits
    # ──────────────────────────────────────────────────────────────────────

    def get_model_limit(self, model_name: str) -> dict[str, Any] | None:
        """Получить лимиты модели."""
        row = self._fetchone(
            "SELECT * FROM model_limits WHERE model_name = ?", (model_name,)
        )
        if row is None:
            return None

        return {
            'model': row['model_name'],
            'remaining_requests': row['remaining_requests'],
            'request_limit': row['request_limit'],
            'remaining_tokens': row['remaining_tokens'],
            'token_limit': row['token_limit'],
            'retry_after': row['retry_after'],
            'last_updated': row['last_updated'],
        }

    def set_model_limit(self, model_name: str, data: dict[str, Any]) -> None:
        """Установить лимиты модели."""
        self._upsert(
            'model_limits',
            'model_name',
            model_name,
            {
                'remaining_requests': data.get('remaining_requests'),
                'request_limit': data.get('request_limit'),
                'remaining_tokens': data.get('remaining_tokens'),
                'token_limit': data.get('token_limit'),
                'retry_after': data.get('retry_after'),
                'last_updated': data.get('last_updated'),
                'updated_at': _now_iso(),
            },
        )

    def get_all_model_limits(self) -> dict[str, dict[str, Any]]:
        """Получить все лимиты моделей."""
        rows = self._fetchall("SELECT * FROM model_limits")
        return {
            row['model_name']: {
                'model': row['model_name'],
                'remaining_requests': row['remaining_requests'],
                'request_limit': row['request_limit'],
                'remaining_tokens': row['remaining_tokens'],
                'token_limit': row['token_limit'],
                'retry_after': row['retry_after'],
                'last_updated': row['last_updated'],
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
