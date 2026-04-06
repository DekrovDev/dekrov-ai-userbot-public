"""Миграция entity_memory.json и user_profiles.json → SQLite.

Однократный скрипт для переноса данных из JSON в SQLite.
"""

import json
import logging
from pathlib import Path

from infra.profiles_sqlite import ProfilesSQLite

LOGGER = logging.getLogger(__name__)


def migrate_profiles_json_to_sqlite(
    entity_json_path: Path,
    profiles_json_path: Path,
    db_path: Path,
) -> bool:
    """Мигрировать entity_memory.json и user_profiles.json в SQLite.

    Args:
        entity_json_path: Путь к entity_memory.json
        profiles_json_path: Путь к user_profiles.json
        db_path: Путь к SQLite БД

    Returns:
        True если миграция успешна
    """
    sqlite = ProfilesSQLite(db_path)

    try:
        # Проверяем, была ли уже миграция
        if sqlite.get_metadata("profiles_migrated") == "true":
            LOGGER.info("Миграция профилей уже была выполнена")
            sqlite.close()
            return True

        migrated_count = 0

        # ──────────────────────────────────────────────────────────────────
        # Мигрируем entity_memory.json
        # ──────────────────────────────────────────────────────────────────
        if entity_json_path.exists():
            try:
                raw = entity_json_path.read_text(encoding="utf-8")
                entity_data = json.loads(raw or "{}")
            except (json.JSONDecodeError, OSError) as e:
                LOGGER.error(f"Ошибка чтения entity_memory.json: {e}")
                entity_data = {}

            # Мигрируем by_id
            by_id = entity_data.get("by_id", {})
            for user_id, entry in by_id.items():
                if not isinstance(entry, dict):
                    continue

                sqlite.set_entity(
                    str(user_id),
                    {
                        "username": entry.get("username"),
                        "display_name": entry.get("display_name"),
                        "first_name": entry.get("first_name"),
                        "last_name": entry.get("last_name"),
                        "age": entry.get("age"),
                        "website": entry.get("website"),
                        "location": entry.get("location"),
                        "bio": entry.get("bio"),
                        "updated_at": entry.get("updated_at"),
                    },
                )
                migrated_count += 1

                # Мигрируем факты
                facts = entry.get("facts", [])
                if facts:
                    sqlite.set_entity_facts(str(user_id), facts)
                    migrated_count += len(facts)

            # Мигрируем by_username (связь через entity_memory)
            # Факты уже привязаны к user_id, by_username используется для поиска

        # ──────────────────────────────────────────────────────────────────
        # Мигрируем user_profiles.json
        # ──────────────────────────────────────────────────────────────────
        if profiles_json_path.exists():
            try:
                raw = profiles_json_path.read_text(encoding="utf-8")
                profiles_data = json.loads(raw or "{}")
            except (json.JSONDecodeError, OSError) as e:
                LOGGER.error(f"Ошибка чтения user_profiles.json: {e}")
                profiles_data = {}

            # Мигрируем owner_profile (как user_profile с special flag)
            owner_profile = profiles_data.get("owner_profile", {})
            if owner_profile:
                # Owner profile не имеет user_id, пропускаем или сохраняем отдельно
                pass

            # Мигрируем user_profiles
            # Ключ может быть 'user_profiles' или 'profiles'
            user_profiles = profiles_data.get("user_profiles") or profiles_data.get(
                "profiles", {}
            )
            for user_id, profile in user_profiles.items():
                if not isinstance(profile, dict):
                    continue

                # Разделяем на profile и stats
                # Структура profiles.json отличается от style_profile.json
                profile_data = {
                    "user_id": user_id,
                    "username": profile.get("username"),
                    "avg_message_length": profile.get("avg_message_length"),
                    "tone": profile.get("typical_tone"),  # typical_tone -> tone
                    "verbosity": "medium",  # Нет в исходных данных
                    "profanity_tolerance": "low",  # Нет в исходных данных
                    "humor_level": "low",  # Нет в исходных данных
                    "formality": "low",  # Нет в исходных данных
                    "punctuation_style": "light",  # Нет в исходных данных
                    "emoji_usage": "low",  # Нет в исходных данных
                    "common_topics": profile.get("common_topics", []),
                    "last_updated": profile.get(
                        "last_interaction_time"
                    ),  # last_interaction_time -> last_updated
                    "sample_size": profile.get(
                        "message_count", 0
                    ),  # message_count -> sample_size
                }

                stats_data = {
                    "message_count": profile.get("message_count", 0),
                    "avg_message_length": profile.get("avg_message_length"),
                    "typical_tone": profile.get("typical_tone"),
                    "interaction_frequency": profile.get("interaction_frequency", 0.0),
                    "last_interaction_at": profile.get("last_interaction_time"),
                }

                sqlite.set_user_profile(str(user_id), profile_data)
                sqlite.set_user_stats(str(user_id), stats_data)
                migrated_count += 2

        # Помечаем миграцию выполненной
        sqlite.set_metadata("profiles_migrated", "true")
        sqlite.set_metadata("profiles_migrated_count", str(migrated_count))

        LOGGER.info(f"Миграция профилей завершена: {migrated_count} записей")
        return True

    except Exception as e:
        LOGGER.error(f"Ошибка миграции: {e}")
        return False

    finally:
        sqlite.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    base_dir = Path(__file__).parent.parent
    entity_json_path = base_dir / "data" / "entity_memory.json"
    profiles_json_path = base_dir / "data" / "user_profiles.json"
    db_path = base_dir / "data" / "profiles.db"

    success = migrate_profiles_json_to_sqlite(
        entity_json_path,
        profiles_json_path,
        db_path,
    )
    exit(0 if success else 1)
