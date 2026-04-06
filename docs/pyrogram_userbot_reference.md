# Pyrogram Userbot Reference

Paraphrased local reference based on the official Pyrogram documentation and the installed Pyrogram package.

Primary sources:
- https://docs.pyrogram.org/
- https://docs.pyrogram.org/api/methods/
- https://docs.pyrogram.org/api/bound-methods/

Purpose of this file:
- keep one local reference for the action system
- show which Pyrogram client methods are relevant to the userbot
- separate safe/read actions from state-changing actions
- document the high-level methods first and note raw MTProto escape hatches only when needed

## How To Use This Reference

For every new `.к` capability we add, we usually need 4 things:
1. a registry action in `action_registry.py`
2. a parser path in `command_router.py`
3. an executor handler in `action_executor.py`
4. a real Pyrogram implementation in `tg_actions.py`

This file is not a verbatim mirror of the docs. It is a structured working reference for our project.

## Risk Model For Our Bot

- `safe`: read-only actions, previews, lookups, history reads
- `sensitive`: send/edit/forward/archive/state changes that do not destroy data
- `destructive`: delete history, remove dialogs, leave chats, block, ban
- `critical`: config/code/env/autonomy changes

## Client Method Categories

## Advanced

These are low-level client helpers. They are useful when the high-level API is not enough.

- `compose`
- `idle`
- `invoke`
- `resolve_peer`
- `save_file`
- `set_parse_mode`

Use in our project:
- peer resolution
- raw MTProto fallbacks
- file transmission internals

## Auth

These methods deal with login/session/auth flows. They are not normal runtime `.к` actions, but they matter for setup and maintenance.

- `accept_terms_of_service`
- `check_password`
- `connect`
- `disconnect`
- `get_password_hint`
- `initialize`
- `log_out`
- `recover_password`
- `resend_code`
- `send_code`
- `send_recovery_code`
- `sign_in`
- `sign_in_bot`
- `sign_up`
- `terminate`

Usually not exposed to natural-language execution in the userbot.

## Bots

Mostly relevant only if we automate bot accounts or interact with inline/game flows.

- `answer_callback_query`
- `answer_inline_query`
- `answer_web_app_query`
- `delete_bot_commands`
- `get_bot_commands`
- `get_bot_default_privileges`
- `get_chat_menu_button`
- `get_game_high_scores`
- `get_inline_bot_results`
- `request_callback_answer`
- `send_game`
- `send_inline_bot_result`
- `set_bot_commands`
- `set_bot_default_privileges`
- `set_chat_menu_button`
- `set_game_score`

Useful for:
- callback/button automation
- inline result workflows
- game-related automation

## Chats

This is one of the main categories for our action system.

- `add_chat_members`
- `archive_chats`
- `ban_chat_member`
- `create_channel`
- `create_group`
- `create_supergroup`
- `delete_channel`
- `delete_chat_photo`
- `delete_supergroup`
- `delete_user_history`
- `get_chat`
- `get_chat_event_log`
- `get_chat_member`
- `get_chat_members`
- `get_chat_members_count`
- `get_chat_online_count`
- `get_dialogs`
- `get_dialogs_count`
- `get_nearby_chats`
- `get_send_as_chats`
- `join_chat`
- `leave_chat`
- `mark_chat_unread`
- `pin_chat_message`
- `promote_chat_member`
- `restrict_chat_member`
- `set_administrator_title`
- `set_chat_description`
- `set_chat_permissions`
- `set_chat_photo`
- `set_chat_protected_content`
- `set_chat_title`
- `set_chat_username`
- `set_send_as_chat`
- `set_slow_mode`
- `unarchive_chats`
- `unban_chat_member`
- `unpin_all_chat_messages`
- `unpin_chat_message`

High-value methods for our userbot:

- `get_chat`
  - read metadata for a chat/channel/dialog
  - good for `.к инфо о чате`

- `get_dialogs`
  - enumerate dialogs accessible to the account
  - good for target resolution and fuzzy matching

- `get_chat_members_count`
  - the reliable way to answer "сколько людей в чате"

- `join_chat`
  - join public chats/channels or invite links

- `leave_chat`
  - leave chats/channels
  - for basic chats it supports deleting the dialog too

- `create_group`
  - create a basic group
  - requires at least one user to add

- `create_supergroup`
  - create a supergroup directly
  - this is the better default for our action layer when the owner says "создай группу"

