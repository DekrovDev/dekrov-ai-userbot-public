# Architecture

## High-level layout

`main.py`
- Loads `.env`
- builds the dependency container
- initializes stores and service singletons
- starts `UserbotService`
- starts `ControlBotService`
- optionally starts `ChatBotService`

## Main runtime surfaces

`app/userbot_core.py`
- primary owner-facing Telegram account automation
- owner command handling
- auto-replies
- action execution
- reminders, memory, live grounding, moderation logic

`app/control_bot.py`
- private bot for runtime management
- model selection
- audience controls
- special targets
- visitor mode and whitelist management

`app/chat_bot.py`
- optional public bot surface
- standard chat history per user
- visitor-mode entrypoint
- owner admin helpers for the public bot

## State and persistence

`state/state.py`
- global runtime state
- model flags
- per-chat reply settings
- chat allow/block lists
- audience flags
- visitor mode flags
- dual-write JSON + SQLite behavior

`memory/`
- owner knowledge
- owner directives
- shared memory
- entity memory
- user profiles
- style profiles

## AI layer

`ai/groq_client.py`
- Groq/OpenAI-compatible client
- model fallback
- judge model path
- transcription
- vision
- response validation and rate-limit persistence

## Live data layer

`live/live_router.py`
- weather intent
- currency/rates intent
- news/search intent
- caching
- routing to dedicated tool modules

## Visitor layer

`visitor/`
- isolated public-facing flow
- routing
- moderation
- FAQ cache
- visitor session state
- owner inbox bridge
- public source policy

## Supporting infrastructure

`infra/`
- dependency container
- JSON atomic writes
- SQLite helpers
- scheduler
- rate limiter
- runtime context formatting
- Telegram compatibility helpers

## Public-version notes

Parts intentionally left as templates:
- owner identity defaults
- owner knowledge content
- contact links
- runtime data
- deployment-specific paths

Parts intentionally removed from the repository:
- `.env`
- `.session`
- generated JSON/DB state
- logs
- temporary test output
