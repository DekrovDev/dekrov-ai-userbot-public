# Functions Catalog

This document is the exhaustive capability catalog of the project. It does not describe implementation files. It describes what the system can actually do.

## 1. Owner workflows

The owner can use the project as:
- a direct AI assistant
- a Telegram action runner
- a planner/explainer for those actions
- a reminder/schedule assistant
- a memory-backed conversation assistant
- an auto-reply engine
- a runtime-controlled Telegram operator

## 2. Owner command modes

### `.b` as the main/default mode

Use `.b` when you want the assistant to solve the task directly.

It can:
- answer questions
- summarize chats
- summarize what another person wants
- rewrite a message in a different tone
- draft a reply
- suggest what to do next
- explain a situation
- analyze context from recent conversation history
- use stored memory and style information
- use live-data and web-grounding when needed
- work with image and audio inputs when the flow supports it

Typical examples:
- `.b summarize this chat`
- `.b answer this message shortly`
- `.b rewrite this to sound firmer`
- `.b what should I do next here`

### `.d` as helper/planning mode

Use `.d` when you want to think through the task before execution.

It can:
- explain how the system should be used
- tell you whether the task belongs to `.b`, `.d`, `.k`, control bot, or stored memory
- convert an intention into a `.k` command
- explain the safe order of operations
- help with reminders and schedules
- discuss a Telegram action before it is executed

Typical examples:
- `.d what .k command should I use to mute this chat`
- `.d explain how to do this through Telegram actions`
- `.d what is the safest way to clean this chat`
- `.d remind me tomorrow at 10 to review this thread`

### `.k` as direct Telegram action mode

Use `.k` when you want the Telegram-side action itself.

It can:
- send something
- edit something
- delete something
- inspect something
- move something between chats
- manage membership/admin state
- create chats/channels
- manage contacts
- work with linked chats and channel comment threads

## 3. Message creation and delivery

The project can send:
- plain text messages
- replies to a specific message
- comments on channel posts through linked discussion threads
- text into linked discussion chats or linked channels
- photos
- videos
- video notes
- GIFs/animations
- documents
- audio files
- voice messages
- stickers
- media groups/albums
- contact cards
- locations
- venues
- polls
- dice/game emoji messages

It can send content:
- into the current chat
- into another resolved chat
- into another resolved user conversation
- into a linked discussion chat
- into a selected previously saved target

## 4. Message editing and cleanup

The project can:
- edit one of the owner's messages
- change the caption of a media message
- replace media in an existing message
- edit or clear inline buttons/reply markup
- delete a single message
- delete multiple messages
- clear accessible message history from a chat
- remove/delete a whole dialog from the owner account where Telegram allows it

## 5. Forwarding, copying, and moving information

The project can:
- forward messages
- copy messages
- forward into linked chats
- copy into linked chats
- search for a relevant message in one chat and deliver it to another chat
- prepare a draft before sending
- keep a selected target for follow-up actions

## 6. Chat-state and message-state operations

The project can:
- mark a chat as read
- archive a chat
- unarchive a chat
- pin a message
- unpin one message
- unpin multiple/all supported pins
- add a reaction to a message

## 7. Lookup and inspection capabilities

The project can inspect:
- recent chat history
- one specific message through reply context
- chat metadata
- user metadata
- members of a chat
- one specific member in a chat
- linked discussion/chat information
- comments on a channel post

It can also:
- summarize found messages
- search by textual relevance
- search across dialogs
- search across different content kinds

## 8. Cross-chat and search-driven actions

The system is not limited to the current chat.

It can:
- resolve another chat from a username, title, ID, or recent reference
- search across dialogs
- find text-like matches
- find photo-like matches
- find voice-like matches
- find a message around a specific time
- find the last matching message
- forward the last matching message
- build a compact “documentation” style summary from a chat
- discover linked channels and related discussions
- use transcript or visual-summary signals to improve message search

## 9. Membership and access operations

The project can:
- join a chat, channel, or invite link
- leave a chat or channel
- block a user at account level
- unblock a user
- ban a user from a chat
- unban a user from a chat
- restrict a member
- unrestrict a member
- promote a member to admin
- demote an admin
- set a custom administrator title
- change default member permissions in a chat
- approve chat join requests
- decline chat join requests

