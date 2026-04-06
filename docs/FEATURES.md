# Features

This document explains what the project can do in practice. It is written from the product/user point of view, not from the file/class point of view.

## 1. What this project is

This project is a multi-surface Telegram assistant stack built around:
- an owner-side `userbot`
- a private `control bot`
- an optional public `chat bot`
- a stricter `visitor` mode for public sessions

The system combines AI, memory, Telegram actions, moderation, scheduling, live-data lookup, and persistent runtime state.

## 2. Main ways to use it

The owner can interact with the system mainly through three userbot modes:
- `.b` as the main/default AI mode
- `.d` as the planning, explanation, helper, and reminder mode
- `.k` as the direct Telegram action mode

Typical usage:
- use `.b` to ask the assistant to solve something directly
- use `.d` to ask how to do something, what mode to use, or which `.k` command should be sent
- use `.k` when you want the Telegram operation itself

Examples:
- `.b summarize this conversation and suggest a reply`
- `.d what .k command should I use to delete this chat`
- `.k archive this chat`

## 3. What the owner-side assistant can do

In normal owner use, the project can:
- answer questions
- summarize chats and messages
- rewrite text in different tones
- draft replies
- explain options and next steps
- help decide how to respond in a conversation
- work with chat context, memory, and style
- use live web/search/weather/rates information when enabled
- interpret images and transcribe audio

It also understands the difference between:
- ordinary AI help
- planning/explaining how to do something
- executing a Telegram-side action

## 4. What `.b` can do

`.b` is the main AI mode. It is the best default mode for most owner tasks.

It can:
- answer a direct question
- summarize a chat or thread
- rewrite a draft
- produce a stronger, softer, shorter, or clearer reply
- explain what another person wants
- generate message drafts
- use memory and runtime context to answer more personally
- use live-data and web-grounding when the request needs current information
- process image-based and audio-based prompts when supported

Examples:
- `.b answer this politely but briefly`
- `.b make this reply firmer`
- `.b what does this person want from me`
- `.b summarize the important points from this chat`

## 5. What `.d` can do

`.d` is the dialogue/helper/planning mode.

It can:
- explain how to do something in the system
- tell you whether to use `.b`, `.d`, `.k`, the control bot, or stored memory
- convert an intention into the correct `.k` command
- help plan a sequence of actions before execution
- help with reminders and scheduled tasks
- act as a safer "talk it through first" mode before running direct commands

Examples:
- `.d what is the best way to clean up this chat`
- `.d what .k command should I send to mute this chat`
- `.d explain how to do this through Telegram action mode`
- `.d remind me tomorrow at 10 to review this thread`

## 6. What `.k` can do

`.k` is the direct Telegram action mode.

It can perform or prepare Telegram-side operations such as:
- sending messages and media
- replying to messages
- editing own messages
- deleting messages
- forwarding or copying messages
- reacting, pinning, unpinning
- marking chats as read
- archiving or unarchiving chats
- clearing history or deleting a dialog
- looking up chat/user/member information
- joining or leaving chats
- managing invite links and join requests
- creating groups and channels
- moderating members
- changing chat title/description/photo
- managing personal contacts

Examples:
- `.k send this message to @example_user`
- `.k delete this message`
- `.k pin this message`
- `.k create a new group with these users`

## 7. Telegram action capabilities

The Telegram action layer is one of the biggest parts of the project. It supports:

Message and media operations:
- send text
- send photos, videos, video notes, GIFs, documents, audio, voice, stickers
- send media groups/albums
- send contacts, locations, venues, polls, dice/game emoji
- reply to a specific message
- comment on a channel post through the linked discussion chat
- send to a linked discussion chat or linked channel

Edit and cleanup operations:
- edit your own message
- edit captions
- replace media in a message
- edit or clear inline buttons
- delete one message
- delete multiple messages
- clear accessible history
- delete or remove the full dialog from the owner account where possible

Forwarding and copying:
- forward messages
- copy messages
- forward/copy into linked chats

Read and inspect operations:
- get recent chat history
- inspect chat info
- inspect user info
- inspect members of a chat
- inspect one specific member
- inspect linked chat information
- inspect comments on a channel post
- read information from the replied message
- save or reuse a selected target
- generate a draft or preview before sending

Chat and membership operations:
- join a chat/channel/invite link
- leave a chat
- archive or unarchive a chat
- mark a chat as read
- create invite links
- edit/revoke invite links
- approve/decline join requests
- create a group
- create a channel

Moderation/admin operations:
- block/unblock a user at account level
- ban/unban a member in a chat
- restrict/unrestrict a member
- promote/demote an admin
- set a custom admin title
- change default chat permissions
- change chat title, description, and photo

Contact-book operations:
- add a contact
- rename/update a contact
- delete a contact

## 8. Cross-chat capabilities

The system can also work across chats, not only in the current one.