- `set_chat_username`
  - assign or remove a public username for a supergroup/channel

- `set_chat_title`
  - rename a chat

- `set_chat_description`
  - update chat description

- `archive_chats` / `unarchive_chats`
  - manage dialog archive state

- `pin_chat_message` / `unpin_chat_message` / `unpin_all_chat_messages`
  - pinning control

- `delete_user_history`
  - useful when we need to remove one user’s messages from a supergroup

Important limitation:
- deleting a "chat completely" is not a single universal high-level method for every chat type
- behavior depends on private/basic/supergroup/channel semantics

## Contacts

Useful if we later want contact-level actions.

- `add_contact`
- `delete_contacts`
- `get_contacts`
- `get_contacts_count`
- `import_contacts`

These are sensitive and should stay owner-only.

## Invite Links

Useful for moderation/admin flows and invite management.

- `approve_all_chat_join_requests`
- `approve_chat_join_request`
- `create_chat_invite_link`
- `decline_all_chat_join_requests`
- `decline_chat_join_request`
- `delete_chat_admin_invite_links`
- `delete_chat_invite_link`
- `edit_chat_invite_link`
- `export_chat_invite_link`
- `get_chat_admin_invite_links`
- `get_chat_admin_invite_links_count`
- `get_chat_admins_with_invite_links`
- `get_chat_invite_link`
- `get_chat_invite_link_joiners`
- `get_chat_invite_link_joiners_count`
- `get_chat_join_requests`
- `revoke_chat_invite_link`

Good for:
- admin automation
- invite auditing
- join-request workflows

## Messages

This is the other main category for our action system.

- `copy_media_group`
- `copy_message`
- `delete_messages`
- `download_media`
- `edit_inline_caption`
- `edit_inline_media`
- `edit_inline_reply_markup`
- `edit_inline_text`
- `edit_message_caption`
- `edit_message_media`
- `edit_message_reply_markup`
- `edit_message_text`
- `forward_messages`
- `get_chat_history`
- `get_chat_history_count`
- `get_custom_emoji_stickers`
- `get_discussion_message`
- `get_discussion_replies`
- `get_discussion_replies_count`
- `get_media_group`
- `get_messages`
- `read_chat_history`
- `retract_vote`
- `search_global`
- `search_global_count`
- `search_messages`
- `search_messages_count`
- `send_animation`
- `send_audio`
- `send_cached_media`
- `send_chat_action`
- `send_contact`
- `send_dice`
- `send_document`
- `send_location`
- `send_media_group`
- `send_message`
- `send_photo`
- `send_poll`
- `send_reaction`
- `send_sticker`
- `send_venue`
- `send_video`
- `send_video_note`
- `send_voice`
- `stop_poll`
- `stream_media`
- `vote_poll`

High-value methods for our userbot:

- `send_message`
  - the main send primitive

- `edit_message_text`
  - used for placeholder-to-final-response workflows

- `delete_messages`
  - delete one or multiple messages

- `forward_messages`
  - forward messages while preserving origin

- `copy_message`
  - copy message content without forward header

- `get_messages`
  - fetch exact message ids

- `get_chat_history`
  - read recent context from a chat

- `search_messages`
  - find matching messages inside a specific chat

- `search_global`
  - global account-wide Telegram search

- `read_chat_history`
  - mark chat as read

- `send_chat_action`
  - typing/upload status; useful for visible loading

- `send_reaction`
  - reactions where supported

- `download_media`
  - required if we later want file extraction or attachment processing

## Password

Account security methods, not default `.к` surface.

- `change_cloud_password`
- `enable_cloud_password`
- `remove_cloud_password`

## Users

Mainly profile and user metadata methods.

- `block_user`
- `delete_profile_photos`
- `get_chat_photos`
- `get_chat_photos_count`
- `get_common_chats`
- `get_default_emoji_statuses`
- `get_me`
- `get_users`
- `set_emoji_status`
- `set_profile_photo`
- `set_username`
- `unblock_user`
- `update_profile`

High-value methods for our userbot:

- `get_me`
  - runtime self identity

- `get_users`
  - resolve user ids/usernames

- `block_user` / `unblock_user`
  - owner-only moderation over private contacts

- `set_username`
  - changes the owner account username, not a chat username
  - critical/sensitive and should never be exposed casually

