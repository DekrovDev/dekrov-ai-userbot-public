"""Ð£Ð¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ Ð±ÑÐºÐ°Ð¿Ð°Ð¼Ð¸ JSON-Ñ„Ð°Ð¹Ð»Ð¾Ð².

ÐŸÐ¾Ð´Ð´ÐµÑ€Ð¶Ð¸Ð²Ð°ÐµÑ‚:
- Ð¡Ð¾Ð·Ð´Ð°Ð½Ð¸Ðµ Ð±ÑÐºÐ°Ð¿Ð° Ð¿ÐµÑ€ÐµÐ´ Ð·Ð°Ð¿Ð¸ÑÑŒÑŽ
- Ð¥Ñ€Ð°Ð½ÐµÐ½Ð¸Ðµ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ñ… N Ð±ÑÐºÐ°Ð¿Ð¾Ð²
- ÐžÑ‡Ð¸ÑÑ‚ÐºÐ° ÑÑ‚Ð°Ñ€Ñ‹Ñ… Ð±ÑÐºÐ°Ð¿Ð¾Ð²
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List

LOGGER = logging.getLogger("assistant.backup")


class JsonBackupManager:
    """ÐœÐµÐ½ÐµÐ´Ð¶ÐµÑ€ Ð±ÑÐºÐ°Ð¿Ð¾Ð² JSON-Ñ„Ð°Ð¹Ð»Ð¾Ð².

    ÐŸÑ€Ð¸Ð¼ÐµÑ€ Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ð½Ð¸Ñ:
        backup_manager = JsonBackupManager(
            backup_dir=Path("data/backups"),
            max_backups=5,
        )
        await backup_manager.create_backup(Path("data/state.json"))
    """

    def __init__(
        self,
        backup_dir: Path | None = None,
        max_backups: int = 5,
        enabled: bool = True,
    ) -> None:
        self._backup_dir = backup_dir
        self._max_backups = max_backups
        self._enabled = enabled

    def _get_backup_path(self, source_path: Path) -> Path:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð¿ÑƒÑ‚ÑŒ Ð´Ð»Ñ Ð±ÑÐºÐ°Ð¿Ð° Ñ„Ð°Ð¹Ð»Ð°."""
        if self._backup_dir is None:
            self._backup_dir = source_path.parent / "backups"

        self._backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        backup_filename = f"{source_path.name}.{timestamp}.bak"
        return self._backup_dir / backup_filename

    def _sync_create_backup(self, source_path: Path) -> Path | None:
        """Ð¡Ð¸Ð½Ñ…Ñ€Ð¾Ð½Ð½Ð°Ñ Ð²ÐµÑ€ÑÐ¸Ñ ÑÐ¾Ð·Ð´Ð°Ð½Ð¸Ñ Ð±ÑÐºÐ°Ð¿Ð°."""
        if not self._enabled:
            return None

        if not source_path.exists():
            LOGGER.debug("backup_skip_not_exists path=%s", source_path)
            return None

        try:
            backup_path = self._get_backup_path(source_path)
            shutil.copy2(source_path, backup_path)

            LOGGER.info("backup_created src=%s dst=%s", source_path, backup_path)

            # ÐžÑ‡Ð¸ÑÑ‚Ð¸Ñ‚ÑŒ ÑÑ‚Ð°Ñ€Ñ‹Ðµ Ð±ÑÐºÐ°Ð¿Ñ‹
            self._cleanup_old_backups(source_path.name)

            return backup_path

        except OSError as e:
            LOGGER.warning("backup_failed src=%s error=%s", source_path, e)
            return None

    async def create_backup(self, source_path: Path) -> Path | None:
        """Ð¡Ð¾Ð·Ð´Ð°Ñ‚ÑŒ Ð±ÑÐºÐ°Ð¿ Ñ„Ð°Ð¹Ð»Ð° (Ð°ÑÐ¸Ð½Ñ…Ñ€Ð¾Ð½Ð½Ð¾).

        Args:
            source_path: ÐŸÑƒÑ‚ÑŒ Ðº Ð¸ÑÑ…Ð¾Ð´Ð½Ð¾Ð¼Ñƒ Ñ„Ð°Ð¹Ð»Ñƒ

        Returns:
            ÐŸÑƒÑ‚ÑŒ Ðº Ð±ÑÐºÐ°Ð¿Ñƒ Ð¸Ð»Ð¸ None ÐµÑÐ»Ð¸ Ð±ÑÐºÐ°Ð¿ Ð½Ðµ ÑÐ¾Ð·Ð´Ð°Ð½
        """
        if not self._enabled:
            return None

        return await asyncio.to_thread(
            self._sync_create_backup, source_path
        )

    def _get_backup_files(self, source_filename: str) -> List[Path]:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº Ð±ÑÐºÐ°Ð¿Ð¾Ð² Ð´Ð»Ñ Ñ„Ð°Ð¹Ð»Ð°, Ð¾Ñ‚ÑÐ¾Ñ€Ñ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð½Ñ‹Ð¹ Ð¿Ð¾ Ð´Ð°Ñ‚Ðµ."""
        if self._backup_dir is None:
            return []

        if not self._backup_dir.exists():
            return []

        # ÐÐ°Ð¹Ñ‚Ð¸ Ð²ÑÐµ Ð±ÑÐºÐ°Ð¿Ñ‹ Ð´Ð»Ñ ÑÑ‚Ð¾Ð³Ð¾ Ñ„Ð°Ð¹Ð»Ð°
        pattern = f"{source_filename}.*.bak"
        backups = list(self._backup_dir.glob(pattern))

        # Ð¡Ð¾Ñ€Ñ‚Ð¸Ñ€Ð¾Ð²ÐºÐ° Ð¿Ð¾ Ð¸Ð¼ÐµÐ½Ð¸ (timestamp Ð² Ð¸Ð¼ÐµÐ½Ð¸)
        backups.sort(key=lambda p: p.name, reverse=True)

        return backups

    def _cleanup_old_backups(self, source_filename: str) -> int:
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ ÑÑ‚Ð°Ñ€Ñ‹Ðµ Ð±ÑÐºÐ°Ð¿Ñ‹, Ð¾ÑÑ‚Ð°Ð²Ð¸Ñ‚ÑŒ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ max_backups.

        Returns:
            ÐšÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾ ÑƒÐ´Ð°Ð»Ñ‘Ð½Ð½Ñ‹Ñ… Ð±ÑÐºÐ°Ð¿Ð¾Ð²
        """
        if self._backup_dir is None:
            return 0

        backups = self._get_backup_files(source_filename)

        removed = 0
        for backup_path in backups[self._max_backups:]:
            try:
                backup_path.unlink()
                LOGGER.debug("backup_removed path=%s", backup_path)
                removed += 1
            except OSError as e:
                LOGGER.warning("backup_remove_failed path=%s error=%s", backup_path, e)

        if removed > 0:
            LOGGER.info(
                "backup_cleanup_removed count=%d file=%s",
                removed,
                source_filename,
            )

        return removed

    def list_backups(self, source_filename: str) -> List[Path]:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÑŽÑ‰Ð¸Ñ… Ð±ÑÐºÐ°Ð¿Ð¾Ð²."""
        return self._get_backup_files(source_filename)

    def restore_latest(self, source_filename: str, target_path: Path) -> bool:
        """Ð’Ð¾ÑÑÑ‚Ð°Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ð¹ Ð±ÑÐºÐ°Ð¿.

        Args:
            source_filename: Ð˜Ð¼Ñ Ð¸ÑÑ…Ð¾Ð´Ð½Ð¾Ð³Ð¾ Ñ„Ð°Ð¹Ð»Ð°
            target_path: ÐŸÑƒÑ‚ÑŒ Ð´Ð»Ñ Ð²Ð¾ÑÑÑ‚Ð°Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ

        Returns:
            True ÐµÑÐ»Ð¸ Ð²Ð¾ÑÑÑ‚Ð°Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ ÑƒÑÐ¿ÐµÑˆÐ½Ð¾
        """
        backups = self._get_backup_files(source_filename)

        if not backups:
            LOGGER.warning("backup_restore_no_backups file=%s", source_filename)
            return False

        latest_backup = backups[0]  # ÐŸÐµÑ€Ð²Ñ‹Ð¹ = Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ð¹ (Ð¾Ñ‚ÑÐ¾Ñ€Ñ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½Ñ‹ reverse)

        try:
            shutil.copy2(latest_backup, target_path)
            LOGGER.info(
                "backup_restored src=%s dst=%s",
                latest_backup,
                target_path,
            )
            return True

        except OSError as e:
            LOGGER.error(
                "backup_restore_failed src=%s dst=%s error=%s",
                latest_backup,
                target_path,
                e,
            )
            return False

    def get_backup_size(self, source_filename: str) -> int:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾ Ð±ÑÐºÐ°Ð¿Ð¾Ð² Ð´Ð»Ñ Ñ„Ð°Ð¹Ð»Ð°."""
        return len(self._get_backup_files(source_filename))


# Ð“Ð»Ð¾Ð±Ð°Ð»ÑŒÐ½Ñ‹Ð¹ instance Ð´Ð»Ñ ÑƒÐ´Ð¾Ð±ÑÑ‚Ð²Ð°
_global_backup_manager: JsonBackupManager | None = None


def get_backup_manager() -> JsonBackupManager:
    """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð³Ð»Ð¾Ð±Ð°Ð»ÑŒÐ½Ñ‹Ð¹ backup manager."""
    global _global_backup_manager
    if _global_backup_manager is None:
        _global_backup_manager = JsonBackupManager()
    return _global_backup_manager


def set_backup_manager(manager: JsonBackupManager) -> None:
    """Ð£ÑÑ‚Ð°Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ Ð³Ð»Ð¾Ð±Ð°Ð»ÑŒÐ½Ñ‹Ð¹ backup manager."""
    global _global_backup_manager
    _global_backup_manager = manager

