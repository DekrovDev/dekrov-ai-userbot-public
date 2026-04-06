"""Миграция state.json → SQLite.

Однократный скрипт для переноса данных из JSON в SQLite.
"""

import json
import logging
from pathlib import Path

from infra.state_sqlite import StateSQLite

LOGGER = logging.getLogger(__name__)


def migrate_state_json_to_sqlite(json_path: Path, db_path: Path) -> bool:
    """Мигрировать state.json в SQLite.

    Args:
        json_path: Путь к state.json
        db_path: Путь к SQLite БД

    Returns:
        True если миграция успешна
    """
    if not json_path.exists():
        LOGGER.info("state.json не найден, пропускаю миграцию")
        return True

    try:
        raw = json_path.read_text(encoding='utf-8')
        data = json.loads(raw or '{}')
    except (json.JSONDecodeError, OSError) as e:
        LOGGER.error(f"Ошибка чтения state.json: {e}")
        return False

    sqlite = StateSQLite(db_path)

    try:
        # Проверяем, была ли уже миграция
        if sqlite.get_metadata('state_migrated') == 'true':
            LOGGER.info("Миграция уже была выполнена")
            sqlite.close()
            return True

        migrated_count = 0

        # Мигрируем простые ключи конфигурации
        simple_keys = [
            'active_model', 'judge_model', 'available_models',
            'enabled_models', 'fallback_enabled', 'ai_mode_enabled',
            'response_style_mode', 'command_mode_enabled',
            'trigger_aliases', 'dot_prefix_required', 'auto_reply_enabled',
            'reply_audience_mode', 'reply_audience_flags',
            'chat_bot_allowed_user_ids', 'reply_only_questions',
            'chat_bot_owner_only', 'require_owner_mention_or_context',
            'allowed_chat_ids', 'blocked_chat_ids', 'chat_settings',
            'last_limits', 'models_refreshed_at', 'updated_at',
        ]

        for key in simple_keys:
            if key in data:
                sqlite.set_config(key, data[key])
                migrated_count += 1

        # Мигрируем chat_runtime
        chat_runtime = data.get('chat_runtime', {})
        for chat_id, runtime_data in chat_runtime.items():
            sqlite.set_chat_runtime(str(chat_id), runtime_data)
            migrated_count += 1

        # Мигрируем model_limits
        model_limits = data.get('model_limits', {})
        for model_name, limit_data in model_limits.items():
            sqlite.set_model_limit(model_name, limit_data)
            migrated_count += 1

        # Помечаем миграцию выполненной
        sqlite.set_metadata('state_migrated', 'true')
        sqlite.set_metadata('state_migrated_count', str(migrated_count))

        LOGGER.info(f"Миграция state.json завершена: {migrated_count} записей")
        return True

    except Exception as e:
        LOGGER.error(f"Ошибка миграции: {e}")
        return False

    finally:
        sqlite.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    base_dir = Path(__file__).parent.parent
    json_path = base_dir / 'data' / 'state.json'
    db_path = base_dir / 'data' / 'state.db'

    success = migrate_state_json_to_sqlite(json_path, db_path)
    exit(0 if success else 1)