- `update_profile`
  - can change owner profile fields
  - should be treated as critical in our architecture

## Utilities

These are runtime/library control methods.

- `add_handler`
- `export_session_string`
- `remove_handler`
- `restart`
- `run`
- `start`
- `stop`
- `stop_transmission`

Useful for:
- lifecycle management
- dynamic handler registration
- exported sessions
- upload interruption

Usually not normal `.к` commands unless we explicitly decide to expose them.

## Decorators

These are framework integration hooks, not execution actions.

- `on_callback_query`
- `on_chat_join_request`
- `on_chat_member_updated`
- `on_chosen_inline_result`
- `on_deleted_messages`
- `on_disconnect`
- `on_edited_message`
- `on_inline_query`
- `on_message`
- `on_poll`
- `on_raw_update`
- `on_user_status`

Good to know, but not direct action-layer capabilities.

## Bound Methods

Pyrogram also exposes shortcut methods on objects themselves. These are especially useful when the action system works with a `Message`, `Chat`, or `User` object directly.

### Message Bound Methods

- `reply`
- `get_media_group`
- `reply_text`
- `reply_animation`
- `reply_audio`
- `reply_cached_media`
- `reply_chat_action`
- `reply_contact`
- `reply_document`
- `reply_game`
- `reply_inline_bot_result`
- `reply_location`
- `reply_media_group`
- `reply_photo`
- `reply_poll`
- `reply_sticker`
- `reply_venue`
- `reply_video`
- `reply_video_note`
- `reply_voice`
- `edit_text`
- `edit_caption`
- `edit_media`
- `edit_reply_markup`
- `forward`
- `copy`
- `delete`
- `click`
- `react`
- `download`
- `edit`
- `pin`
- `unpin`

Useful mapping hints:
- reply-context actions can be expressed through bound methods cleanly
- button/callback automation often goes through `click`
- reaction support maps naturally to `react`

### Chat Bound Methods

- `get_members`
- `archive`
- `unarchive`
- `set_title`
- `set_description`
- `set_photo`
- `ban_member`
- `unban_member`
- `restrict_member`
- `promote_member`
- `join`
- `leave`
- `get_member`
- `add_members`
- `mark_unread`
- `set_protected_content`
- `unpin_all_messages`

Good for object-oriented action execution if we decide to refactor later.

### User Bound Methods

Common useful user shortcuts:
- `answer`
- `approve`
- `archive`
- `decline`
- `unarchive`
- `block`
- `unblock`

## Raw MTProto Methods Relevant To Our Bot

These are not the first choice, but they matter where the high-level client API is not enough.

- `raw.functions.messages.DeleteHistory`
  - useful for deleting private/basic-chat history

- `raw.functions.messages.DeleteChat`
  - lower-level basic-chat deletion path

- `raw.functions.channels.DeleteHistory`
  - channel/supergroup history deletion path

- `raw.functions.messages.DeleteChatUser`
  - leaving/removing from a basic chat

Rule for our project:
- use documented high-level client methods first
- use raw only when Pyrogram high-level methods do not expose the needed behavior cleanly

## What Matters Most For Our Action Layer

If we want strong `.к` coverage, these method families matter the most:

### Must-cover

- send/edit/delete/copy/forward/reply
- get chat history / get messages / search messages
- join / leave / archive / unarchive
- get chat info / get user info / get dialogs
- pin / unpin / mark read / mark unread
- create supergroup / set chat title / set chat description / set chat username
- block / unblock / ban / unban / add members

### Nice to have

- invite-link management
- contacts
- profile updates
- media sending/downloading
- chat permissions / slow mode / protected content
- send-as / nearby chats / online count / event logs

### Dangerous / critical

- set_username
- update_profile
- export_session_string
- auth/password flows
- raw destructive APIs

## Gaps We Still Need To Map In Code

Even if Pyrogram supports a method, the bot still needs:
- a parser path in `command_router.py`
- a registry definition in `action_registry.py`
- an executor in `action_executor.py`
- a service wrapper in `tg_actions.py`
- a risk/confirmation rule in `action_policy.py`

That is why “Pyrogram supports it” is not the same as “our bot can already do it”.

## Local Files Related To This Reference

- `pyrogram_capabilities.json`
- `action_registry.py`
- `action_policy.py`
- `action_executor.py`
- `command_router.py`
- `tg_actions.py`
