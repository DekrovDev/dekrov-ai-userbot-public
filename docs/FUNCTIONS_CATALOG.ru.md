# Каталог функций

Этот документ является полным каталогом возможностей проекта. Он описывает не устройство по файлам, а то, что система реально умеет делать.

## 1. Owner workflows

Владелец может использовать проект как:
- прямого AI-ассистента
- исполнителя Telegram-действий
- планировщик и объяснитель этих действий
- reminder/schedule ассистента
- memory-backed conversation assistant
- auto-reply engine
- runtime-controlled Telegram operator

## 2. Owner command modes

### `.b` как основной режим

`.b` нужен, когда ты хочешь, чтобы ассистент сразу решил задачу.

Он умеет:
- отвечать на вопросы
- суммировать чаты
- объяснять, чего хочет другой человек
- переписывать сообщение в другом тоне
- писать draft reply
- предлагать, что делать дальше
- объяснять ситуацию
- анализировать контекст из recent conversation history
- использовать stored memory и style information
- использовать live-data и web-grounding, если нужно
- работать с image и audio input там, где flow это поддерживает

Примеры:
- `.b кратко ответь на это сообщение`
- `.b кратко подведи итог этого чата`
- `.b сделай этот ответ мягче`
- `.b что мне лучше сделать дальше здесь`

### `.d` как helper/planning режим

`.d` нужен, когда задачу сначала нужно продумать.

Он умеет:
- объяснять, как использовать систему
- говорить, относится ли задача к `.b`, `.d`, `.k`, control bot или persistent memory
- превращать намерение в `.k` команду
- объяснять безопасный порядок действий
- помогать с reminder и schedule сценариями
- обсуждать Telegram-действие до выполнения

Примеры:
- `.d какую .k команду использовать, чтобы замьютить этот чат`
- `.d объясни, как сделать это через Telegram actions`
- `.d как безопаснее всего почистить этот чат`
- `.d напомни мне завтра в 10:00 проверить этот тред`

### `.k` как режим прямых Telegram-действий

`.k` нужен, когда нужно само Telegram-действие.

Он умеет:
- отправлять
- редактировать
- удалять
- искать и смотреть
- переносить информацию между чатами
- управлять membership/admin state
- создавать группы и каналы
- управлять контактами
- работать с linked chats и comment threads

## 3. Создание и доставка сообщений

Проект умеет отправлять:
- обычный текст
- reply на конкретное сообщение
- комментарии под channel post через linked discussion
- сообщения в linked discussion chat или linked channel
- фото
- видео
- video note
- GIF/animation
- document
- audio file
- voice message
- sticker
- media group/album
- contact card
- location
- venue
- poll
- dice/game emoji message

Отправка возможна:
- в текущий чат
- в другой chat/user dialog
- в linked discussion chat
- в заранее выбранный target

## 4. Редактирование и cleanup

Проект умеет:
- редактировать одно из owner-сообщений
- менять caption у media message
- заменять media в существующем сообщении
- редактировать или очищать inline buttons
- удалять одно сообщение
- удалять несколько сообщений
- очищать доступную историю
- удалять или убирать весь dialog из owner account там, где это разрешает Telegram

## 5. Forward, copy и перенос информации

Проект умеет:
- forward сообщений
- copy сообщений
- forward в linked chats
- copy в linked chats
- искать релевантное сообщение в одном чате и отправлять его в другой
- сначала делать draft вместо немедленной отправки
- держать выбранный target для следующих команд

## 6. Chat-state и message-state операции

Проект умеет:
- mark chat as read
- archive chat
- unarchive chat
- pin message
- unpin one message
- unpin несколько или все поддерживаемые pins
- ставить reaction на message

## 7. Lookup и inspection возможности

Проект умеет смотреть:
- recent chat history
- конкретное сообщение через reply context
- chat metadata
- user metadata
- участников чата
- одного конкретного участника
- linked chat information
- comments под channel post

Также он умеет:
- суммировать найденные сообщения
- искать по текстовой релевантности
- искать по dialog history
- искать по разным content kinds

## 8. Cross-chat возможности

Система не ограничена текущим чатом.

Она умеет:
- resolve другой chat по username, title, ID или recent reference
- искать по dialogs
- искать text-like matches
- искать photo-like matches
- искать voice-like matches
- искать сообщение возле определенного времени
- находить последнее подходящее сообщение
- forward-ить последнее подходящее сообщение
- строить compact documentation-like summary по чату
- находить related channel/discussion chat
- использовать transcript и visual-summary сигналы для улучшения поиска

