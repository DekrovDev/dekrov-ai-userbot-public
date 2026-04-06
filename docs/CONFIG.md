# Config

## Required environment variables

`API_ID`
- Telegram API ID from `my.telegram.org`

`API_HASH`
- Telegram API hash from `my.telegram.org`

`CONTROL_BOT_TOKEN`
- Bot token for the private control bot

`GROQ_API_KEY`
- API key used for LLM completions and transcription

`OWNER_USER_ID`
- Numeric Telegram user ID of the account owner

## Optional environment variables

`CHAT_BOT_TOKEN`
- Enables the separate public bot interface

`GITHUB_TOKEN`
- Improves GitHub API access for search features

`ASSISTANT_NAME`
- Public-facing assistant name override

`CREATOR_NAME`
- Public-facing owner label override

`CREATOR_CHANNEL`
- Public-facing contact channel shown in identity-related responses

## Important behavioral flags

`STRICT_OUTGOING_ONLY`
- Limits sensitive owner-command handling to safer directions

`ALLOW_INCOMING_TRIGGER_COMMANDS`
- Allows trigger-based handling on incoming messages

`COMMAND_TRIGGER_ALIASES`
- Legacy trigger aliases for direct bot invocation

`COMMAND_DOT_PREFIX_REQUIRED`
- Forces the dot-prefixed command style

`DEFAULT_RESPONSE_STYLE_MODE`
- One of the supported response styles, for example `NORMAL`

`LIVE_DATA_ENABLED`
- Enables the live weather/rates/search/news tools

`VISITOR_MODE_ENABLED`
- Enables the public visitor flow in the chat bot

## Local files you should customize

`data/owner_knowledge.md`
- Private knowledge file for the local owner

`data/*.json`, `data/*.db`
- Runtime state generated automatically

`data/*.session`
- Telegram session files created automatically after login

## Public-template placeholders

These values are intentionally fake and must be replaced locally:
- `12345678`
- `0123456789abcdef0123456789abcdef`
- `1234567890:replace_with_control_bot_token`
- `gsk_replace_with_groq_key`
- `https://example.com`
- `https://t.me/example_owner`
- `https://t.me/example_channel`
- `owner@example.com`