Cross-chat features include:
- sending something to another chat or user by reference
- searching across dialogs
- finding a message by content
- finding a related channel/discussion chat
- forwarding the latest relevant message
- looking for text/photo/voice content
- using transcription and image-summary signals to improve search
- building compact documentation/summaries of a chat from recent messages

This is useful for workflows like:
- "find the last voice message about X"
- "send this answer to the selected target"
- "forward the newest matching message to another chat"

## 9. Memory and personalization

The project has several memory layers, each with a different purpose.

It can keep:
- owner knowledge
- owner directives/rules
- shared reusable memory
- memory about people/entities
- user profiles
- writing-style profiles
- relationship-style patterns

In practice this means the system can:
- remember long-lived owner preferences
- remember instructions like "reply more formally to this person"
- remember facts about recurring people or entities
- infer and reuse tone/style patterns
- adapt responses to the owner, the target user, and the relationship between them
- maintain special targets and close-contact settings

## 10. Auto-reply and chat behavior control

The project is not only command-driven. It can also behave automatically.

Auto-reply capabilities include:
- enabling/disabling auto replies globally
- per-chat probability controls
- per-chat cooldowns and reply delays
- per-chat hourly reply limits
- audience filters
- special-target behavior
- reply-only-to-questions mode
- owner-mention-or-context requirement
- duplicate suppression
- silence heuristics
- business-like filtering
- follow-up detection

This allows the owner to run the assistant in a more passive or more active way depending on the chat.

## 11. Reminders, schedule, and monitoring

The project includes automation beyond normal chat replies.

It can:
- create reminders
- parse time-based owner requests
- schedule one-time tasks
- schedule repeating tasks
- run timers
- detect reminder-like intent even from less formal phrasing
- keep scheduled tasks across restarts
- run monitor rules against incoming text
- build notifications when a monitor rule is triggered

## 12. Live-data and web capabilities

When enabled, the assistant can enrich answers with fresh external information.

Supported live-data areas:
- weather
- exchange rates
- web search
- news-like search routing
- page fetching for grounding
- location resolution
- caching of live results

This means the assistant can answer requests like:
- current weather in a location
- a currency quote
- a recent search-backed answer
- a grounded reply using fetched web pages

## 13. AI capabilities

The AI subsystem does more than a single text completion.

It supports:
- text generation
- multi-model fallback
- task-aware model selection
- judge-model arbitration
- output validation and cleanup
- wrong-language detection
- malformed/truncated answer detection
- reasoning-leak filtering
- voice transcription
- image/vision input handling

The system is designed to choose and validate responses rather than blindly return the first model output.

## 14. Public chat bot capabilities

The optional public bot can:
- start a public conversation
- show help
- clear conversation state
- answer text/photo/voice inputs
- enforce whitelist or owner-only access
- notify the owner when needed
- hand users into visitor mode

The owner also gets helper commands around the public bot for visitor operations.

## 15. Visitor mode capabilities

Visitor mode is a separate public-facing experience with stricter boundaries than normal owner use.

It can:
- start and end visitor sessions
- keep temporary visitor history
- route questions by category
- moderate abusive or low-signal messages
- apply rate limits and cooldowns
- temporarily block problematic users
- keep FAQ shortcuts
- escalate a visitor question to the owner inbox
- let the owner reply back to that visitor
- decide when a visitor response needs additional review
- generate public cards such as owner info, links, projects, collaboration, FAQ, capabilities
- search portfolio/web/GitHub sources for public-facing answers
- enforce a public-source policy
- expose visitor stats/admin controls
- send broadcasts to active visitor sessions

Visitor mode is designed as a controlled consultation-like flow, not just a generic chatbot.

## 16. Control bot capabilities

The private control bot is the operations panel for the project.

It can:
- show health state
- switch models
- enable/disable models
- toggle runtime flags
- manage audience filters
- manage auto-reply behavior
- manage allowed/blocked chats
- adjust per-chat settings
- manage special targets and close contacts
- inspect users in panels

This is the owner's runtime control surface without editing local files manually.

## 17. Safety, identity, and boundaries

The project explicitly manages sensitive boundaries.

It can:
- recognize identity questions
- force correct identity answers
- detect wrong identity claims
- refuse non-owner authority or threat scenarios
- classify risky/sensitive prompts
- restrict disclosure of secrets/private information
- restrict what public answers may cite or reveal
- validate outgoing AI text before it is shown

## 18. Reliability and persistence

The system includes infrastructure to keep it stable and stateful.

It supports:
- persistent JSON and SQLite storage
- atomic writes
- backup management for JSON data
- health checks and uptime tracking
- structured logging
- rate limiting
- scheduler persistence
- encrypted fields for selected storage
- local migration helpers for state/profile storage

## 19. Public-version limitation

The public repository keeps the architecture and logic, but removes:
- real secrets
- real Telegram sessions
- private owner data
- real runtime JSON/SQLite state
- logs and caches

So the public version shows what the project can do, but you still need your own credentials and your own local runtime state to use it.