## 9. Membership и access операции

Проект умеет:
- join chat/channel/invite link
- leave chat/channel
- block user на уровне account
- unblock user
- ban user в чате
- unban user в чате
- restrict member
- unrestrict member
- promote member to admin
- demote admin
- set custom administrator title
- change default member permissions
- approve join request
- decline join request

## 10. Создание и настройка чатов

Проект умеет:
- create new group
- create new channel
- change chat title
- change chat description
- set chat photo
- delete chat photo
- export primary invite link
- create additional invite links
- edit invite links
- revoke invite links

## 11. Операции с контактами

Проект умеет:
- add user to the owner contact book
- rename/update contact
- delete contact

## 12. Drafting и подготовка действий

Перед выполнением проект умеет:
- генерировать draft вместо мгновенной отправки
- строить понятный preview действия
- спрашивать подтверждение для sensitive/destructive operations
- помнить выбранный target для следующих команд
- переписывать vague request в cleaner actionable command

## 13. Обычная AI-помощь

Как AI-ассистент проект умеет:
- отвечать на прямые вопросы
- суммировать треды
- объяснять social/chat context
- переписывать текст в другом тоне
- сокращать или расширять текст
- делать ответ сильнее или мягче
- помогать решить, как отвечать
- строить drafts из контекста
- объяснять tradeoffs и next steps
- помогать пользоваться самой системой

## 14. Context-aware ответы

Ассистент умеет использовать:
- recent conversation history
- кто сейчас говорит
- mention owner или нет
- type of chat
- current runtime mode
- memory stores
- special-target rules
- writing style information
- live-data results
- reply context из текущего треда

## 15. Audio и image возможности

Проект умеет:
- скачивать media из Telegram messages
- извлекать фото из current/replied message
- транскрибировать audio и voice messages
- строить vision-aware prompts из images
- объединять multimodal context с обычным text prompting

## 16. Live-data возможности

Когда включено, система умеет отвечать через:
- weather lookup
- exchange-rate lookup
- web search
- news-like search routing
- page fetching for grounding
- location resolution
- cached live results

Она умеет:
- понимать, что prompt похож на weather request
- понимать, что prompt похож на exchange-rates request
- понимать, что prompt похож на news/search request
- строить grounding block из search results
- fetch-ить и включать page text там, где это разрешено

## 17. Оркестрация моделей

AI-слой умеет:
- запускать text generation
- запускать vision generation
- транскрибировать audio
- refresh-ить available models
- detect task type
- выбирать preferred model order для задачи
- fallback на другую модель
- judge-ить несколько candidates
- хранить model performance statistics
- хранить model rate-limit state

## 18. Валидация и cleanup ответа

Система валидирует generated output перед использованием.

Она умеет:
- sanitize visible output
- repair broken text
- strip unwanted prefixes
- detect reasoning leaks
- detect malformed/truncated answers
- detect refusal-like и useless answers
- detect wrong-language answers
- choose best candidate из нескольких generated options

## 19. Memory возможности

У проекта есть несколько memory-слоев.

### Owner knowledge

Он умеет:
- хранить owner knowledge как structured text
- разделять public-safe и private/internal sections
- строить public-safe block
- строить owner-only block
- выбирать наиболее релевантные sections для owner query

### Owner directives

Он умеет:
- хранить global behavioral rules
- хранить target-specific rules
- enable/disable replies for a target
- set response mode for a target
- clear one target или clear all directives
- build readable summary of active directives

### Shared memory

Он умеет:
- наблюдать reusable short-term facts/fragments
- выделять useful keywords
- возвращать только релевантный context для нового запроса
- deduplicate entries
- prune old entries automatically

### Entity memory

Он умеет:
- хранить память о recurring people/entities
- remember explicit facts
- observe users from conversation
- infer attributes вроде name, age, username, website, location
- build entity context for a query
- build entity context for a target user/entity
- keep entries encrypted where configured
- cleanup stale entries

### User memory

Он умеет:
- хранить user profiles
- observe interaction patterns
- infer tone/topics
- keep special targets
- keep close contacts
- resolve user by username
- build per-user instructions for prompting
- cleanup stale profiles

