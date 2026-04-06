"""Миграция шифрования для entity_memory.json.

Шифрует чувствительные поля в существующих данных.
"""

import json
import logging
import os
from pathlib import Path

from infra.crypto.encryptor import Encryptor
from infra.crypto.key_manager import KeyManager

LOGGER = logging.getLogger(__name__)

# Поля для шифрования в entity_memory
ENCRYPTED_FIELDS = ["location", "bio", "age", "website"]


def _load_env_file(env_path: Path) -> None:
    """Загрузить переменные из .env файла."""
    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def encrypt_entity_memory(
    json_path: Path,
    dry_run: bool = False,
) -> int:
    """Зашифровать чувствительные поля в entity_memory.json.

    Args:
        json_path: Путь к entity_memory.json
        dry_run: Если True, не записывать изменения

    Returns:
        Количество зашифрованных полей
    """
    km = KeyManager()
    encryptor = Encryptor(km.key)

    if not json_path.exists():
        LOGGER.info("entity_memory.json не найден")
        return 0

    try:
        raw = json_path.read_text(encoding="utf-8")
        data = json.loads(raw or "{}")
    except (json.JSONDecodeError, OSError) as e:
        LOGGER.error(f"Ошибка чтения entity_memory.json: {e}")
        return 0

    encrypted_count = 0
    already_encrypted = 0

    # Шифрование by_id
    by_id = data.get("by_id", {})
    for user_id, entry in by_id.items():
        if not isinstance(entry, dict):
            continue

        # Шифрование чувствительных полей
        for field_name in ENCRYPTED_FIELDS:
            if field_name in entry and entry[field_name] is not None:
                value = entry[field_name]

                # Проверка уже зашифровано ли
                if isinstance(value, str) and value.startswith("enc:"):
                    already_encrypted += 1
                    continue

                # Шифрование
                entry[field_name] = "enc:" + encryptor.encrypt(str(value))
                encrypted_count += 1

        # Шифрование фактов
        facts = entry.get("facts", [])
        for i, fact in enumerate(facts):
            if isinstance(fact, str) and fact.startswith("enc:"):
                already_encrypted += 1
                continue

            facts[i] = "enc:" + encryptor.encrypt(fact)
            encrypted_count += 1

    if dry_run:
        LOGGER.info(
            f"Dry run: {encrypted_count} полей будут зашифрованы, "
            f"{already_encrypted} уже зашифрованы"
        )
        return encrypted_count

    # Запись зашифрованных данных
    try:
        json_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        LOGGER.info(
            f"Шифрование завершено: {encrypted_count} полей зашифровано, "
            f"{already_encrypted} уже были зашифрованы"
        )
    except OSError as e:
        LOGGER.error(f"Ошибка записи entity_memory.json: {e}")
        return 0

    return encrypted_count


def decrypt_entity_memory(
    json_path: Path,
    dry_run: bool = False,
) -> int:
    """Расшифровать поля в entity_memory.json (для отката).

    Args:
        json_path: Путь к entity_memory.json
        dry_run: Если True, не записывать изменения

    Returns:
        Количество расшифрованных полей
    """
    km = KeyManager()
    encryptor = Encryptor(km.key)

    if not json_path.exists():
        LOGGER.info("entity_memory.json не найден")
        return 0

    try:
        raw = json_path.read_text(encoding="utf-8")
        data = json.loads(raw or "{}")
    except (json.JSONDecodeError, OSError) as e:
        LOGGER.error(f"Ошибка чтения entity_memory.json: {e}")
        return 0

    decrypted_count = 0

    # Расшифрование by_id
    by_id = data.get("by_id", {})
    for user_id, entry in by_id.items():
        if not isinstance(entry, dict):
            continue

        # Расшифрование чувствительных полей
        for field_name in ENCRYPTED_FIELDS:
            if field_name in entry and entry[field_name] is not None:
                value = entry[field_name]

                if not (isinstance(value, str) and value.startswith("enc:")):
                    continue

                try:
                    entry[field_name] = encryptor.decrypt(value[4:])
                    decrypted_count += 1
                except ValueError:
                    LOGGER.warning(
                        f"Не удалось расшифровать {field_name} для {user_id}"
                    )

        # Расшифрование фактов
        facts = entry.get("facts", [])
        for i, fact in enumerate(facts):
            if not (isinstance(fact, str) and fact.startswith("enc:")):
                continue

            try:
                facts[i] = encryptor.decrypt(fact[4:])
                decrypted_count += 1
            except ValueError:
                LOGGER.warning(f"Не удалось расшифровать факт для {user_id}")

    if dry_run:
        LOGGER.info(f"Dry run: {decrypted_count} полей будут расшифрованы")
        return decrypted_count

    # Запись расшифрованных данных
    try:
        json_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        LOGGER.info(f"Расшифрование завершено: {decrypted_count} полей расшифровано")
    except OSError as e:
        LOGGER.error(f"Ошибка записи entity_memory.json: {e}")
        return 0

    return decrypted_count


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    base_dir = Path(__file__).parent.parent.parent

    # Загрузить .env файл для ENCRYPTION_KEY
    env_path = base_dir / ".env"
    _load_env_file(env_path)

    json_path = base_dir / "data" / "entity_memory.json"

    if len(sys.argv) > 1 and sys.argv[1] == "--decrypt":
        count = decrypt_entity_memory(json_path, dry_run="--dry" in sys.argv)
        LOGGER.info(f"Расшифровано: {count} полей")
    else:
        count = encrypt_entity_memory(json_path, dry_run="--dry" in sys.argv)
        LOGGER.info(f"Зашифровано: {count} полей")
