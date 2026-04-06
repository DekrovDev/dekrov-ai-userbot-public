# Telegram AI Assistant

[Русская версия](README.ru.md)

Public, sanitized version of a Telegram automation project with three main interfaces:
- a `userbot` running under the owner's Telegram account,
- a private `control bot` for runtime management,
- an optional public `chat bot`,
- plus an isolated `visitor` flow for public conversations.

This repository was prepared for public GitHub release. Personal data, secrets, runtime state, local infrastructure details, and owner-specific content were removed or replaced with placeholders.

## Full instruction files

If you want full documentation instead of just a quick overview, read these files directly:
- [docs/SETUP.md](docs/SETUP.md) for step-by-step installation and launch
- [docs/CONFIG.md](docs/CONFIG.md) for `.env` and config variables
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for project structure
- [docs/FEATURES.md](docs/FEATURES.md) for a complete feature overview
- [docs/FUNCTIONS_CATALOG.md](docs/FUNCTIONS_CATALOG.md) for a practical catalog of what the project can do

## What the project does

The project combines several layers:
- Telegram `userbot` commands for messaging, planning, reminders, memory, and automation
- a private `control bot` for switching modes and managing runtime behavior
- an optional public-facing `chat bot`
- persistent local state in JSON and SQLite files
- optional live-data tools for weather, exchange rates, search, and news
- a visitor pipeline for public conversations with moderation and session handling

## Public-version limitations

This public repository does not include:
- real `.env` values
- bot tokens, API keys, session strings, cookies, passwords
- Telegram session files
- private owner knowledge and memory data
- runtime databases, JSON state, logs, caches, temp files
- personal contact details, identifiers, channels, or local machine paths

You must provide your own local values before the project can run normally.

## Repository structure

```text
actions/    Telegram action execution and command routing
ai/         model client and AI orchestration
app/        userbot, control bot, and chat bot runtime services
chat/       chat-related helpers
config/     settings, identity rules, prompt configuration
data/       local runtime state and private local knowledge files
docs/       setup, config, and architecture notes
infra/      storage, scheduler, runtime context, utility infrastructure
live/       live weather/rates/search/news integrations
memory/     owner/shared/entity/style memory handling
safety/     safety and disclosure boundaries
state/      runtime state management
visitor/    public visitor mode, moderation, inbox, policies, cards
main.py     application entry point
```

## Requirements

Install these before starting:
- Python 3.11 or newer
- `pip`
- a Telegram account for the userbot
- Telegram API credentials from `https://my.telegram.org`
- a bot token from `@BotFather` for the control bot
- a Groq API key

Optional:
- a second bot token for `CHAT_BOT_TOKEN`
- a GitHub token for GitHub-backed search features

## Quick start

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd telegram-ai-assistant-public
```

### 2. Create a virtual environment

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

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create `.env` from the template

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

Then open `.env` and replace the placeholder values.

Minimum required variables:
- `API_ID`
- `API_HASH`
- `CONTROL_BOT_TOKEN`
- `GROQ_API_KEY`
- `OWNER_USER_ID`

Optional but commonly used:
- `CHAT_BOT_TOKEN`
- `GITHUB_TOKEN`
- `ASSISTANT_NAME`
- `CREATOR_NAME`
- `CREATOR_CHANNEL`

### 5. Prepare local data files

The `data/` directory is already present in the repository, but runtime files are not committed.

Create your private owner knowledge file from the safe template.

Windows PowerShell:

```powershell
Copy-Item data\owner_knowledge.example.md data\owner_knowledge.md
```

Linux/macOS:

```bash
cp data/owner_knowledge.example.md data/owner_knowledge.md
```

After that, edit `data/owner_knowledge.md` with your own private local information. Do not commit that file.

Files generated automatically on first start usually include:
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

Telegram session files are also created automatically after login:
- `data/*.session`

### 6. Run the project

```bash
python main.py
```

On the first run, Pyrogram will request Telegram authorization for the userbot account. Be ready to enter:
- the phone number of the Telegram account,
- the login code sent by Telegram,
- the 2FA password, if enabled on that account.

## How to verify startup

Normal startup looks like this:
- the process starts without an immediate traceback
- the userbot login flow completes
- the control bot starts successfully
- the chat bot starts only if `CHAT_BOT_TOKEN` is set
- new runtime files appear in `data/`

Practical checks:
- open the control bot in Telegram and send `/start`
- use `/health` in the control bot if enabled
- verify that `data/state.json` or `data/state.db` was created
- confirm that Telegram session files appeared in `data/` after successful login

## Main command surfaces

### Userbot

Owner-side command families include:
- `.b` as the main/default AI mode for most normal work
- `.d` for dialogue, planning, clarification, reminders, and asking how to do something
- `.k` for direct Telegram actions and action-style commands

Recommended usage:
- use `.b` as the primary mode
- use `.d` to ask things like "what `.k` command should I send to do X?"
- use `.k` when you want the execution-oriented Telegram form directly

Examples:
- `.b write a short answer to this message`
- `.b summarize this chat situation`
- `.d what `.k` command should I use to remove this chat`
- `.d explain how to do this through Telegram action mode`
- `.k delete this chat`
- `.k mute this chat for 8 hours`

Exact command coverage depends on configuration and enabled modules.

### Control bot

Typical control bot entry points:
- `/start`
- `/health`

The control bot acts as the private runtime/admin surface.

Examples:
- `/start` to open the admin panel
- `/health` to verify the runtime is alive

### Chat bot

Typical public bot commands:
- `/start`
- `/help`
- `/clear`

The chat bot is optional and starts only when `CHAT_BOT_TOKEN` is configured.

Examples:
- `/start` to initialize the public conversation
- `/help` to show the user-facing command surface
- `/clear` to reset the current conversation where supported

### Visitor mode

Visitor mode is the stricter public conversation flow layered on top of the chat bot.

Examples of what it does:
- starts moderated visitor sessions
- keeps temporary visitor history
- can escalate difficult questions into the owner inbox
- can block spammy or abusive interactions
- can answer through safer public-source-oriented logic

## What was replaced with placeholders

This public version intentionally uses fake example values in files such as `.env.example`, config defaults, and template data. Examples:
- `12345678`
- `0123456789abcdef0123456789abcdef`
- `1234567890:replace_with_control_bot_token`
- `gsk_replace_with_groq_key`
- `@example_owner`
- `https://t.me/example_channel`
- generic owner/assistant labels instead of real personal names

## What will not work until you configure it locally

The project will not be usable as-is until you provide:
- your own Telegram API credentials
- your own bot tokens
- your own Groq API key
- your own `OWNER_USER_ID`
- your own local owner knowledge file
- fresh runtime files generated on your machine

Some behaviors also depend on local runtime state and will only appear after the first successful startup.

## Safety notes for publication

If you publish a fork of this repository, do not commit:
- `.env`
- anything inside `data/` except safe templates
- `*.session`
- logs
- caches
- generated SQLite and JSON runtime files

Use the included `.gitignore` as the default baseline, then review `git status` before every push.

## Additional documentation

- [docs/FEATURES.md](docs/FEATURES.md)
- [docs/FUNCTIONS_CATALOG.md](docs/FUNCTIONS_CATALOG.md)
- [docs/SETUP.md](docs/SETUP.md)
- [docs/CONFIG.md](docs/CONFIG.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
