"""Декораторы и утилиты для автоматического шифрования полей."""

from __future__ import annotations

from typing import Any, Callable


class EncryptedField:
    """Поле с автоматическим шифрованием.

    Пример использования:
        encryptor = Encryptor(key)
        encrypted_value = EncryptedField.encrypt_value(encryptor, location)
        decrypted_value = EncryptedField.decrypt_value(encryptor, encrypted_location)
    """

    @staticmethod
    def encrypt_value(encryptor: Encryptor, value: Any) -> Any:
        """Зашифровать значение.

        Args:
            encryptor: Экземпляр Encryptor
            value: Значение для шифрования

        Returns:
            Зашифрованное значение с префиксом "enc:"
        """
        if value is None:
            return None
        if isinstance(value, str) and value.startswith("enc:"):
            return value  # Уже зашифровано
        return "enc:" + encryptor.encrypt(value)

    @staticmethod
    def decrypt_value(encryptor: Encryptor, value: Any) -> Any:
        """Расшифровать значение.

        Args:
            encryptor: Экземпляр Encryptor
            value: Зашифрованное значение

        Returns:
            Расшифрованное значение
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.startswith("enc:"):
            return value  # Не зашифровано
        return encryptor.decrypt(value[4:])  # Remove "enc:" prefix

    @staticmethod
    def encrypt_list(encryptor: Encryptor, values: list[str]) -> list[str]:
        """Зашифровать список строк."""
        if not values:
            return values
        return [EncryptedField.encrypt_value(encryptor, v) for v in values]

    @staticmethod
    def decrypt_list(encryptor: Encryptor, values: list[str]) -> list[str]:
        """Расшифровать список строк."""
        if not values:
            return values
        return [EncryptedField.decrypt_value(encryptor, v) for v in values]


def encrypt_on_write(*field_names: str) -> Callable:
    """Декоратор для автоматического шифрования полей при записи.

    Пример:
        class EntityMemoryStore:
            @encrypt_on_write("location", "bio", "website")
            async def set_entity(self, user_id: str, data: dict):
                ...

    Args:
        *field_names: Имена полей для шифрования
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(self, *args, **kwargs):
            # Получить encryptor из self или создать
            encryptor = getattr(self, '_encryptor', None)
            if encryptor is None:
                return func(self, *args, **kwargs)

            # Шифрование полей в data
            if 'data' in kwargs and isinstance(kwargs['data'], dict):
                for fname in field_names:
                    if fname in kwargs['data']:
                        value = kwargs['data'][fname]
                        kwargs['data'][fname] = EncryptedField.encrypt_value(
                            encryptor, value
                        )

            # Шифрование facts если есть
            if 'data' in kwargs and isinstance(kwargs['data'], dict):
                if 'facts' in kwargs['data'] and kwargs['data']['facts']:
                    kwargs['data']['facts'] = EncryptedField.encrypt_list(
                        encryptor, kwargs['data']['facts']
                    )

            return func(self, *args, **kwargs)
        return wrapper
    return decorator


def decrypt_on_read(*field_names: str) -> Callable:
    """Декоратор для автоматического расшифрования полей при чтении.

    Пример:
        class EntityMemoryStore:
            @decrypt_on_read("location", "bio", "website")
            async def get_entity(self, user_id: str):
                ...

    Args:
        *field_names: Имена полей для расшифрования
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(self, *args, **kwargs):
            result = func(self, *args, **kwargs)

            # Получить encryptor из self
            encryptor = getattr(self, '_encryptor', None)
            if encryptor is None:
                return result

            # Расшифрование полей в результате
            if result is None:
                return result

            # Для dict результатов
            if isinstance(result, dict):
                for fname in field_names:
                    if fname in result:
                        result[fname] = EncryptedField.decrypt_value(
                            encryptor, result[fname]
                        )

                # Расшифрование facts если есть
                if 'facts' in result and result['facts']:
                    result['facts'] = EncryptedField.decrypt_list(
                        encryptor, result['facts']
                    )

            return result
        return wrapper
    return decorator


# Import Encryptor for type hints
from infra.crypto.encryptor import Encryptor  # noqa: E402
