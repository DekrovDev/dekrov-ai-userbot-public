# Функции проекта

Этот документ объясняет, что проект умеет на практике. Он написан не с точки зрения файлов и классов, а с точки зрения поведения системы и пользовательских сценариев.

## 1. Что это за проект

Это многоуровневый Telegram-ассистент, в котором есть:
- owner-side `userbot`
- приватный `control bot`
- опциональный публичный `chat bot`
- более строгий публичный `visitor`-режим

Система объединяет:
- AI-ответы
- память
- Telegram-действия
- модерацию
- scheduling и напоминания
- live-data поиск и grounding
- persistent runtime-state

## 2. Основные способы использования

Владелец в основном работает с проектом через три режима userbot:
- `.b` как основной/default AI-режим
- `.d` как режим планирования, объяснения, помощи и напоминаний
- `.k` как режим прямых Telegram-действий

Практическая логика:
- `.b` использовать, когда нужно, чтобы ассистент решил задачу напрямую
- `.d` использовать, когда нужно спросить, как лучше что-то сделать, каким режимом воспользоваться или какую `.k` команду отправить
- `.k` использовать, когда нужно само Telegram-действие

Примеры:
- `.b кратко подведи итог этого диалога и предложи ответ`
- `.d какую .k команду использовать, чтобы удалить этот чат`
- `.k архивировать этот чат`

## 3. Что умеет owner-side ассистент

В обычной owner-работе проект умеет:
- отвечать на вопросы
- суммировать переписки и сообщения
- переписывать текст в другом тоне
- писать черновики ответов
- объяснять варианты и следующие шаги
- помогать решить, как отвечать в разговоре
- использовать контекст чата, память и стиль
- использовать live-data и web-grounding, если запрос требует актуальной информации
- интерпретировать изображения и транскрибировать аудио

Он понимает разницу между:
- обычной AI-помощью
- режимом планирования и объяснения
- режимом выполнения Telegram-действий

## 4. Что умеет `.b`

`.b` — это главный AI-режим. Для большинства owner-задач он должен быть основным.

Он умеет:
- отвечать на прямые вопросы
- суммировать чат или тред
- переписывать черновик
- делать ответ сильнее, мягче, короче или понятнее
- объяснять, чего хочет другой человек
- генерировать reply drafts
- использовать память и runtime-context для более персонального ответа
- использовать live-data и web-grounding, если это нужно для ответа
- работать с image/audio input, если это поддерживает текущий flow

Примеры:
- `.b ответь на это сообщение коротко и вежливо`
- `.b сделай этот ответ жестче`
- `.b чего этот человек от меня хочет`
- `.b кратко подведи итог этого чата`

## 5. Что умеет `.d`

`.d` — это режим диалога, helper-логики и планирования.

Он умеет:
- объяснять, как использовать саму систему
- говорить, что лучше использовать: `.b`, `.d`, `.k`, control bot или persistent memory
- превращать намерение в правильную `.k` команду
- объяснять безопасный порядок действий
- помогать с reminder и schedule сценариями
- обсуждать Telegram-действие до того, как ты его выполнишь

Примеры:
- `.d как лучше всего почистить этот чат`
- `.d какую .k команду отправить, чтобы замьютить этот чат`
- `.d объясни, как сделать это через режим Telegram-действий`
- `.d напомни мне завтра в 10:00 проверить этот тред`

## 6. Что умеет `.k`

`.k` — это режим прямых Telegram-действий.

Он умеет выполнять или подготавливать такие Telegram-операции, как:
- отправка сообщений и медиа
- reply на сообщения
- редактирование собственных сообщений
- удаление сообщений
- пересылка и копирование
- реакции, pin, unpin
- mark read
- archive и unarchive chats
- clear history и delete dialog
- lookup информации о чатах, пользователях и участниках
- join и leave chats
- работа с invite links и join requests
- создание групп и каналов
- moderation/admin операции
- управление контактами

Примеры:
- `.k отправь это сообщение пользователю @example_user`
- `.k удалить это сообщение`
- `.k закрепить это сообщение`
- `.k создать новую группу с этими пользователями`

## 7. Telegram action-возможности

Telegram action-слой — одна из самых крупных частей проекта. Он поддерживает:

Создание и отправку:
- текстовых сообщений
- reply-сообщений
- комментариев под channel posts через linked discussion
- сообщений в linked discussion chats и linked channels
- фото
- видео
- video notes
- GIF/animations
- документов
- аудио
- voice messages
- stickers
- media groups/albums
- contacts
- locations
- venues
- polls
- dice/game emoji сообщений

Редактирование и cleanup:
- редактирование своего сообщения
- редактирование captions
- замена media в существующем сообщении
- редактирование и очистка inline buttons
- удаление одного сообщения
- удаление нескольких сообщений
- очистка доступной истории
- удаление/удаление диалога из owner-аккаунта там, где Telegram это позволяет

Forward/copy:
- forward сообщений
- copy сообщений
- forward/copy в linked chats

Lookup и inspection:
- recent chat history
- chat metadata
- user metadata
- members of a chat
- one specific member
- linked chat information
- comments under a channel post
- reading info from the replied message
- saving/reusing a selected target
- generating a draft/preview instead of immediate send

Chat/member/admin операции:
- join chat/channel/invite link
- leave chat
- archive/unarchive chat
- mark chat as read
- export primary invite link
- create additional invite links
- edit/revoke invite links
- approve/decline join requests
- create group
- create channel
- block/unblock user
- ban/unban member
- restrict/unrestrict member
- promote/demote admin
- set custom admin title
- change default member permissions
- change chat title, description and photo

Contact-book операции:
- add contact
- rename/update contact
- delete contact

## 8. Cross-chat возможности