## 10. Chat creation and chat configuration operations

The project can:
- create a new group
- create a new channel
- change chat title
- change chat description
- set a chat photo
- delete a chat photo
- export a primary invite link
- create additional invite links
- edit invite links
- revoke invite links

## 11. Contact-book operations

The project can:
- add a user to the owner’s Telegram contact book
- rename/update a contact
- remove a contact from the contact book

## 12. Drafting and action preparation

Before executing something, the project can:
- generate a draft instead of sending immediately
- build a human-readable preview of the action
- ask for confirmation for sensitive/destructive operations
- remember a selected target for later commands
- rewrite a vague request into a cleaner actionable command

## 13. Normal AI assistance

As an AI assistant, the system can:
- answer direct questions
- summarize threads
- explain social/chat context
- rewrite texts in another tone
- shorten or expand text
- provide a stronger/weaker version of a message
- help decide how to reply
- produce drafts from context
- explain tradeoffs and next steps
- provide help using the system itself

## 14. Context-aware answering

The assistant is context-aware. It can use:
- recent conversation history
- who is speaking
- whether the owner is mentioned
- the type of chat
- the current runtime mode
- memory stores
- special target rules
- writing style information
- live-data results
- reply context from the current thread

## 15. Audio and image capabilities

The project can:
- download media from Telegram messages
- extract photos from the current or replied message
- transcribe audio and voice messages
- build vision-aware prompts from images
- combine multimodal context with normal text prompting

## 16. Live-data capabilities

When enabled, the system can answer requests using:
- weather lookup
- exchange-rate lookup
- web search
- news-like search routing
- page fetching for grounding
- location resolution
- cached live results

It can:
- detect when a prompt looks like weather
- detect when it looks like exchange rates
- detect when it looks like a news/search request
- build a grounding block from search results
- fetch and include page text where allowed

## 17. Model orchestration

The AI layer can:
- run text generation
- run vision generation
- transcribe audio
- refresh available models
- detect task type
- choose a preferred model order for the task
- fall back to another model if needed
- judge multiple candidates
- keep model performance statistics
- keep model rate-limit state

## 18. Response validation and cleanup

The system validates generated output before using it.

It can:
- sanitize visible output
- repair broken text
- strip unwanted prefixes
- detect reasoning leaks
- detect malformed/truncated answers
- detect refusal-like and useless answers
- detect wrong-language answers
- choose the best candidate from multiple generated options

## 19. Memory capabilities

The project has several memory layers.

### Owner knowledge

It can:
- store owner knowledge as structured text
- separate public-safe and private/internal sections
- build a public-safe block
- build an owner-only block
- select the most relevant sections for an owner query

### Owner directives

It can:
- keep global behavioral rules
- keep target-specific rules
- enable or disable replies for a target
- set a response mode for a target
- clear one target or clear all directives
- build a readable summary of active directives

### Shared memory

It can:
- observe reusable short-term facts/fragments
- extract useful keywords
- return only context relevant to a new request
- deduplicate entries
- prune old entries automatically

### Entity memory

It can:
- keep memory about recurring people/entities
- remember explicit facts
- observe users from conversation
- infer attributes like name, age, username, website, location
- build entity context for a query
- build entity context for a target user/entity
- keep entries encrypted where configured
- cleanup stale entries

### User memory

It can:
- store user profiles
- observe interaction patterns
- infer tone/topics
- keep special targets
- keep close contacts
- resolve a user by username
- build per-user instructions for prompting
- cleanup stale profiles

### Style memory

It can:
- learn the owner’s writing style
- learn a user’s writing style
- learn the relationship style between owner and user
- build style summaries
- build prompt sections from style
- blend owner style, user style, and relationship style into one response strategy

## 20. Auto-reply engine

The project can automatically reply under configured conditions.

It supports:
- global auto-reply enable/disable
- per-chat probability
- per-chat cooldown
- per-chat delay range
- per-chat hourly reply limit
- minimum message-length checks
- duplicate suppression
- owner mention/context requirements
- audience filtering
- business-like filtering
- question detection
- special target behavior
- close contact behavior
- silence heuristics