### Style memory

Он умеет:
- учить owner writing style
- учить user writing style
- учить relationship style between owner and user
- build style summaries
- build prompt sections from style
- blend owner style, user style и relationship style в единую response strategy

## 20. Auto-reply engine

Проект умеет автоматически отвечать при заданных условиях.

Он поддерживает:
- global auto-reply enable/disable
- per-chat probability
- per-chat cooldown
- per-chat delay range
- per-chat hourly limit
- minimum message-length checks
- duplicate suppression
- owner mention/context requirement
- audience filters
- business-like filtering
- question detection
- special-target behavior
- close-contact behavior
- silence heuristics

## 21. Runtime state controls

Проект хранит runtime-state и дает владельцу его менять.

Он умеет хранить и менять:
- active model
- judge model
- enabled/disabled models
- fallback mode
- AI mode
- command mode
- response style mode
- trigger aliases
- dot-prefix requirement
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

## 22. Reminders и scheduler

Проект умеет:
- parse reminder requests
- detect schedule intent
- create one-time reminders
- create repeating reminders
- run timers
- keep scheduled tasks across restarts
- fire callback when a task is due
- строить понятные labels и humanized schedule info

Также он умеет более пассивно:
- detect reminder intent из менее формального текста
- пытаться создать reminder из natural owner phrasing

## 23. Monitoring

Проект умеет:
- хранить monitor rules
- add/remove/patch rules
- check incoming text against rules
- produce monitor notifications
- parse monitor-like owner commands

## 24. Поведение публичного chat bot

Опциональный публичный bot умеет:
- начинать conversation
- показывать help
- clear current conversation state
- принимать text, image и voice input
- отвечать через AI
- использовать live-data и web-grounding
- enforce owner-only access
- enforce whitelist-style access
- уведомлять владельца
- bridge в visitor mode

## 25. Поведение visitor mode

Visitor mode — это контролируемый public-facing flow.

Он умеет:
- start visitor session
- end visitor session
- хранить per-visitor history during the active window
- track inactivity
- apply restart cooldown
- apply temporary blocks
- apply rate limits
- track abuse
- track boundary-pushing behavior
- track low-signal behavior
- decide whether the current turn looks meaningful
- give supportive guidance to shy or uncertain visitors
- avoid drifting into casual friend-chat mode when the flow should stay bounded

## 26. Visitor routing и стили ответов

Visitor requests могут идти в разные paths:
- static/knowledge path
- FAQ path
- card path
- AI answer path
- search-backed path
- ask-owner path
- moderated refusal path

Visitor-система также умеет отдавать:
- owner overview cards
- links cards
- projects cards
- collaboration cards
- FAQ cards
- capabilities cards

## 27. Visitor moderation и public safety

Публичный контур имеет более жесткие границы.

Он умеет:
- detect abusive messages
- notify owner about moderation incidents
- classify visitor topics
- detect requests that should be blocked or redirected
- restrict source usage in public answers
- escalate suspicious/problematic AI outputs for review
- keep a judge/incident log

## 28. Visitor FAQ, inbox и admin tools

Visitor support tooling включает:
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

## 29. Public search и portfolio lookup

Для public-facing answers проект умеет:
- parse portfolio URL from safe public knowledge
- crawl portfolio site
- search portfolio pages
- search GitHub
- search the web
- build snippets from matched public pages
- prioritize allowed/public-safe sources

## 30. Identity и safety

У проекта есть явная identity и safety логика.

Он умеет:
- detect identity questions
- force canonical identity answers
- detect wrong identity claims
- refuse non-owner authority claims
- refuse non-owner threats
- classify risky prompts
- detect secret/credential-style requests
- protect owner-only/private information
- validate outgoing AI responses before sending

## 31. Надежность и persistence

В проекте есть инфраструктура для устойчивой работы:
- persistent JSON и SQLite storage
- atomic writes
- JSON backups
- rate limiting
- health checks
- uptime reporting
- structured logging
- scheduler persistence
- migration helpers
- encrypted fields и key management
- owner action logging

## 32. Ограничения публичной версии

Публичный репозиторий специально не включает:
- реальные secrets
- реальные Telegram sessions
- private owner data
- реальный runtime state
- private logs и caches

Логика и архитектура сохранены, но для реальной работы нужны свои локальные credentials, sessions и runtime data.
