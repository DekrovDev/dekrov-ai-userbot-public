"""Базовый слой для SQLite-хранилищ.

Обеспечивает потокобезопасные подключения и базовые операции.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any


class SQLiteStore:
    """Базовый класс для SQLite-хранилищ.

    Использует одно подключение на поток (thread-local) и WAL-режим
    для лучшей конкурентности.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_db()

    @property
    def _conn(self) -> sqlite3.Connection:
        """Получить подключение для текущего потока."""
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(
                str(self._db_path),
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
                timeout=30.0,
            )
            self._local.conn.row_factory = sqlite3.Row
            # Включаем внешние ключи
            self._local.conn.execute("PRAGMA foreign_keys = ON")
        return self._local.conn

    def _init_db(self) -> None:
        """Инициализировать БД (WAL-режим)."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path), timeout=30.0)
            try:
                # Enable foreign keys for this connection (table creation)
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.execute("PRAGMA cache_size = -64000")  # 64 MB
                conn.commit()
            finally:
                conn.close()

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Выполнить SQL-запрос."""
        return self._conn.execute(sql, params)

    def _fetchone(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        """Выполнить запрос и вернуть одну строку."""
        return self._execute(sql, params).fetchone()

    def _fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Выполнить запрос и вернуть все строки."""
        return self._execute(sql, params).fetchall()

    def _upsert(
        self, table: str, key_col: str, key_val: str, data: dict[str, Any]
    ) -> None:
        """UPSERT: INSERT OR REPLACE."""
        columns = ", ".join([key_col] + list(data.keys()))
        placeholders = ", ".join(["?"] * (1 + len(data)))
        update_cols = ", ".join(f"{k}=excluded.{k}" for k in data.keys())

        self._execute(
            f"""
            INSERT INTO {table} ({columns}) VALUES ({placeholders})
            ON CONFLICT({key_col}) DO UPDATE SET {update_cols}
        """,
            (key_val, *data.values()),
        )
        self._conn.commit()

    def _delete(self, table: str, key_col: str, key_val: str) -> None:
        """Удалить запись."""
        self._execute(f"DELETE FROM {table} WHERE {key_col} = ?", (key_val,))
        self._conn.commit()

    def close(self) -> None:
        """Закрыть подключение текущего потока."""
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            del self._local.conn
