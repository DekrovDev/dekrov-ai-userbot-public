"""Атомарная запись JSON-файлов с бэкапом.

Гарантирует целостность данных при сбоях питания/процесса.
Алгоритм:
  1. Создать бэкап существующего файла (если есть)
  2. Запись во временный файл (.tmp)
  3. fsync() для гарантии записи на диск
  4. Атомарное переименование (replace)

Кроссплатформенно: Windows + Linux + macOS.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from infra.json_backup import get_backup_manager


def _get_temp_path(path: Path) -> Path:
    """Создать путь к временному файлу в той же директории."""
    return path.with_suffix(path.suffix + ".tmp")


def _atomic_write_sync(path: Path, data: Any, indent: int = 2) -> None:
    """Синхронная атомарная запись JSON.

    Args:
        path: Целевой путь к файлу
        data: Данные для сериализации в JSON
        indent: Отступ для форматирования (default: 2)

    Raises:
        OSError: При ошибке записи на диск
        TypeError: При ошибке сериализации JSON
    """
    temp_path = _get_temp_path(path)
    payload = json.dumps(data, ensure_ascii=False, indent=indent)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            suffix=".tmp",
        ) as f:
            temp_path = Path(f.name)
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _atomic_write_text_sync(path: Path, text: str) -> None:
    """Синхронная атомарная запись текста.

    Args:
        path: Целевой путь к файлу
        text: Текст для записи

    Raises:
        OSError: При ошибке записи на диск
    """
    temp_path = _get_temp_path(path)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            suffix=".tmp",
        ) as f:
            temp_path = Path(f.name)
            f.write(text)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


async def _atomic_write_async(path: Path, data: Any, indent: int = 2) -> None:
    """Асинхронная атомарная запись JSON (через to_thread)."""
    await asyncio.to_thread(_atomic_write_sync, path, data, indent)


async def atomic_write_json(path: Path, data: Any, indent: int = 2) -> None:
    """Атомарно записать данные в JSON-файл с бэкапом.

    Args:
        path: Путь к файлу
        data: Данные для записи (сериализуемые в JSON)
        indent: Отступ для форматирования (default: 2)

    Example:
        >>> await atomic_write_json(Path("state.json"), {"key": "value"})
    """
    # Создать бэкап перед записью (неблокирующе)
    backup_manager = get_backup_manager()
    await backup_manager.create_backup(path)

    await _atomic_write_async(path, data, indent)


def atomic_write_json_sync(path: Path, data: Any, indent: int = 2) -> None:
    """Синхронно атомарно записать данные в JSON-файл с бэкапом.

    Args:
        path: Путь к файлу
        data: Данные для записи (сериализуемые в JSON)
        indent: Отступ для форматирования (default: 2)

    Example:
        >>> atomic_write_json_sync(Path("cache.json"), {"key": "value"})
    """
    # Создать бэкап перед записью
    backup_manager = get_backup_manager()
    backup_manager.create_backup(path)

    _atomic_write_sync(path, data, indent)


async def atomic_write_text(path: Path, text: str) -> None:
    """Атомарно записать текст в файл.

    Args:
        path: Путь к файлу
        text: Текст для записи

    Example:
        >>> await atomic_write_text(Path("config.txt"), "content")
    """
    await asyncio.to_thread(_atomic_write_text_sync, path, text)


def atomic_write_text_sync(path: Path, text: str) -> None:
    """Синхронно атомарно записать текст в файл.

    Args:
        path: Путь к файлу
        text: Текст для записи

    Example:
        >>> atomic_write_text_sync(Path("config.txt"), "content")
    """
    _atomic_write_text_sync(path, text)
