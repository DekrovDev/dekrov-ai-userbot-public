# Setup

## 1. What this project is

This project is a Telegram automation stack with:
- a `userbot` on the owner's Telegram account,
- a private `control bot` with an admin panel,
- an optional public `chat bot`,
- persistent memory/state stores in local files,
- optional live data tools for weather, rates, search, and news,
- visitor mode for public-facing conversations.

## 2. Prerequisites

Install these first:
- Python 3.11 or newer
- `pip`
- a Telegram account for the userbot
- Telegram API credentials from `https://my.telegram.org`
- a bot token from `@BotFather` for the control bot
- a Groq API key

Optional:
- a second bot token for `CHAT_BOT_TOKEN`
- a GitHub token for GitHub search
- `tgcrypto` build prerequisites if your platform needs compilation

## 3. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd telegram-ai-assistant-public
```

## 4. Create a virtual environment

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

## 5. Install dependencies

```bash
pip install -r requirements.txt
```

## 6. Create `.env`

Copy the example file:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

Then fill at least these fields:
- `API_ID`
- `API_HASH`
- `CONTROL_BOT_TOKEN`
- `GROQ_API_KEY`
- `OWNER_USER_ID`

If you want the public chat bot too, also fill:
- `CHAT_BOT_TOKEN`

## 7. Prepare data files

Create the `data` directory if it does not exist:

```bash
mkdir data
```

Then create your local owner knowledge file from the safe template:

Windows PowerShell:

```powershell
Copy-Item data\owner_knowledge.example.md data\owner_knowledge.md
```

Linux/macOS:

```bash
cp data/owner_knowledge.example.md data/owner_knowledge.md
```

Do not commit `data/owner_knowledge.md`. It is meant to become private local content.

The rest of the runtime files are auto-created on first start:
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

## 8. Run the project

```bash
python main.py
```

On the first run, Pyrogram will ask you to authorize the Telegram userbot account. You will need:
- the phone number of the Telegram account,
- the login code,
- and 2FA password if that account uses one.

## 9. Verify startup

Normal startup means:
- no immediate traceback in the terminal,
- `userbot` starts and logs in,
- `control bot` starts,
- `chat bot` starts only if `CHAT_BOT_TOKEN` is set,
- the `data/` directory gets populated with runtime files,
- `logs/` may be created automatically.

You can verify behavior by:
- opening the control bot in Telegram and sending `/start`,
- using owner commands in Telegram once the userbot session is active,
- checking that `data/state.json` or `data/state.db` appeared.

## 10. Main command surfaces

Owner command modes:
- `.d` for dialogue/planning/reminders/memory actions
- `.k` for Telegram actions
- `.b` for AI tasks

Control bot:
- `/start` opens the admin panel
- `/health` shows runtime checks

Chat bot:
- `/start`
- `/help`
- `/clear`

## 11. Public-version limitations

This repository will not fully work until you provide your own private local values:
- Telegram credentials
- bot tokens
- Groq API key
- owner identity and owner knowledge
- runtime data generated after first launch

Removed from the public version:
- real `.env`
- Telegram sessions
- runtime databases and JSON state
- logs
- caches and temp files
- personal docs and deployment examples with private paths

## 12. Next reading

- [`CONFIG.md`](CONFIG.md)
- [`ARCHITECTURE.md`](ARCHITECTURE.md)
