# Telegram AI Assistant

[English version](README.md)

Публичная, очищенная версия Telegram-проекта с тремя основными интерфейсами:
- `userbot`, работающий от Telegram-аккаунта владельца,
- приватный `control bot` для управления рантаймом,
- опциональный публичный `chat bot`,
- а также изолированный `visitor`-контур для публичных диалогов.

Этот репозиторий подготовлен для публикации на GitHub. Личные данные, секреты, рабочее состояние, детали локальной инфраструктуры и owner-specific содержимое удалены или заменены плейсхолдерами.

## Файлы с полными инструкциями

Если нужен не только краткий обзор, а полные инструкции, смотри эти файлы:
- [docs/SETUP.md](docs/SETUP.md) для пошаговой установки и запуска
- [docs/CONFIG.md](docs/CONFIG.md) для `.env` и переменных конфигурации
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) для структуры проекта
- [docs/FEATURES.ru.md](docs/FEATURES.ru.md) для полного обзора возможностей
- [docs/FUNCTIONS_CATALOG.ru.md](docs/FUNCTIONS_CATALOG.ru.md) для практического каталога функций проекта

## Что делает проект

Проект объединяет несколько слоев:
- команды `userbot` для сообщений, планирования, напоминаний, памяти и автоматизации
- приватный `control bot` для переключения режимов и управления поведением системы
- опциональный публичный `chat bot`
- локальное хранение состояния в JSON и SQLite
- опциональные live-data инструменты для погоды, курсов, поиска и новостей
- visitor-пайплайн для публичных разговоров с модерацией и сессиями

## Ограничения публичной версии

В этот публичный репозиторий не входят:
- реальные значения `.env`
- bot tokens, API keys, session strings, cookies, passwords
- Telegram session-файлы
- приватные owner knowledge и memory-данные
- runtime-базы, JSON-state, логи, кеши, временные файлы
- личные контакты, идентификаторы, каналы и локальные пути машины

До локальной настройки проект полноценно работать не будет.

## Структура репозитория

```text
actions/    исполнение Telegram-действий и роутинг команд
ai/         клиент модели и AI-оркестрация
app/        рантайм userbot, control bot и chat bot
chat/       chat-утилиты
config/     настройки, identity-правила, prompt-конфигурация
data/       локальное runtime-состояние и приватные локальные knowledge-файлы
docs/       setup, config и архитектурная документация
infra/      storage, scheduler, runtime context и инфраструктурные утилиты
live/       интеграции погоды, курсов, поиска и новостей
memory/     owner/shared/entity/style memory
safety/     safety-ограничения и защита от утечки данных
state/      управление runtime-state
visitor/    публичный visitor mode, модерация, inbox, policy, cards
main.py     точка входа приложения
```

## Что нужно установить заранее

Перед запуском установи:
- Python 3.11 или новее
- `pip`
- Telegram-аккаунт для userbot
- Telegram API credentials с `https://my.telegram.org`
- bot token от `@BotFather` для control bot
- Groq API key

Опционально:
- второй bot token для `CHAT_BOT_TOKEN`
- GitHub token для GitHub-based search функций

## Пошаговый запуск