## 21. Runtime state controls

The project keeps runtime state and lets the owner change it.

It can store and change:
- active model
- judge model
- enabled/disabled models
- fallback mode
- AI mode
- command mode
- response style mode
- trigger aliases
- whether dot-prefix is required
- auto-reply state
- reply audience mode
- audience flags
- reply-only-questions
- require-owner-mention-or-context
- visitor mode enabled/disabled
- chat-bot owner-only state
- chat-bot allowed users
- allowed chats
- blocked chats
- per-chat reply settings

## 22. Reminders and scheduler

The project can:
- parse reminder requests
- detect schedule intent
- create one-time reminders
- create repeating reminders
- run timers
- keep scheduled tasks across restarts
- fire a callback when a task is due
- label and humanize schedule information

It also supports more passive reminder behavior:
- detect reminder intent from looser language
- try to create reminders from natural owner phrasing

## 23. Monitoring

The project can:
- keep monitor rules
- add/remove/patch rules
- check incoming text against monitor rules
- produce monitor notifications
- parse monitor-like owner commands

## 24. Public chat bot behavior

The optional public chat bot can:
- start a conversation
- show help
- clear current conversation state
- accept text, image, and voice input
- answer using AI
- use live-data and web-grounding
- enforce owner-only access
- enforce whitelist-style access
- notify the owner
- bridge into visitor mode

## 25. Visitor-mode behavior

Visitor mode is a controlled public-facing flow.

It can:
- start a visitor session
- end a visitor session
- keep per-visitor history during the active window
- track inactivity
- apply a restart cooldown
- apply temporary blocks
- apply rate limits
- track abuse
- track boundary-pushing behavior
- track low-signal behavior
- decide whether the current turn looks meaningful
- give supportive guidance to shy or uncertain visitors
- avoid drifting into casual “friend chat” when the mode should stay bounded

## 26. Visitor routing and answer styles

Visitor requests can be routed into different paths:
- static/knowledge path
- FAQ path
- card path
- AI answer path
- search-backed path
- ask-owner path
- moderated refusal path

The visitor system can also return:
- owner overview cards
- links cards
- projects cards
- collaboration cards
- FAQ cards
- capabilities cards

## 27. Visitor moderation and public safety

The public side has stronger boundaries.

It can:
- detect abusive messages
- notify the owner about moderation incidents
- classify visitor topics
- detect requests that should be blocked or redirected
- restrict source usage in public answers
- escalate suspicious/problematic AI outputs for review
- keep a judge/incident log

## 28. Visitor FAQ, inbox, and admin tools

Visitor support tooling includes:
- FAQ matching
- adding/removing FAQ entries
- formatting FAQ lists
- owner inbox for visitor questions
- awaiting-question states
- owner replies back to the visitor
- inbox cleanup
- visitor stats
- visitor session lists
- topic summaries
- broadcasts to active visitor sessions
- quiet mode for visitor admin handling

## 29. Public search and portfolio lookup

For public-facing answers, the project can:
- parse a portfolio URL from safe public knowledge
- crawl a portfolio site
- search portfolio pages
- search GitHub
- search the web
- build snippets from matched public pages
- prefer allowed/public-safe sources

## 30. Identity and safety

The project has explicit identity and safety logic.

It can:
- detect identity questions
- force canonical identity answers
- detect wrong identity claims
- refuse non-owner authority claims
- refuse non-owner threats
- classify risky prompts
- detect secret/credential-style requests
- protect owner-only/private information
- validate outgoing AI responses before sending

## 31. Reliability and persistence

The project includes infrastructure for reliability:
- persistent JSON and SQLite storage
- atomic writes
- JSON backups
- rate limiting
- health checks
- uptime reporting
- structured logging
- scheduler persistence
- migration helpers
- encrypted fields and key management
- owner action logging

## 32. Public version limitations

The public repository intentionally excludes:
- real secrets
- real Telegram sessions
- private owner data
- real runtime state databases/files
- private logs and caches

The logic and architecture remain, but actual operation requires your own local credentials, sessions, and runtime data.
