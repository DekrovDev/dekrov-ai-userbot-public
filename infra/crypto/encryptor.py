"""Простое шифрование на основе Fernet."""

from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class Encryptor:
    """Шифрование/дешифрование данных.

    Использует Fernet (AES-128-CBC + HMAC) для симметричного шифрования.
    """

    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    @classmethod
    def from_base64_key(cls, key_b64: str) -> Encryptor:
        """Создать из base64 ключа."""
        key = base64.urlsafe_b64decode(key_b64)
        return cls(key)

    def encrypt(self, data: str | dict | list) -> str:
        """Зашифровать данные.

        Args:
            data: Строка, dict или list для шифрования

        Returns:
            Base64 зашифрованные данные
        """
        if isinstance(data, (dict, list)):
            data = json.dumps(data, ensure_ascii=False)

        token = self._fernet.encrypt(data.encode('utf-8'))
        return base64.urlsafe_b64encode(token).decode('ascii')

    def decrypt(self, token: str) -> str:
        """Расшифровать данные.

        Args:
            token: Base64 зашифрованные данные

        Returns:
            Расшифрованная строка
        """
        try:
            raw = base64.urlsafe_b64decode(token.encode('ascii'))
            decrypted = self._fernet.decrypt(raw)
            return decrypted.decode('utf-8')
        except InvalidToken:
            raise ValueError("Invalid encryption token")

    def decrypt_json(self, token: str) -> dict | list:
        """Расшифровать и распарсить JSON."""
        return json.loads(self.decrypt(token))

    def is_encrypted(self, value: str) -> bool:
        """Проверить зашифровано ли значение."""
        return isinstance(value, str) and value.startswith("enc:")

    def encrypt_if_plain(self, data: str | dict | list | None) -> str | None:
        """Зашифровать если не зашифровано."""
        if data is None:
            return None
        if isinstance(data, str) and self.is_encrypted(data):
            return data
        return "enc:" + self.encrypt(data)

    def decrypt_if_encrypted(self, token: str | None) -> str | None:
        """Расшифровать если зашифровано."""
        if token is None:
            return None
        if not self.is_encrypted(token):
            return token
        return self.decrypt(token[4:])  # Remove "enc:" prefix