Система умеет работать не только в текущем чате.

Она может:
- находить другой чат по username, title, ID или recent reference
- искать по диалогам
- искать text-like совпадения
- искать photo-like совпадения
- искать voice-like совпадения
- искать сообщение около определенного времени
- находить последнее подходящее сообщение
- forward-ить последнее подходящее сообщение
- строить компактную “documentation-like” выжимку по чату
- находить related channel/discussion chat
- использовать transcript и visual-summary сигналы для улучшения поиска

Это полезно для сценариев вроде:
- “найди последнее voice сообщение про X”
- “отправь этот ответ в выбранный target”
- “перешли последнее подходящее сообщение в другой чат”

## 9. Память и персонализация

У проекта есть несколько memory-слоев.

Он умеет хранить:
- owner knowledge
- owner directives/rules
- shared reusable memory
- память о людях и сущностях
- user profiles
- writing-style profiles
- relationship-style patterns

На практике это значит, что система может:
- помнить долгоживущие owner preferences
- помнить инструкции вроде “этому человеку отвечай формальнее”
- помнить факты о повторяющихся людях и сущностях
- выводить и использовать тон/style patterns
- адаптировать ответ под owner, target user и их relationship
- хранить special targets и close-contact настройки

## 10. Auto-reply и контроль поведения в чатах

Проект работает не только по явным командам. Он умеет вести себя автоматически.

Auto-reply возможности:
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

Это позволяет запускать ассистента как более пассивно, так и более активно в зависимости от чата.

## 11. Reminders, schedule и monitoring

Проект умеет автоматизировать не только ответы.

Он может:
- создавать reminders
- разбирать time-based owner requests
- ставить one-time tasks
- ставить repeating tasks
- запускать timers
- хранить scheduled tasks между перезапусками
- запускать callback в момент срабатывания
- строить понятные подписи и человекочитаемые schedule labels
- держать monitor rules
- проверять incoming text на monitor rules
- отправлять notifications, когда правило сработало

Также он умеет более пассивно ловить reminder-намерения:
- распознавать reminder intent даже из менее формальной речи
- пытаться создать reminder из естественных owner-фраз

## 12. Live-data и web-возможности

Если включено, ассистент может обогащать ответы внешней актуальной информацией.

Поддерживаемые области:
- weather lookup
- exchange-rate lookup
- web search
- news-like search routing
- page fetching for grounding
- location resolution
- caching live results

Это позволяет отвечать на запросы вроде:
- текущая погода в локации
- курс валют
- recent search-backed answer
- grounded reply на основе fetched web pages

## 13. AI-возможности

AI-подсистема делает не одну text completion.

Она умеет:
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

Система рассчитана не на “взять первый ответ модели”, а на выбор и валидацию результата.

## 14. Возможности публичного chat bot

Опциональный публичный bot умеет:
- начинать разговор
- показывать help
- очищать conversation state
- принимать text, image и voice input
- отвечать через AI
- использовать live-data и web-grounding
- enforce owner-only access
- enforce whitelist-style access
- уведомлять владельца
- передавать пользователя в visitor mode

У владельца также есть helper-команды для visitor-операций вокруг этого бота.

## 15. Возможности visitor mode

Visitor mode — это отдельный публичный experience с более жесткими границами, чем обычный owner-side режим.

Он умеет:
- стартовать visitor session
- завершать visitor session
- хранить временную visitor history
- отслеживать inactivity
- включать restart cooldown
- включать temporary blocks
- применять rate limits
- отслеживать abuse
- отслеживать boundary-pushing behavior
- отслеживать low-signal behavior
- решать, насколько текущий turn выглядит meaningful
- давать supportive guidance неуверенным или стеснительным visitors
- не уходить в casual “friend chat”, если режим должен оставаться bounded

## 16. Routing и answer-styles в visitor

Visitor requests могут попадать в разные пути:
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

## 17. Модерация visitor и public safety

Публичный контур имеет более жесткие ограничения.

Он умеет:
- detect abusive messages
- уведомлять владельца о moderation incidents
- классифицировать visitor topics
- detect requests, которые надо блокировать или redirect-ить
- ограничивать source usage в публичных ответах
- эскалировать suspicious/problematic AI outputs на review
- хранить judge/incident log

## 18. Visitor FAQ, inbox и admin-инструменты

Visitor support tooling включает:
- FAQ matching
- добавление и удаление FAQ entries
- formatting FAQ lists
- owner inbox для visitor questions
- awaiting-question states
- owner replies back to the visitor
- inbox cleanup
- visitor stats
- visitor session lists
- topic summaries
- broadcasts в активные visitor sessions
- quiet mode для visitor admin handling

## 19. Public search и portfolio lookup

Для публичных ответов проект умеет:
- извлекать portfolio URL из safe public knowledge
- crawl-ить portfolio site
- искать по portfolio pages
- искать по GitHub
- искать по web
- строить snippets из matched public pages
- отдавать приоритет allowed/public-safe sources

## 20. Identity, safety и границы

У проекта есть явная логика identity и safety.

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

## 21. Надежность и persistence

В проекте есть инфраструктура для устойчивой работы:
- persistent JSON и SQLite storage
- atomic writes
- backup management for JSON data
- health checks и uptime tracking
- structured logging
- rate limiting
- scheduler persistence
- local migration helpers
- encrypted fields для selected storage

## 22. Ограничение публичной версии

Публичный репозиторий сохраняет архитектуру и логику, но убирает:
- реальные секреты
- реальные Telegram sessions
- private owner data
- реальный runtime JSON/SQLite state
- logs и caches

То есть публичная версия показывает, что проект умеет, но для реальной работы нужны свои credentials и свой локальный runtime-state.