### 1. Клонирование репозитория

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd telegram-ai-assistant-public
```

### 2. Создание виртуального окружения

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Создание `.env` из шаблона

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

После этого открой `.env` и замени плейсхолдеры на свои значения.

Минимально обязательные переменные:
- `API_ID`
- `API_HASH`
- `CONTROL_BOT_TOKEN`
- `GROQ_API_KEY`
- `OWNER_USER_ID`

Часто нужны дополнительно:
- `CHAT_BOT_TOKEN`
- `GITHUB_TOKEN`
- `ASSISTANT_NAME`
- `CREATOR_NAME`
- `CREATOR_CHANNEL`

### 5. Подготовка локальных файлов данных

Папка `data/` уже есть в репозитории, но runtime-файлы туда не коммитятся.

Создай локальный приватный owner knowledge-файл из безопасного шаблона.

Windows PowerShell:

```powershell
Copy-Item data\owner_knowledge.example.md data\owner_knowledge.md
```

Linux/macOS:

```bash
cp data/owner_knowledge.example.md data/owner_knowledge.md
```

После этого отредактируй `data/owner_knowledge.md`, заполнив его своими локальными данными. Этот файл нельзя коммитить.

При первом запуске автоматически обычно создаются:
- `data/state.json`
- `data/state.db`
- `data/user_profiles.json`
- `data/shared_memory.json`
- `data/entity_memory.json`
- `data/style_profile.json`
- `data/chat_config.json`
- `data/chat_topics.json`
- `data/scheduler.json`
- `data/monitor.json`
- `data/live_cache.json`

После авторизации также автоматически появятся Telegram session-файлы:
- `data/*.session`

### 6. Запуск проекта

```bash
python main.py
```

При первом старте Pyrogram попросит авторизовать Telegram-аккаунт для userbot. Нужны будут:
- номер телефона Telegram-аккаунта,
- код входа от Telegram,
- пароль 2FA, если он включен на аккаунте.

## Как проверить, что проект стартовал нормально

Нормальный старт выглядит так:
- процесс запускается без мгновенного traceback
- userbot проходит логин
- control bot успешно стартует
- chat bot стартует только если задан `CHAT_BOT_TOKEN`
- в `data/` появляются новые runtime-файлы

Практическая проверка:
- открой control bot в Telegram и отправь `/start`
- используй `/health` в control bot, если команда включена
- проверь, что появились `data/state.json` или `data/state.db`
- убедись, что после логина появились Telegram session-файлы в `data/`

## Основные поверхности команд

### Userbot

Основные семейства owner-команд:
- `.b` как основной/default AI-режим для большинства обычных задач
- `.d` для диалога, планирования, уточнений, напоминаний и вопросов "как это сделать"
- `.k` для прямых Telegram-действий и action-style команд

Рекомендуемое использование:
- `.b` использовать как основной режим
- `.d` использовать для вопросов вроде "какую `.k` команду отправить, чтобы сделать X?"
- `.k` использовать, когда нужна уже готовая форма действия для Telegram

Примеры:
- `.b ответь на это сообщение коротко и вежливо`
- `.b кратко объясни, что происходит в этом чате`
- `.d какую `.k` команду отправить, чтобы удалить этот чат`
- `.d объясни, как сделать это через режим Telegram-действий`
- `.k удалить этот чат`
- `.k замьютить этот чат на 8 часов`

Точное покрытие команд зависит от конфигурации и включенных модулей.

### Control bot

Типовые точки входа:
- `/start`
- `/health`

Это приватная admin/runtime-панель проекта.

Примеры:
- `/start` для открытия admin-панели
- `/health` для быстрой проверки, что рантайм жив

### Chat bot

Типовые публичные команды:
- `/start`
- `/help`
- `/clear`

`chat bot` опционален и стартует только если заполнен `CHAT_BOT_TOKEN`.

Примеры:
- `/start` для начала публичного диалога
- `/help` для списка пользовательских команд
- `/clear` для сброса текущего диалога там, где это поддерживается

### Visitor mode

Visitor mode — это более строгий публичный conversational flow поверх chat bot.

Примеры того, что он делает:
- запускает модерируемые visitor-сессии
- хранит временную visitor-историю
- может эскалировать сложные вопросы в owner inbox
- может блокировать spammy и abusive сценарии
- может отвечать через более безопасную public-source логику

## Что заменено плейсхолдерами

В публичной версии используются заведомо фейковые значения в `.env.example`, дефолтах конфигурации и шаблонах данных. Например:
- `12345678`
- `0123456789abcdef0123456789abcdef`
- `1234567890:replace_with_control_bot_token`
- `gsk_replace_with_groq_key`
- `@example_owner`
- `https://t.me/example_channel`
- generic owner/assistant labels вместо реальных имен

## Что не будет работать без локальной настройки

Проект не заработает из коробки, пока ты не добавишь:
- свои Telegram API credentials
- свои bot tokens
- свой Groq API key
- свой `OWNER_USER_ID`
- свой локальный `owner_knowledge.md`
- свежие runtime-файлы, созданные уже на твоей машине

Некоторые сценарии также зависят от локального runtime-state и проявятся только после первого успешного запуска.

## Что нельзя коммитить при публикации форка

Если будешь публиковать форк этого репозитория, не коммить:
- `.env`
- anything inside `data/` кроме безопасных шаблонов
- `*.session`
- логи
- кеши
- сгенерированные SQLite и JSON runtime-файлы

Используй приложенный `.gitignore` как базу и проверяй `git status` перед каждым `git push`.

## Дополнительная документация

- [docs/FEATURES.ru.md](docs/FEATURES.ru.md)
- [docs/FUNCTIONS_CATALOG.ru.md](docs/FUNCTIONS_CATALOG.ru.md)
- [docs/SETUP.md](docs/SETUP.md)
- [docs/CONFIG.md](docs/CONFIG.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
