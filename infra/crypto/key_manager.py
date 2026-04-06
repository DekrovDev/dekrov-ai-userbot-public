"""Управление ключами шифрования.

Поддерживает:
- Загрузка из environment переменной
- Загрузка из файла
- Генерация нового ключа
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.fernet import Fernet


class KeyManager:
    """Менеджер ключей шифрования.

    Поддерживает:
    - Загрузка из environment переменной
    - Загрузка из файла
    - Генерация нового ключа
    """

    ENV_VAR = "ENCRYPTION_KEY"

    def __init__(
        self,
        env_var: str | None = None,
        key_file: Path | None = None,
        auto_generate: bool = True,
    ) -> None:
        self._env_var = env_var or self.ENV_VAR
        self._key_file = key_file
        self._key: bytes | None = None

        if auto_generate:
            self._ensure_key_exists()

    def _ensure_key_exists(self) -> None:
        """Убедиться что ключ существует."""
        # 1. Проверить environment
        key_b64 = os.environ.get(self._env_var)
        if key_b64:
            self._key = base64.urlsafe_b64decode(key_b64)
            return

        # 2. Проверить файл
        if self._key_file and self._key_file.exists():
            key_b64 = self._key_file.read_text().strip()
            self._key = base64.urlsafe_b64decode(key_b64)
            return

        # 3. Сгенерировать новый
        if self._key_file:
            self._generate_and_save()

    def _generate_and_save(self) -> bytes:
        """Сгенерировать и сохранить ключ."""
        key = Fernet.generate_key()
        key_b64 = base64.urlsafe_b64encode(key).decode('ascii')

        self._key_file.parent.mkdir(parents=True, exist_ok=True)
        self._key_file.write_text(key_b64)
        os.chmod(self._key_file, 0o600)  # Только владелец

        self._key = key
        return key

    @property
    def key(self) -> bytes:
        """Получить ключ."""
        if self._key is None:
            self._ensure_key_exists()
        return self._key  # type: ignore

    @property
    def key_b64(self) -> str:
        """Получить ключ в base64."""
        return base64.urlsafe_b64encode(self.key).decode('ascii')

    @classmethod
    def generate_key(cls) -> str:
        """Сгенерировать новый ключ (для CLI)."""
        key = Fernet.generate_key()
        return base64.urlsafe_b64encode(key).decode('ascii')
