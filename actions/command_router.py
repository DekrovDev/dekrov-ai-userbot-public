from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from .action_models import ActionContext, ActionRequest, ResolvedActionTarget
from .cross_chat_actions import CrossChatActionService
from .tg_actions import TelegramActionService


MESSAGE_ID_RE = re.compile(r"(?iu)(?:message|msg|\u0441\u043e\u043e\u0431\u0449\u0435\u043d\w*|#)\s*#?\s*(-?\d+)")
COUNT_RE = re.compile(r"(?iu)\b(\d{1,3})\b")
SEND_PREFIX_RE = re.compile(
    r'(?iu)^(?:send|post|upload|\u043e\u0442\u043f\u0440\u0430\u0432\u044c|\u0441\u043a\u0438\u043d\u044c|\u043f\u0435\u0440\u0435\u043a\u0438\u043d\u044c)\b'
)
MEDIA_GROUP_ITEM_RE = re.compile(
    r'(?iu)(photo|image|picture|video|audio|track|music|document|file|doc|'
    r'\u0444\u043e\u0442\w*|\u043a\u0430\u0440\u0442\u0438\u043d\w*|\u0438\u0437\u043e\u0431\u0440\u0430\u0436\u0435\u043d\w*|'
    r'\u0432\u0438\u0434\u0435\u043e\w*|\u0430\u0443\u0434\u0438\u043e\w*|\u0442\u0440\u0435\u043a\w*|\u043c\u0443\u0437\u044b\u043a\w*|'
    r'\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\w*|\u0444\u0430\u0439\u043b\w*)\s+(".*?"|\'.*?\'|[^,]+?)(?=(?:\s*,\s*|$))'
)
QUOTED_RE = re.compile(r'["\'](.+?)["\']')


@dataclass(slots=True)
class SessionTarget:
    kind: str
    reference: str | int
    label: str


@dataclass(slots=True)
class DraftEnvelope:
    text: str
    mode: str
    target_reference: str | int | None
    target_label: str | None
    reply_to_message_id: int | None
    chat_id: int
    created_at: str
    source_prompt: str


class CommandRouter:
    def __init__(self, tg_actions: TelegramActionService, cross_chat_actions: CrossChatActionService | None = None, user_memory_store=None) -> None:
        self._tg_actions = tg_actions
        self._cross_chat_actions = cross_chat_actions
        self._user_memory_store = user_memory_store
        self._session_targets: dict[int, SessionTarget] = {}
        self._drafts: dict[int, DraftEnvelope] = {}

    async def route(self, prompt: str, context: ActionContext) -> ActionRequest | None:
        normalized = " ".join((prompt or "").strip().split())
        if not normalized:
            return None
        lowered = normalized.casefold()

        direct_request = await self._route_direct_action(normalized, lowered, context)
        if direct_request is not None:
            self._remember_request_target(direct_request)
            return direct_request

        comment_request = await self._parse_post_comments_v2(normalized, lowered, context)
        if comment_request is not None:
            self._remember_request_target(comment_request)
            return comment_request

        comment_request = await self._parse_comment_channel_post_v2(normalized, lowered, context)
        if comment_request is not None:
            self._remember_request_target(comment_request)
            return comment_request

        if self._cross_chat_actions is not None:
            cross_request = self._cross_chat_actions.parse_request(prompt=normalized, current_chat_id=context.request_chat_id)
            if cross_request is not None:
                target = await self._build_cross_chat_target(cross_request.source_reference, context)
                secondary_target = None
                if cross_request.target_reference is not None:
                    secondary_target = await self._build_cross_chat_target(cross_request.target_reference, context)
                request = ActionRequest(
                    action_name="cross_chat_request",
                    raw_prompt=normalized,
                    context=context,
                    target=target,
                    secondary_target=secondary_target,
                    arguments={
                        "subaction": cross_request.action,
                        "source_reference": cross_request.source_reference,
                        "target_reference": cross_request.target_reference,
                        "query": cross_request.query,
                        "message_limit": cross_request.message_limit,
                        "within_hours": cross_request.within_hours,
                        "prefix_text": cross_request.prefix_text,
                    },
                    summary=self._cross_chat_actions.describe_request(cross_request),
                )
                self._remember_request_target(request)
                return request
        return None

    def record_selected_target(self, chat_id: int, target: ResolvedActionTarget) -> None:
        if target.lookup is None:
            return
        self._session_targets[chat_id] = SessionTarget(kind=target.kind, reference=target.lookup, label=target.label)

    def get_selected_target(self, chat_id: int) -> SessionTarget | None:
        return self._session_targets.get(chat_id)

    def save_draft(
        self,
        *,
        chat_id: int,
        text: str,
        mode: str,
        target_reference: str | int | None,
        target_label: str | None,
        reply_to_message_id: int | None,
        source_prompt: str,
    ) -> DraftEnvelope:
        envelope = DraftEnvelope(
            text=text,
            mode=mode,
            target_reference=target_reference,
            target_label=target_label,
            reply_to_message_id=reply_to_message_id,
            chat_id=chat_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            source_prompt=source_prompt,
        )
        self._drafts[chat_id] = envelope
        return envelope

    def get_draft(self, chat_id: int) -> DraftEnvelope | None:
        return self._drafts.get(chat_id)

    def supported_action_examples(self) -> list[str]:
        return [
            'send last 2 messages from this chat to Saved Messages',
            'send last 20 messages from @username to chat Karina',
            'send "hello there" to chat Karina',
            'reply "ok"',
            'clear chat',
            'clear last 5 messages',
            'find in chat @username',
            'copy message to Saved Messages',
            'copy message 123 to Saved Messages caption "Updated"',
            'delete this chat',
            'get user info about @username',
            'send photo "C:\\media\\cat.jpg" to chat Karina',
            'send video "C:\\media\\clip.mp4" caption "Latest cut" to chat Karina',
            'send video note "C:\\media\\note.mp4" to chat Karina',
            'send animation "C:\\media\\loop.gif" to Saved Messages',
            'send document "C:\\docs\\report.pdf" caption "Latest version" to Saved Messages',
            'send audio "C:\\music\\track.mp3" caption "listen" to @username',
            'send voice "C:\\voice\\note.ogg" to chat Karina',
            'send media group photo "C:\\media\\a.jpg", video "C:\\media\\b.mp4" caption "Album" to chat Karina',
            'send contact "+123456789" first_name "John" last_name "Doe" to chat Karina',
            'add @username to contacts',
            'add replied user to contacts',
            'add @username to contacts as John Doe',
            'remove @username from contacts',
            'delete contact @username',
            'send location 41.9028, 12.4964 to Saved Messages',
            'send venue 41.9028, 12.4964 title "Cafe Roma" address "Via Roma 1" to chat Karina',
            'send poll "Best option?" options "Yes" | "No" | "Maybe" to chat Karina',
            'send sticker "CAACAgIAAxkBAA..." to @username',
            'remove buttons from message 123',
            'set button "Open" url "https://example.com" on message 123',
            'edit caption of message 123 to "New caption"',
            'replace media in message 123 with photo "C:\\media\\new.jpg" caption "Updated"',
            'delete my last 3 messages',
            'удали мои последние 3 сообщения',
            'edit message 123 to "new text"',
            'delete message 123',
            'forward replied message to @username',
            'pin replied message',
            'unpin all messages',
            'mark current chat as read',
            'archive this chat',
            'unarchive this chat',
            'join https://t.me/example',
            'leave this chat',
            'export invite link for @opsnews',
            'create invite link name "VIP" limit 5 for @opsnews',
            'approve join request for replied user in this chat',
            'decline join request for @username in @opsnews',
            'ban replied user',
            'unban replied user',
            'set chat title "New Title"',
            'set chat description "New Description"',
            'set chat photo "C:\\media\\avatar.jpg"',
            'delete chat photo',
            'set chat permissions to text only',
            'mute replied user',
            'unmute replied user',
            'promote replied user',
            'make @username admin in this chat',
            'set admin title "Moderator" for replied user',
            'unpin all messages in this chat',
            'clear all pins in @opsnews',
            'export invite link for @opsnews',
            'create invite link name "VIP" limit 5 for @opsnews',
            'revoke invite link "https://t.me/+example" for @opsnews',
            'select chat Karina',
            'read reply context',
            'draft send "hello" to chat Karina',
        ]
    async def _route_direct_action(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        request = await self._parse_select_target_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_delete_own_recent_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_history_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_clear_chat_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send_media_group(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send_structured(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send_media(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send_to_linked_chat_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_reply_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_copy_with_caption_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_forward_or_copy_to_linked_chat_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_forward_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_delete_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_select_target(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_read_reply_context(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_chat_history(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_member_lookup_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_linked_chat_lookup_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_post_comments_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_comment_channel_post_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_info_lookup(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_mark_read(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_archive(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_blocking(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_join_leave(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_chat_permissions_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_member_restrictions_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_ban(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_chat_photo_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_title_description(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_delete(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_edit_caption(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_edit_media(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_edit(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_pin(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_reaction(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_reply(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_forward_or_copy(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_draft(normalized, lowered, context)
        if request is not None:
            return request
        return None

    def supported_action_examples(self) -> list[str]:
        return [
            'create supergroup "Hyena 228" username "reqnuinkvko"',
            'create channel "Ops News" description "Internal updates" username "opsnews"',
            'send last 2 messages from this chat to Saved Messages',
            'send last 20 messages from @username to chat Karina',
            'send "hello there" to chat Karina',
            'reply "ok"',
            'clear chat',
            'clear last 5 messages',
            'find in chat @username',
            'copy message to Saved Messages',
            'delete this chat',
            'get user info about @username',
            'list members in this chat',
            'find members "john" in @opsnews',
            'inspect admins in this chat',
            'show permissions for replied user in this chat',
            'list banned members in @opsnews',
            'show linked chat for @opsnews',
            'show discussion chat for this chat',
            'inspect linked channel for this chat',
            'show comments for post 123 in @opsnews',
            'show 5 comments for post 123 in @opsnews',
            'comment "Nice update" on post 123 in @opsnews',
            'comment "Looks good"',
            'send "hello team" to linked chat',
            'copy replied message to linked channel of @opsnews',
            'forward message 123 to discussion chat',
            'send photo "C:\\media\\cat.jpg" to chat Karina',
            'send video "C:\\media\\clip.mp4" caption "Latest cut" to chat Karina',
            'send video note "C:\\media\\note.mp4" to chat Karina',
            'send animation "C:\\media\\loop.gif" to Saved Messages',
            'send document "C:\\docs\\report.pdf" caption "Latest version" to Saved Messages',
            'send audio "C:\\music\\track.mp3" caption "listen" to @username',
            'send voice "C:\\voice\\note.ogg" to chat Karina',
            'send media group photo "C:\\media\\a.jpg", video "C:\\media\\b.mp4" caption "Album" to chat Karina',
            'send contact "+123456789" first_name "John" last_name "Doe" to chat Karina',
            'add @username to contacts',
            'add replied user to contacts',
            'remove @username from contacts',
            'send location 41.9028, 12.4964 to Saved Messages',
            'send venue 41.9028, 12.4964 title "Cafe Roma" address "Via Roma 1" to chat Karina',
            'send poll "Best option?" options "Yes" | "No" | "Maybe" to chat Karina',
            'send dice 🎯 to Saved Messages',
            'send sticker "CAACAgIAAxkBAA..." to @username',
            'edit message 123 to "new text"',
            'delete message 123',
            'forward replied message to @username',
            'pin replied message',
            'unpin all messages',
            'mark current chat as read',
            'archive this chat',
            'unarchive this chat',
            'join https://t.me/example',
            'leave this chat',
            'ban replied user',
            'unban replied user',
            'set chat title "New Title"',
            'set chat description "New Description"',
            'set chat photo "C:\\media\\avatar.jpg"',
            'delete chat photo',
            'set chat permissions to text only',
            'mute replied user',
            'unmute replied user',
            'promote replied user',
            'make @username admin in this chat',
            'set admin title "Moderator" for replied user',
            'select chat Karina',
            'read reply context',
            'draft send "hello" to chat Karina',
        ]
    async def _route_direct_action(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        request = await self._parse_create_group_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_select_target_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_delete_own_recent_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_history_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_clear_chat_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send_media_group(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send_structured(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send_media(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send_to_linked_chat_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_reply_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_copy_with_caption_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_forward_or_copy_to_linked_chat_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_forward_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_delete_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_select_target(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_read_reply_context(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_chat_history(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_member_lookup_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_linked_chat_lookup_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_post_comments_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_comment_channel_post_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_info_lookup(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_mark_read(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_archive(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_blocking(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_join_leave(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_ban(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_title_description(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_delete(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_edit_reply_markup_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_edit_media_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_edit_caption_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_edit(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_pin(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_reaction(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_reply(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_forward_or_copy(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_draft(normalized, lowered, context)
        if request is not None:
            return request
        return None

    async def _parse_create_group_shortcuts(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not any(
            marker in lowered
            for marker in (
                "создай",
                "создать",
                "сделай",
                "открой",
                "create",
                "make",
                "new group",
            )
        ):
            return None
        if not any(
            marker in lowered
            for marker in ("груп", "супергруп", "group", "supergroup", "чат", "бесед")
        ):
            return None

        title = None
        for pattern in (
            r'(?iu)(?:с\s+названи(?:ем|е)|назови|название|title|name(?:\s+it)?)\s+[\"«“](.+?)[\"»”]',
            r'(?iu)(?:групп\w*|супергрупп\w*|group|supergroup)\s+[\"«“](.+?)[\"»”]',
            r'(?iu)(?:с\s+названи(?:ем|е)|title|name(?:\s+it)?)\s+(.+?)(?:\s+(?:и|and)\s+(?:кинь|скинь|дай|send|drop|share)\b|$)',
        ):
            match = re.search(pattern, normalized)
            if match:
                title = self._strip_wrapping_quotes(match.group(1).strip(" .,!?:;"))
                break

        username = None
        username_match = re.search(
            r'(?iu)(?:юзернейм|username|user\s+name|ник)\s*[:=]?\s*@?[\"«“]?([A-Za-z][A-Za-z0-9_]{3,31})[\"»”]?',
            normalized,
        )
        if username_match:
            username = username_match.group(1).strip()

        if not title:
            return None

        wants_link = self._prompt_requests_created_chat_link(lowered)

        target = ResolvedActionTarget(
            kind="chat",
            lookup=None,
            label=title,
            source="planned_creation",
        )
        summary = f'Create a new group "{title}"'
        arguments: dict[str, object] = {"title": title}
        if username:
            summary += f" with username @{username}"
            arguments["username"] = username
        if wants_link:
            summary += " and share a link"
            arguments["return_link"] = True
        return ActionRequest(
            action_name="create_group",
            raw_prompt=normalized,
            context=context,
            target=target,
            arguments=arguments,
            summary=summary,
        )

    async def _parse_create_channel_shortcuts(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not any(marker in lowered for marker in ("create", "make", "open", "start", "создай", "сделай", "channel", "канал")):
            return None
        match = re.match(
            r'(?iu)^(?:create|make|open|start|создай|сделай)\s+(?:new\s+|нов\w+\s+)?(?:channel|канал\w*)\s+(.+)$',
            normalized,
        )
        if not match:
            return None
        remainder = match.group(1).strip()
        if not remainder:
            return None

        description = None
        description_match = re.search(
            r'(?iu)(?:description|desc|описани\w*)\s+(".*?"|\'.*?\')',
            remainder,
        )
        if description_match:
            description = self._strip_wrapping_quotes(description_match.group(1).strip())
            remainder = f"{remainder[:description_match.start()]} {remainder[description_match.end():]}".strip()

        username = None
        username_match = re.search(
            r'(?iu)(?:username|user\s+name|юзернейм|ник)\s*[:=]?\s*@?([A-Za-z][A-Za-z0-9_]{3,31})',
            remainder,
        )
        if username_match:
            username = username_match.group(1).strip()
            remainder = f"{remainder[:username_match.start()]} {remainder[username_match.end():]}".strip()

        title = None
        title_match = re.search(
            r'(?iu)(?:title|name|названи\w*)\s+(".*?"|\'.*?\')',
            remainder,
        )
        if title_match:
            title = self._strip_wrapping_quotes(title_match.group(1).strip())
            remainder = f"{remainder[:title_match.start()]} {remainder[title_match.end():]}".strip()

        if not title:
            title = self._strip_wrapping_quotes(remainder.strip(" ,"))
        if not title:
            return None

        wants_link = self._prompt_requests_created_chat_link(lowered)

        target = ResolvedActionTarget(
            kind="chat",
            lookup=None,
            label=title,
            source="planned_creation",
        )
        arguments: dict[str, object] = {"title": title}
        if description:
            arguments["description"] = description
        if username:
            arguments["username"] = username
        if wants_link:
            arguments["return_link"] = True
        summary = f'Create a new channel "{title}"'
        if username:
            summary += f" with username @{username}"
        if wants_link:
            summary += " and share a link"
        return ActionRequest(
            action_name="create_channel",
            raw_prompt=normalized,
            context=context,
            target=target,
            arguments=arguments,
            summary=summary,
        )

    def _prompt_requests_created_chat_link(self, lowered_prompt: str) -> bool:
        normalized = " ".join((lowered_prompt or "").split())
        if not normalized:
            return False
        return any(
            marker in normalized
            for marker in (
                "link",
                "invite",
                "url",
                "\u0441\u0441\u044b\u043b",
                "\u0438\u043d\u0432\u0430\u0439\u0442",
                "\u043f\u0440\u0438\u0433\u043b\u0430\u0448\u0435\u043d",
            )
        )

    async def _parse_select_target_shortcuts(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        patterns = (
            r"(?iu)^(?:выбери|используй|поставь|сделай|select|use|set)\s+"
            r"(?P<kind>чат|диалог|канал|цель|пользователя|пользователь|юзера|контакт|chat|dialog|channel|target|user|contact)\s+"
            r"(?P<target>.+)$",
        )
        user_kinds = {"пользователя", "пользователь", "юзера", "контакт", "user", "contact"}
        for pattern in patterns:
            match = re.match(pattern, normalized)
            if not match:
                continue
            raw_target = self._strip_wrapping_quotes(match.group("target").strip())
            if not raw_target:
                continue
            kind = match.group("kind").casefold()
            if kind in user_kinds:
                target = await self._build_user_target(raw_target, context)
            else:
                target = await self._build_chat_target(raw_target, context)
            return ActionRequest(
                action_name="select_target",
                raw_prompt=normalized,
                context=context,
                target=target,
                summary=f"Select active target: {target.label}",
            )
        return None

    async def _parse_history_shortcuts(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not any(
            marker in lowered
            for marker in (
                "истори",
                "последние сообщения",
                "последние соо",
                "show history",
                "chat history",
                "recent messages",
                "покажи историю",
            )
        ):
            return None
        limit = self._extract_count(normalized, default=20)
        target_ref = self._extract_target_after_preposition(normalized, ("из", "from", "в", "for", "чата", "chat"))
        target = await self._build_chat_target(target_ref, context)
        return ActionRequest(
            action_name="get_chat_history",
            raw_prompt=normalized,
            context=context,
            target=target,
            arguments={"limit": limit},
            summary=f"Read the last {limit} messages from {target.label}",
        )

    async def _parse_clear_chat_shortcuts(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not any(
            marker in lowered
            for marker in (
                "clear chat",
                "clear history",
                "delete chat",
                "\u043e\u0447\u0438\u0441\u0442\u0438 \u0447\u0430\u0442",
                "\u043e\u0447\u0438\u0441\u0442\u0438 \u0438\u0441\u0442\u043e\u0440\u0438\u044e",
                "\u0443\u0434\u0430\u043b\u0438 \u0447\u0430\u0442",
            )
        ):
            return None
        limit = self._extract_count(normalized, default=50)
        target_ref = self._extract_target_after_preposition(
            normalized,
            ("to", "for", "from", "chat", "dialog", "channel", "\u0432", "\u0438\u0437", "\u0447\u0430\u0442\u0435", "\u0434\u0438\u0430\u043b\u043e\u0433\u0435", "\u043a\u0430\u043d\u0430\u043b\u0435"),
        )
        target = await self._build_chat_target(target_ref, context)
        return ActionRequest(
            action_name="clear_history",
            raw_prompt=normalized,
            context=context,
            target=target,
            arguments={"limit": limit},
            summary=f"Clear recent history in {target.label}",
        )
    async def _parse_clear_chat_shortcuts(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        explicit_current_chat = {
            "delete this chat",
            "delete chat",
            "clear this chat",
            "clear chat",
            "\u043e\u0447\u0438\u0441\u0442\u0438 \u044d\u0442\u043e\u0442 \u0447\u0430\u0442",
            "\u043e\u0447\u0438\u0441\u0442\u0438 \u0447\u0430\u0442",
            "\u0443\u0434\u0430\u043b\u0438 \u044d\u0442\u043e\u0442 \u0447\u0430\u0442",
            "\u0443\u0434\u0430\u043b\u0438 \u0447\u0430\u0442",
        }
        if lowered in explicit_current_chat:
            target = await self._build_chat_target(None, context)
            return ActionRequest(
                action_name="clear_history",
                raw_prompt=normalized,
                context=context,
                target=target,
                arguments={"limit": 50},
                summary=f"Clear recent history in {target.label}",
            )
        if not any(
            marker in lowered
            for marker in (
                "clear chat",
                "clear history",
                "delete chat",
                "\u043e\u0447\u0438\u0441\u0442\u0438 \u0447\u0430\u0442",
                "\u043e\u0447\u0438\u0441\u0442\u0438 \u0438\u0441\u0442\u043e\u0440\u0438\u044e",
                "\u0443\u0434\u0430\u043b\u0438 \u0447\u0430\u0442",
            )
        ):
            return None
        limit = self._extract_count(normalized, default=50)
        target_ref = self._extract_target_after_preposition(
            normalized,
            ("to", "for", "from", "chat", "dialog", "channel", "\u0432", "\u0438\u0437", "\u0447\u0430\u0442\u0435", "\u0434\u0438\u0430\u043b\u043e\u0433\u0435", "\u043a\u0430\u043d\u0430\u043b\u0435"),
        )
        target = await self._build_chat_target(target_ref, context)
        return ActionRequest(
            action_name="clear_history",
            raw_prompt=normalized,
            context=context,
            target=target,
            arguments={"limit": limit},
            summary=f"Clear recent history in {target.label}",
        )
    async def _parse_send_shortcuts(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        send_patterns = (
            r'(?iu)^(?:send|write|post|upload|\u043e\u0442\u043f\u0440\u0430\u0432\u044c|\u0441\u043a\u0438\u043d\u044c|\u043d\u0430\u043f\u0438\u0448\u0438)\s+(.+?)\s+(?:to|into|\u0432)\s+(?:chat\s+|dialog\s+|channel\s+|\u0447\u0430\u0442\s+|\u0434\u0438\u0430\u043b\u043e\u0433\s+|\u043a\u0430\u043d\u0430\u043b\s+)?(.+)$',
        )
        for pattern in send_patterns:
            match = re.match(pattern, normalized)
            if not match:
                continue
            text = self._strip_wrapping_quotes(match.group(1).strip())
            target_ref = self._normalize_target_reference(match.group(2))
            if not text:
                continue
            if self._looks_like_linked_target_reference(target_ref):
                continue
            target = await self._build_chat_target(target_ref, context)
            return ActionRequest(
                action_name="send_message",
                raw_prompt=normalized,
                context=context,
                target=target,
                arguments={"text": text},
                summary=f"Send a message to {target.label}",
            )
        if lowered in {
            "send this text",
            "reply with draft",
            "\u043e\u0442\u043f\u0440\u0430\u0432\u044c \u044d\u0442\u043e\u0442 \u0442\u0435\u043a\u0441\u0442",
            "\u043e\u0442\u043f\u0440\u0430\u0432\u044c \u0434\u0440\u0430\u0444\u0442",
        }:
            return None
        return None
    async def _parse_send_media(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not self._looks_like_send_command(lowered):
            return None
        match = re.match(
            r'(?iu)^(?:send|post|upload|\u043e\u0442\u043f\u0440\u0430\u0432\u044c|\u0441\u043a\u0438\u043d\u044c|\u043f\u0435\u0440\u0435\u043a\u0438\u043d\u044c)\s+'
            r'(video(?:\s+note)?|video_note|round\s+video|circle\s+video|photo|image|picture|video|animation|gif|document|file|doc|audio|track|music|song|voice(?:\s+message)?|voice(?:\s+note)?|sticker|'
            r'\u0444\u043e\u0442\w*|\u043a\u0430\u0440\u0442\u0438\u043d\w*|\u0438\u0437\u043e\u0431\u0440\u0430\u0436\u0435\u043d\w*|'
            r'\u0432\u0438\u0434\u0435\u043e\w*|\u0440\u043e\u043b\u0438\u043a\w*|\u043a\u0440\u0443\u0436\u043e\u043a\w*|\u0432\u0438\u0434\u0435\u043e\u0441\u043e\u043e\u0431\u0449\u0435\u043d\w*|'
            r'\u0433\u0438\u0444\w*|\u0430\u043d\u0438\u043c\u0430\u0446\w*|'
            r'\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\w*|\u0444\u0430\u0439\u043b\w*|\u0430\u0443\u0434\u0438\u043e\w*|\u0442\u0440\u0435\u043a\w*|\u043c\u0443\u0437\u044b\u043a\w*|'
            r'\u0433\u043e\u043b\u043e\u0441\u043e\u0432\w*|\u0441\u0442\u0438\u043a\u0435\u0440\w*)\s+'
            r'(.+?)(?=(?:\s+(?:caption|with\s+caption|\u043f\u043e\u0434\u043f\u0438\u0441\u044c|\u0441\s+\u043f\u043e\u0434\u043f\u0438\u0441\u044c\u044e)\s+|\s+(?:to|into|\u0432)\s+|$))'
            r'(?:\s+(?:caption|with\s+caption|\u043f\u043e\u0434\u043f\u0438\u0441\u044c|\u0441\s+\u043f\u043e\u0434\u043f\u0438\u0441\u044c\u044e)\s+(.+?))?'
            r'(?:\s+(?:to|into|\u0432)\s+(?:chat\s+|dialog\s+|channel\s+|\u0447\u0430\u0442\s+|\u0434\u0438\u0430\u043b\u043e\u0433\s+|\u043a\u0430\u043d\u0430\u043b\s+)?(.+))?$',
            normalized,
        )
        if not match:
            return None
        media_kind = self._canonicalize_media_kind(match.group(1))
        asset = self._strip_wrapping_quotes(match.group(2).strip())
        caption_raw = (match.group(3) or "").strip()
        target_raw = self._normalize_target_reference(match.group(4))
        if not asset or media_kind is None:
            return None
        if self._looks_like_linked_target_reference(target_raw):
            return None
        action_names = {
            "photo": "send_photo",
            "video": "send_video",
            "video_note": "send_video_note",
            "animation": "send_animation",
            "document": "send_document",
            "audio": "send_audio",
            "voice": "send_voice",
            "sticker": "send_sticker",
        }
        argument_names = {
            "photo": "photo",
            "video": "video",
            "video_note": "video_note",
            "animation": "animation",
            "document": "document",
            "audio": "audio",
            "voice": "voice",
            "sticker": "sticker",
        }
        action_name = action_names.get(media_kind)
        argument_name = argument_names.get(media_kind)
        if action_name is None or argument_name is None:
            return None
        arguments = {argument_name: asset}
        if caption_raw and media_kind not in {"sticker", "video_note"}:
            arguments["caption"] = self._strip_wrapping_quotes(caption_raw)
        target = await self._build_chat_target(target_raw, context)
        return ActionRequest(
            action_name=action_name,
            raw_prompt=normalized,
            context=context,
            target=target,
            arguments=arguments,
            summary=f"Send {argument_name.replace('_', ' ')} to {target.label}",
        )

    async def _parse_send_media_group(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not self._looks_like_send_command(lowered):
            return None
        match = re.match(
            r'(?iu)^(?:send|post|upload|\u043e\u0442\u043f\u0440\u0430\u0432\u044c|\u0441\u043a\u0438\u043d\u044c|\u043f\u0435\u0440\u0435\u043a\u0438\u043d\u044c)\s+(?:media\s+group|album|\u0430\u043b\u044c\u0431\u043e\u043c|\u043c\u0435\u0434\u0438\u0430\u0433\u0440\u0443\u043f\u043f\u0430)\s+(.+?)'
            r'(?:\s+(?:caption|with\s+caption|\u043f\u043e\u0434\u043f\u0438\u0441\u044c|\u0441\s+\u043f\u043e\u0434\u043f\u0438\u0441\u044c\u044e)\s+(.+?))?'
            r'(?:\s+(?:to|into|\u0432)\s+(?:chat\s+|dialog\s+|channel\s+|\u0447\u0430\u0442\s+|\u0434\u0438\u0430\u043b\u043e\u0433\s+|\u043a\u0430\u043d\u0430\u043b\s+)?(.+))?$',
            normalized,
        )
        if not match:
            return None
        raw_items = (match.group(1) or "").strip()
        caption_raw = (match.group(2) or "").strip()
        target_raw = self._normalize_target_reference(match.group(3))
        if not raw_items:
            return None
        if self._looks_like_linked_target_reference(target_raw):
            return None
        items: list[dict[str, str]] = []
        cursor = 0
        for item_match in MEDIA_GROUP_ITEM_RE.finditer(raw_items):
            gap = raw_items[cursor:item_match.start()]
            if gap.strip(" ,"):
                return None
            kind = self._canonicalize_media_group_kind(item_match.group(1))
            media = self._strip_wrapping_quotes(item_match.group(2).strip())
            if not media or kind is None:
                return None
            items.append({"kind": kind, "media": media})
            cursor = item_match.end()
        if raw_items[cursor:].strip(" ,"):
            return None
        if len(items) < 2:
            return None
        if len(items) > 10:
            items = items[:10]
        target = await self._build_chat_target(target_raw, context)
        arguments: dict[str, object] = {"items": items}
        if caption_raw:
            arguments["caption"] = self._strip_wrapping_quotes(caption_raw)
        return ActionRequest(
            action_name="send_media_group",
            raw_prompt=normalized,
            context=context,
            target=target,
            arguments=arguments,
            summary=f"Send media group to {target.label}",
        )

    async def _parse_send_structured(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not self._looks_like_send_command(lowered):
            return None

        contact_match = re.match(
            r'(?iu)^(?:send|post|upload|\u043e\u0442\u043f\u0440\u0430\u0432\u044c|\u0441\u043a\u0438\u043d\u044c)\s+'
            r'(?:contact|\u043a\u043e\u043d\u0442\u0430\u043a\u0442\w*)\s+(".*?"|\'.*?\'|\S+)\s+'
            r'(?:first(?:_name)?|first\s+name|name|\u0438\u043c\u044f)\s+(".*?"|\'.*?\')'
            r'(?:\s+(?:last(?:_name)?|last\s+name|surname|\u0444\u0430\u043c\u0438\u043b\u0438\w*)\s+(".*?"|\'.*?\'))?'
            r'(?:\s+(?:to|into|\u0432)\s+(?:chat\s+|dialog\s+|channel\s+|\u0447\u0430\u0442\s+|\u0434\u0438\u0430\u043b\u043e\u0433\s+|\u043a\u0430\u043d\u0430\u043b\s+)?(.+))?$',
            normalized,
        )
        if contact_match:
            phone_number = self._strip_wrapping_quotes(contact_match.group(1).strip())
            first_name = self._strip_wrapping_quotes(contact_match.group(2).strip())
            last_name = self._strip_wrapping_quotes((contact_match.group(3) or "").strip()) or None
            target_ref = self._normalize_target_reference(contact_match.group(4))
            if not phone_number or not first_name:
                return None
            if self._looks_like_linked_target_reference(target_ref):
                return None
            target = await self._build_chat_target(target_ref, context)
            arguments: dict[str, object] = {
                "phone_number": phone_number,
                "first_name": first_name,
            }
            if last_name:
                arguments["last_name"] = last_name
            return ActionRequest(
                action_name="send_contact",
                raw_prompt=normalized,
                context=context,
                target=target,
                arguments=arguments,
                summary=f"Send contact to {target.label}",
            )

        location_match = re.match(
            r'(?iu)^(?:send|post|upload|\u043e\u0442\u043f\u0440\u0430\u0432\u044c|\u0441\u043a\u0438\u043d\u044c)\s+'
            r'(?:location|geo|point|\u043b\u043e\u043a\u0430\u0446\w*|\u0433\u0435\u043e\w*|\u0442\u043e\u0447\u043a\w*)\s+'
            r'(-?\d+(?:\.\d+)?)\s*(?:,|\s)\s*(-?\d+(?:\.\d+)?)(?:\s+(?:to|into|\u0432)\s+(?:chat\s+|dialog\s+|channel\s+|\u0447\u0430\u0442\s+|\u0434\u0438\u0430\u043b\u043e\u0433\s+|\u043a\u0430\u043d\u0430\u043b\s+)?(.+))?$',
            normalized,
        )
        if location_match:
            try:
                latitude = float(location_match.group(1))
                longitude = float(location_match.group(2))
            except ValueError:
                return None
            target_ref = self._normalize_target_reference(location_match.group(3))
            if self._looks_like_linked_target_reference(target_ref):
                return None
            target = await self._build_chat_target(target_ref, context)
            return ActionRequest(
                action_name="send_location",
                raw_prompt=normalized,
                context=context,
                target=target,
                arguments={"latitude": latitude, "longitude": longitude},
                summary=f"Send location to {target.label}",
            )

        venue_match = re.match(
            r'(?iu)^(?:send|post|upload|\u043e\u0442\u043f\u0440\u0430\u0432\u044c|\u0441\u043a\u0438\u043d\u044c)\s+'
            r'(?:venue|place|\u043c\u0435\u0441\u0442\w*|\u043b\u043e\u043a\u0430\u0446\u0438\u044f\s+\u043c\u0435\u0441\u0442\u0430)\s+'
            r'(-?\d+(?:\.\d+)?)\s*(?:,|\s)\s*(-?\d+(?:\.\d+)?)\s+'
            r'(?:title|name|\u043d\u0430\u0437\u0432\u0430\u043d\u0438\w*)\s+(".*?"|\'.*?\')\s+'
            r'(?:address|\u0430\u0434\u0440\u0435\u0441\w*)\s+(".*?"|\'.*?\')'
            r'(?:\s+(?:to|into|\u0432)\s+(?:chat\s+|dialog\s+|channel\s+|\u0447\u0430\u0442\s+|\u0434\u0438\u0430\u043b\u043e\u0433\s+|\u043a\u0430\u043d\u0430\u043b\s+)?(.+))?$',
            normalized,
        )
        if venue_match:
            try:
                latitude = float(venue_match.group(1))
                longitude = float(venue_match.group(2))
            except ValueError:
                return None
            title = self._strip_wrapping_quotes(venue_match.group(3).strip())
            address = self._strip_wrapping_quotes(venue_match.group(4).strip())
            target_ref = self._normalize_target_reference(venue_match.group(5))
            if not title or not address:
                return None
            if self._looks_like_linked_target_reference(target_ref):
                return None
            target = await self._build_chat_target(target_ref, context)
            return ActionRequest(
                action_name="send_venue",
                raw_prompt=normalized,
                context=context,
                target=target,
                arguments={
                    "latitude": latitude,
                    "longitude": longitude,
                    "title": title,
                    "address": address,
                },
                summary=f"Send venue to {target.label}",
            )

        poll_match = re.match(
            r'(?iu)^(?:send|post|upload|\u043e\u0442\u043f\u0440\u0430\u0432\u044c|\u0441\u043a\u0438\u043d\u044c)\s+'
            r'(?:poll|survey|\u043e\u043f\u0440\u043e\u0441\w*|\u0433\u043e\u043b\u043e\u0441\u043e\u0432\u0430\u043d\u0438\w*)\s+(".*?"|\'.*?\')\s+'
            r'(?:options|variants|\u0432\u0430\u0440\u0438\u0430\u043d\u0442\w*|\u043e\u0442\u0432\u0435\u0442\w*)\s+(.+?)'
            r'(?:\s+(?:to|into|\u0432)\s+(?:chat\s+|dialog\s+|channel\s+|\u0447\u0430\u0442\s+|\u0434\u0438\u0430\u043b\u043e\u0433\s+|\u043a\u0430\u043d\u0430\u043b\s+)?(.+))?$',
            normalized,
        )
        if poll_match:
            question = self._strip_wrapping_quotes(poll_match.group(1).strip())
            raw_options = (poll_match.group(2) or "").strip()
            target_ref = self._normalize_target_reference(poll_match.group(3))
            options = self._split_poll_options(raw_options)
            if not question or len(options) < 2:
                return None
            if self._looks_like_linked_target_reference(target_ref):
                return None
            target = await self._build_chat_target(target_ref, context)
            return ActionRequest(
                action_name="send_poll",
                raw_prompt=normalized,
                context=context,
                target=target,
                arguments={"question": question, "options": options[:10]},
                summary=f"Send poll to {target.label}",
            )

        return None

    async def _parse_send_dice_shortcuts(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not any(marker in lowered for marker in ("send", "post", "upload", "throw", "roll", "отправь", "скинь", "перекинь", "кинь")):
            return None
        match = re.match(
            r'(?iu)^(?:send|post|upload|throw|roll|отправь|скинь|перекинь|кинь)\s+(.+?)(?:\s+(?:to|into|в)\s+(?:chat\s+|dialog\s+|channel\s+|чат\s+|диалог\s+|канал\s+)?(.+))?$',
            normalized,
        )
        if not match:
            return None
        dice_part = self._strip_wrapping_quotes((match.group(1) or "").strip())
        emoji = self._canonicalize_dice_emoji(dice_part)
        if emoji is None:
            return None
        target_ref = self._normalize_target_reference(match.group(2))
        if self._looks_like_linked_target_reference(target_ref):
            return None
        target = await self._build_chat_target(target_ref, context)
        return ActionRequest(
            action_name="send_dice",
            raw_prompt=normalized,
            context=context,
            target=target,
            arguments={"emoji": emoji},
            summary=f"Send dice {emoji} to {target.label}",
        )

    async def _parse_send_to_linked_chat_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not self._looks_like_send_command(lowered):
            return None
        match = re.match(
            r'(?iu)^(?:send|write|post|\u043e\u0442\u043f\u0440\u0430\u0432\u044c|\u0441\u043a\u0438\u043d\u044c|\u043d\u0430\u043f\u0438\u0448\u0438)\s+(.+?)\s+'
            r'(?:to|into|\u0432)\s+(?:the\s+)?(?:linked\s+(?:chat|channel)|discussion\s+(?:chat|group)|'
            r'\u0441\u0432\u044f\u0437\u0430\u043d\w*\s+(?:\u0447\u0430\u0442|\u043a\u0430\u043d\u0430\u043b)|'
            r'(?:\u0447\u0430\u0442|\u0433\u0440\u0443\u043f\u043f\w*)\s+\u043e\u0431\u0441\u0443\u0436\u0434\u0435\u043d\w*)'
            r'(?:\s+(?:of|for|in|\u0434\u043b\u044f|\u0443)\s+(.+))?$',
            normalized,
        )
        if not match:
            return None
        text = self._strip_wrapping_quotes((match.group(1) or "").strip())
        if not text or self._looks_like_non_text_send_payload(text):
            return None
        source_ref = self._resolve_chat_target_reference_or_current(match.group(2), context)
        source_target = await self._build_chat_target(source_ref, context)
        return ActionRequest(
            action_name="send_to_linked_chat",
            raw_prompt=normalized,
            context=context,
            target=source_target,
            arguments={"text": text},
            summary=f"Send a message to the linked chat for {source_target.label}",
        )

    async def _parse_reply_shortcuts(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if context.reply_to_message_id is None:
            return None
        reply_patterns = (
            r'(?iu)^(?:ответь|напиши в ответ|reply|answer)\s+'
            r'(?:ему|ей|им|на это|на это сообщение)?\s*(.+)$',
        )
        for pattern in reply_patterns:
            match = re.match(pattern, normalized)
            if not match:
                continue
            text = self._strip_wrapping_quotes(match.group(1).strip())
            if not text:
                continue
            target = ResolvedActionTarget(
                kind="message",
                lookup=context.request_chat_id,
                label=f"message #{context.reply_to_message_id}",
                chat_id=context.request_chat_id,
                message_id=context.reply_to_message_id,
                source="reply_context",
            )
            return ActionRequest(
                action_name="reply_to_message",
                raw_prompt=normalized,
                context=context,
                target=target,
                arguments={"text": text},
                summary=f"Reply to message #{context.reply_to_message_id}",
            )
        return None

    async def _parse_forward_shortcuts(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if context.reply_to_message_id is None:
            return None
        if not any(marker in lowered for marker in ("перекинь", "перешли", "forward", "copy", "скопируй")):
            return None
        target_ref = self._extract_target_after_preposition(normalized, ("в", "to", "chat", "чат"))
        if not target_ref:
            return None
        action_name = "copy_message" if any(marker in lowered for marker in ("copy", "скопируй")) else "forward_message"
        target = await self._build_chat_target(target_ref, context)
        source = ResolvedActionTarget(
            kind="message",
            lookup=context.request_chat_id,
            label=f"message #{context.reply_to_message_id}",
            chat_id=context.request_chat_id,
            message_id=context.reply_to_message_id,
            source="reply_context",
        )
        return ActionRequest(
            action_name=action_name,
            raw_prompt=normalized,
            context=context,
            target=source,
            secondary_target=target,
            summary=f"{'Copy' if action_name == 'copy_message' else 'Forward'} message #{context.reply_to_message_id} to {target.label}",
        )

    async def _parse_forward_or_copy_to_linked_chat_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not any(marker in lowered for marker in ("forward", "copy", "\u043f\u0435\u0440\u0435\u043a\u0438\u043d\u044c", "\u043f\u0435\u0440\u0435\u0448\u043b\u0438", "\u0441\u043a\u043e\u043f\u0438\u0440\u0443\u0439")):
            return None
        match = re.search(
            r'(?iu)\b(?:to|into|\u0432)\s+(?:the\s+)?(?:linked\s+(?:chat|channel)|discussion\s+(?:chat|group)|'
            r'\u0441\u0432\u044f\u0437\u0430\u043d\w*\s+(?:\u0447\u0430\u0442|\u043a\u0430\u043d\u0430\u043b)|'
            r'(?:\u0447\u0430\u0442|\u0433\u0440\u0443\u043f\u043f\w*)\s+\u043e\u0431\u0441\u0443\u0436\u0434\u0435\u043d\w*)'
            r'(?:\s+(?:of|for|in|\u0434\u043b\u044f|\u0443)\s+(?P<chat>.+))?$',
            normalized,
        )
        if match is None:
            return None
        message_id = self._extract_message_id(normalized) or context.reply_to_message_id
        if message_id is None:
            return None
        action_name = "copy_to_linked_chat" if any(marker in lowered for marker in ("copy", "\u0441\u043a\u043e\u043f\u0438\u0440\u0443\u0439")) else "forward_to_linked_chat"
        source_chat_ref = self._resolve_chat_target_reference_or_current(match.groupdict().get("chat"), context)
        source_chat_target = await self._build_chat_target(source_chat_ref, context)
        source_target = ResolvedActionTarget(
            kind="message",
            lookup=context.request_chat_id,
            label=f"message #{message_id}",
            chat_id=context.request_chat_id,
            message_id=message_id,
            source="reply_context" if context.reply_to_message_id == message_id else "explicit",
        )
        verb = "Copy" if action_name == "copy_to_linked_chat" else "Forward"
        return ActionRequest(
            action_name=action_name,
            raw_prompt=normalized,
            context=context,
            target=source_target,
            secondary_target=source_chat_target,
            summary=f"{verb} message #{message_id} to the linked chat for {source_chat_target.label}",
        )

    async def _parse_delete_shortcuts(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if context.reply_to_message_id is not None and lowered in {"удали это", "удали это сообщение", "delete this", "delete this message"}:
            target = ResolvedActionTarget(
                kind="message",
                lookup=context.request_chat_id,
                label=f"message #{context.reply_to_message_id}",
                chat_id=context.request_chat_id,
                message_id=context.reply_to_message_id,
                source="reply_context",
            )
            return ActionRequest(
                action_name="delete_message",
                raw_prompt=normalized,
                context=context,
                target=target,
                summary=f"Delete message #{context.reply_to_message_id}",
            )
        return None

    async def _parse_select_target(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        pattern = (
            r"(?iu)^(?:select|use|set|выбери|используй|поставь)\s+"
            r"(?P<kind>chat|target|user|contact|чат|цель|пользователя|пользователь|юзера|контакт)\s+"
            r"(?P<target>.+)$"
        )
        match = re.match(pattern, normalized)
        if not match:
            return None
        raw_target = self._strip_wrapping_quotes(match.group("target").strip())
        if not raw_target:
            return None
        kind = match.group("kind").casefold()
        if kind in {"user", "contact", "пользователя", "пользователь", "юзера", "контакт"}:
            target = await self._build_user_target(raw_target, context)
        else:
            target = await self._build_chat_target(raw_target, context)
        return ActionRequest(
            action_name="select_target",
            raw_prompt=normalized,
            context=context,
            target=target,
            summary=f"Select active target: {target.label}",
        )

    async def _parse_read_reply_context(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if context.reply_to_message_id is None:
            return None
        markers = ("reply context", "read reply", "context of reply", "что в этом сообщении", "прочитай реплай", "контекст реплая")
        if not any(marker in lowered for marker in markers):
            return None
        target = ResolvedActionTarget(
            kind="message",
            lookup=context.request_chat_id,
            label=f"message #{context.reply_to_message_id} in current chat",
            chat_id=context.request_chat_id,
            message_id=context.reply_to_message_id,
            user_id=context.reply_to_user_id,
            source="reply_context",
        )
        return ActionRequest(
            action_name="read_reply_context",
            raw_prompt=normalized,
            context=context,
            target=target,
            summary=f"Read replied message context from #{context.reply_to_message_id}",
        )

    async def _parse_chat_history(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not any(marker in lowered for marker in ("history", "recent messages", "последние", "история", "контекст")):
            return None
        if not any(marker in lowered for marker in ("show", "get", "read", "покажи", "прочитай", "дай", "скинь")):
            return None
        target_ref = self._extract_target_after_preposition(normalized, ("from", "of", "из", "в", "чата"))
        limit = self._extract_count(normalized, default=10)
        target = await self._build_chat_target(target_ref, context)
        return ActionRequest(
            action_name="get_chat_history",
            raw_prompt=normalized,
            context=context,
            target=target,
            arguments={"limit": limit},
            summary=f"Read the last {limit} messages from {target.label}",
        )

    async def _parse_info_lookup(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if any(
            marker in lowered
            for marker in (
                "chat info",
                "info about chat",
                "инфо о чате",
                "информация о чате",
                "кто в чате",
                "кто в этом чате",
                "about this chat",
                "данные чата",
                "инфо чата",
                "инфо по чату",
                "что за чат",
                "расскажи о чате",
                "get chat info",
                "show chat info",
            )
        ):
            target_ref = self._extract_target_after_preposition(normalized, ("about", "for", "о", "про", "of"))
            target = await self._build_chat_target(target_ref, context)
            return ActionRequest(
                action_name="get_chat_info",
                raw_prompt=normalized,
                context=context,
                target=target,
                summary=f"Get chat info for {target.label}",
            )
        if any(
            marker in lowered
            for marker in (
                "user info",
                "info about user",
                "инфо о пользователе",
                "информация о пользователе",
                "кто такой",
                "about user",
                "кто это",
                "данные пользователя",
                "инфо по юзеру",
                "расскажи о пользователе",
                "get user info",
            )
        ):
            target_ref = self._extract_target_after_preposition(normalized, ("about", "for", "о", "про"))
            target = await self._build_user_target(target_ref, context)
            return ActionRequest(
                action_name="get_user_info",
                raw_prompt=normalized,
                context=context,
                target=target,
                summary=f"Get user info for {target.label}",
            )
        return None

    async def _parse_member_lookup_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        limit = min(self._extract_count(normalized, default=20), 50)

        async def _build_members_request(
            *,
            filter_name: str,
            filter_label: str,
            chat_raw: str | None,
            query_raw: str | None = None,
        ) -> ActionRequest:
            target_ref = self._resolve_chat_target_reference_or_current(chat_raw, context)
            target = await self._build_chat_target(target_ref, context)
            query = self._strip_wrapping_quotes((query_raw or "").strip())
            arguments: dict[str, object] = {
                "limit": limit,
                "filter_name": filter_name,
                "filter_label": filter_label,
            }
            if query:
                arguments["query"] = query
            summary = f"Inspect {filter_label} in {target.label}"
            if query:
                summary = f'Find {filter_label} matching "{query}" in {target.label}'
            return ActionRequest(
                action_name="get_chat_members",
                raw_prompt=normalized,
                context=context,
                target=target,
                arguments=arguments,
                summary=summary,
            )

        admin_patterns = (
            r'(?iu)^(?:show|get|list|inspect|read)(?:\s+\d{1,3})?\s+(?:chat\s+)?(?:admins|administrators)(?:\s+(?:in|for|of)\s+(?P<chat>.+))?$',
            r'(?iu)^(?:покажи|получи|список|посмотри|проверь)(?:\s+\d{1,3})?\s+(?:админ\w*|администратор\w*)(?:\s+(?:в|для)\s+(?P<chat>.+))?$',
        )
        for pattern in admin_patterns:
            match = re.match(pattern, normalized)
            if match is not None:
                return await _build_members_request(
                    filter_name="administrators",
                    filter_label="administrators",
                    chat_raw=match.groupdict().get("chat"),
                )

        banned_search_patterns = (
            r'(?iu)^(?:find|search)(?:\s+\d{1,3})?\s+(?:banned|kicked|blocked)\s+(?:members?|users?)\s+(?P<query>".*?"|\'.*?\'|.+?)(?:\s+(?:in|for)\s+(?P<chat>.+))?$',
            r'(?iu)^(?:найди|ищи|поищи)(?:\s+\d{1,3})?\s+(?:забаненн\w*|заблокированн\w*)(?:\s+(?:участник\w*|пользовател\w*))?\s+(?P<query>".*?"|\'.*?\'|.+?)(?:\s+в\s+(?P<chat>.+))?$',
        )
        for pattern in banned_search_patterns:
            match = re.match(pattern, normalized)
            if match is not None:
                return await _build_members_request(
                    filter_name="banned",
                    filter_label="banned members",
                    chat_raw=match.groupdict().get("chat"),
                    query_raw=match.groupdict().get("query"),
                )

        banned_patterns = (
            r'(?iu)^(?:show|get|list|inspect)(?:\s+\d{1,3})?\s+(?:banned|kicked|blocked)\s+(?:members?|users?)(?:\s+(?:in|for|of)\s+(?P<chat>.+))?$',
            r'(?iu)^(?:покажи|получи|список|посмотри)(?:\s+\d{1,3})?\s+(?:забаненн\w*|заблокированн\w*|банлист|бан-лист)(?:\s+(?:участник\w*|пользовател\w*))?(?:\s+в\s+(?P<chat>.+))?$',
        )
        for pattern in banned_patterns:
            match = re.match(pattern, normalized)
            if match is not None:
                return await _build_members_request(
                    filter_name="banned",
                    filter_label="banned members",
                    chat_raw=match.groupdict().get("chat"),
                )

        member_detail_patterns = (
            r'(?iu)^(?:show|get|inspect|read|check)\s+(?:member\s+)?(?:permissions|rights|status)(?:\s+(?:for|of)\s+(?P<user>.+?))?(?:\s+(?:in|for)\s+(?P<chat>.+))?$',
            r'(?iu)^(?:show|get|inspect|check)\s+(?:member|participant)\s+(?P<user>.+?)(?:\s+(?:in|for)\s+(?P<chat>.+))?$',
            r'(?iu)^(?:покажи|получи|посмотри|проверь)\s+(?:права|разрешения|статус)(?:\s+(?:для|у)\s+(?P<user>.+?))?(?:\s+в\s+(?P<chat>.+))?$',
            r'(?iu)^(?:покажи|получи|посмотри|проверь)\s+(?:участника|пользователя)\s+(?P<user>.+?)(?:\s+в\s+(?P<chat>.+))?$',
        )
        for pattern in member_detail_patterns:
            match = re.match(pattern, normalized)
            if match is None:
                continue
            user_ref = self._normalize_member_reference(match.groupdict().get("user"))
            if user_ref is None and context.reply_to_user_id is None:
                session_target = self.get_selected_target(context.request_chat_id)
                if session_target is None or session_target.kind != "user":
                    return None
            target = await self._build_user_target(user_ref, context)
            chat_ref = self._resolve_chat_target_reference_or_current(match.groupdict().get("chat"), context)
            chat_target = await self._build_chat_target(chat_ref, context)
            return ActionRequest(
                action_name="get_chat_member",
                raw_prompt=normalized,
                context=context,
                target=target,
                secondary_target=chat_target,
                summary=f"Inspect member state for {target.label} in {chat_target.label}",
            )

        member_search_patterns = (
            r'(?iu)^(?:find|search)(?:\s+\d{1,3})?\s+(?:chat\s+)?(?:members?|participants?)\s+(?P<query>".*?"|\'.*?\'|.+?)(?:\s+(?:in|for|of)\s+(?P<chat>.+))?$',
            r'(?iu)^(?:найди|ищи|поищи)(?:\s+\d{1,3})?\s+(?:участник\w*|пользовател\w*)\s+(?P<query>".*?"|\'.*?\'|.+?)(?:\s+в\s+(?P<chat>.+))?$',
        )
        for pattern in member_search_patterns:
            match = re.match(pattern, normalized)
            if match is not None:
                return await _build_members_request(
                    filter_name="search",
                    filter_label="matching members",
                    chat_raw=match.groupdict().get("chat"),
                    query_raw=match.groupdict().get("query"),
                )

        member_list_patterns = (
            r'(?iu)^(?:show|get|list)(?:\s+\d{1,3})?\s+(?:chat\s+)?(?:members?|participants?)(?:\s+(?:in|for|of)\s+(?P<chat>.+))?$',
            r'(?iu)^(?:покажи|список|получи|посмотри)(?:\s+\d{1,3})?\s+(?:участник\w*|пользовател\w*)(?:\s+в\s+(?P<chat>.+))?$',
        )
        for pattern in member_list_patterns:
            match = re.match(pattern, normalized)
            if match is not None:
                return await _build_members_request(
                    filter_name="recent",
                    filter_label="members",
                    chat_raw=match.groupdict().get("chat"),
                )

        return None

    async def _parse_linked_chat_lookup_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        patterns = (
            r'(?iu)^(?:show|get|inspect|read|check)\s+(?:linked\s+(?:chat|channel)|discussion\s+(?:chat|group))(?:\s+(?:for|of|in)\s+(?P<chat>.+))?$',
            r'(?iu)^(?:покажи|получи|посмотри|проверь)\s+(?:связанн\w*\s+(?:чат|канал)|чат\s+обсуждени\w*|канал\s+для\s+обсуждени\w*)(?:\s+(?:для|у|в)\s+(?P<chat>.+))?$',
        )
        for pattern in patterns:
            match = re.match(pattern, normalized)
            if match is None:
                continue
            chat_ref = self._resolve_chat_target_reference_or_current(match.groupdict().get("chat"), context)
            target = await self._build_chat_target(chat_ref, context)
            return ActionRequest(
                action_name="get_linked_chat_info",
                raw_prompt=normalized,
                context=context,
                target=target,
                summary=f"Inspect linked chat for {target.label}",
            )
        return None

    async def _parse_post_comments_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not any(marker in lowered for marker in ("comment", "comments", "discussion replies", "коммент", "комментар")):
            return None
        patterns = (
            r'(?iu)^(?:show|get|read|list|inspect)(?:\s+(?:last\s+)?(?P<count>\d{1,3}))?\s+(?:comments?|discussion\s+replies|replies)'
            r'(?:\s+(?:for|of|on|under)\s+(?:post|message|msg)?\s*#?(?P<message_id>\d+))?'
            r'(?:\s+(?:in|for)\s+(?P<chat>.+))?$',
            r'(?iu)^(?:\u043f\u043e\u043a\u0430\u0436\u0438|\u043f\u043e\u0441\u043c\u043e\u0442\u0440\u0438|\u043f\u0440\u043e\u0447\u0438\u0442\u0430\u0439|\u043f\u043e\u043b\u0443\u0447\u0438)(?:\s+(?:\u043f\u043e\u0441\u043b\u0435\u0434\u043d\w*\s+)?(?P<count>\d{1,3}))?\s+(?:\u043a\u043e\u043c\u043c\u0435\u043d\u0442\w*|\u043e\u0442\u0432\u0435\u0442\w*)'
            r'(?:\s+(?:\u043a|\u043f\u043e\u0434|\u0434\u043b\u044f)\s+(?:\u043f\u043e\u0441\u0442\w*|\u0441\u043e\u043e\u0431\u0449\u0435\u043d\w*)?\s*#?(?P<message_id>\d+))?'
            r'(?:\s+(?:\u0432|\u0438\u0437)\s+(?P<chat>.+))?$',
        )
        for pattern in patterns:
            match = re.match(pattern, normalized)
            if match is None:
                continue
            message_id_raw = match.groupdict().get("message_id")
            message_id = int(message_id_raw) if message_id_raw else context.reply_to_message_id
            if message_id is None:
                continue
            count_raw = match.groupdict().get("count")
            limit = max(1, min(int(count_raw), 20)) if count_raw else 5
            chat_ref = self._resolve_chat_target_reference_or_current(match.groupdict().get("chat"), context)
            target = await self._build_chat_target(chat_ref, context)
            return ActionRequest(
                action_name="get_post_comments",
                raw_prompt=normalized,
                context=context,
                target=target,
                arguments={"message_id": message_id, "limit": limit},
                summary=f"Read comments for post #{message_id} in {target.label}",
            )
        return None

    async def _parse_comment_channel_post_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not any(
            marker in lowered
            for marker in (
                "comment",
                "leave comment",
                "add comment",
                "\u043f\u0440\u043e\u043a\u043e\u043c\u043c\u0435\u043d\u0442",
                "\u043e\u0441\u0442\u0430\u0432\u044c \u043a\u043e\u043c\u043c\u0435\u043d\u0442",
                "\u0434\u043e\u0431\u0430\u0432\u044c \u043a\u043e\u043c\u043c\u0435\u043d\u0442",
            )
        ):
            return None
        patterns = (
            r'(?iu)^(?:comment|leave\s+comment|add\s+comment)\s+(?P<text>".*?"|\'.*?\')'
            r'(?:\s+(?:on|under|to|for)\s+(?:post|message|msg)?\s*#?(?P<message_id>\d+))?'
            r'(?:\s+(?:in|for|of)\s+(?P<chat>.+))?$',
            r'(?iu)^(?:comment|leave\s+comment|add\s+comment)\s+(?:on|under|to|for)\s+(?:post|message|msg)?\s*#?(?P<message_id>\d+)?'
            r'(?:\s+(?:in|for|of)\s+(?P<chat>.+?))?\s+(?P<text>".*?"|\'.*?\')$',
            r'(?iu)^(?:\u043f\u0440\u043e\u043a\u043e\u043c\u043c\u0435\u043d\u0442\w*|\u043e\u0441\u0442\u0430\u0432\u044c\s+\u043a\u043e\u043c\u043c\u0435\u043d\u0442\w*|\u0434\u043e\u0431\u0430\u0432\u044c\s+\u043a\u043e\u043c\u043c\u0435\u043d\u0442\w*)\s+(?P<text>".*?"|\'.*?\')'
            r'(?:\s+(?:\u043a|\u043f\u043e\u0434|\u0434\u043b\u044f)\s+(?:\u043f\u043e\u0441\u0442\w*|\u0441\u043e\u043e\u0431\u0449\u0435\u043d\w*)?\s*#?(?P<message_id>\d+))?'
            r'(?:\s+(?:\u0432|\u0438\u0437)\s+(?P<chat>.+))?$',
            r'(?iu)^(?:\u043f\u0440\u043e\u043a\u043e\u043c\u043c\u0435\u043d\u0442\w*|\u043e\u0441\u0442\u0430\u0432\u044c\s+\u043a\u043e\u043c\u043c\u0435\u043d\u0442\w*|\u0434\u043e\u0431\u0430\u0432\u044c\s+\u043a\u043e\u043c\u043c\u0435\u043d\u0442\w*)\s+(?:\u043a|\u043f\u043e\u0434|\u0434\u043b\u044f)\s+(?:\u043f\u043e\u0441\u0442\w*|\u0441\u043e\u043e\u0431\u0449\u0435\u043d\w*)?\s*#?(?P<message_id>\d+)?'
            r'(?:\s+(?:\u0432|\u0438\u0437)\s+(?P<chat>.+?))?\s+(?P<text>".*?"|\'.*?\')$',
        )
        for pattern in patterns:
            match = re.match(pattern, normalized)
            if match is None:
                continue
            text = self._strip_wrapping_quotes((match.groupdict().get("text") or "").strip())
            if not text:
                continue
            message_id_raw = match.groupdict().get("message_id")
            message_id = int(message_id_raw) if message_id_raw else context.reply_to_message_id
            if message_id is None:
                continue
            chat_ref = self._resolve_chat_target_reference_or_current(match.groupdict().get("chat"), context)
            target = await self._build_chat_target(chat_ref, context)
            return ActionRequest(
                action_name="comment_channel_post",
                raw_prompt=normalized,
                context=context,
                target=target,
                arguments={"message_id": message_id, "text": text},
                summary=f"Leave a comment under post #{message_id} in {target.label}",
            )
        return None

    async def _parse_mark_read(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not any(marker in lowered for marker in (
            "mark read", "прочитай чат", "прочитай этот чат", "отметь прочитанным", "read this chat",
            "пометь прочитанным", "mark as read", "прочитать чат",
            "очисти счётчик", "убери уведомления", "прочитано",
        )):
            return None
        target = await self._build_chat_target(None, context)
        return ActionRequest("mark_read", normalized, context, target=target, summary=f"Mark {target.label} as read")

    async def _parse_archive(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if any(marker in lowered for marker in ("archive", "архив", "заархивируй", "в архив", "убери в архив", "разархивируй", "из архива")):
            action_name = "unarchive_chat" if any(marker in lowered for marker in ("unarchive", "разархив", "из архива", "достань из архива", "разархивируй")) else "archive_chat"
            target_ref = self._extract_target_after_preposition(normalized, ("chat", "to", "в", "чат"))
            target = await self._build_chat_target(target_ref, context)
            verb = "Unarchive" if action_name == "unarchive_chat" else "Archive"
            return ActionRequest(action_name, normalized, context, target=target, summary=f"{verb} {target.label}")
        return None

    async def _parse_blocking(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if any(marker in lowered for marker in ("block", "заблок", "unblock", "разблок", "заблокируй", "разблокируй", "добавь в чс", "удали из чс")):
            action_name = "unblock_user" if any(marker in lowered for marker in ("unblock", "разблок", "разблокируй", "удали из чс")) else "block_user"
            target_ref = self._extract_blocking_target_reference(
                normalized,
                unblock=action_name == "unblock_user",
            )
            if target_ref is None:
                target_ref = self._normalize_member_reference(
                    self._extract_target_after_preposition(
                        normalized,
                        ("user", "пользователя", "@"),
                    )
                )
            target = await self._build_user_target(target_ref, context)
            verb = "Unblock" if action_name == "unblock_user" else "Block"
            return ActionRequest(action_name, normalized, context, target=target, summary=f"{verb} {target.label}")
        return None

    async def _parse_join_leave(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if any(marker in lowered for marker in ("join", "вступи", "зайди", "подпишись", "войти", "subscribe", "добавься", "вступить")):
            target_ref = self._extract_target_after_preposition(normalized, ("chat", "channel", "в", "to", "на", "к"))
            if target_ref is None:
                match = re.match(r"(?iu)^(?:join|вступи|зайди|подпишись|войти|subscribe|добавься|вступить)\s+(?:в|на|to)?\s*(.+)$", normalized)
                target_ref = self._strip_wrapping_quotes(match.group(1).strip()) if match else None
            if target_ref is None:
                return None
            target = await self._build_chat_target(target_ref, context)
            return ActionRequest("join_chat", normalized, context, target=target, summary=f"Join {target.label}")
        if any(marker in lowered for marker in ("leave", "покинь", "выйди", "отпишись", "выйти из", "покинуть", "unsubscribe", "уйди из")):
            target_ref = self._extract_target_after_preposition(normalized, ("chat", "channel", "из", "from", "с"))
            if target_ref is None:
                match = re.match(r"(?iu)^(?:leave|покинь|выйди|отпишись|выйти из|покинуть|unsubscribe|уйди из)\s+(?:из|from)?\s*(.+)$", normalized)
                target_ref = self._strip_wrapping_quotes(match.group(1).strip()) if match else None
            target = await self._build_chat_target(target_ref, context)
            return ActionRequest("leave_chat", normalized, context, target=target, summary=f"Leave {target.label}")
        return None

    async def _parse_ban(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not any(marker in lowered for marker in ("ban", "kick", "забань", "кикни", "unban", "разбань", "исключи", "выгони", "удали участника", "remove user", "kick out")):
            return None
        action_name = "unban_user" if any(marker in lowered for marker in ("unban", "разбань", "разбан", "вернуть доступ")) else "ban_user"
        explicit_ref = self._normalize_member_reference(self._extract_target_after_preposition(normalized, ("user", "пользователя", "@")))
        target = await self._build_user_target(explicit_ref, context)
        chat_target = await self._build_chat_target(None, context)
        verb = "Unban" if action_name == "unban_user" else "Ban"
        return ActionRequest(
            action_name,
            normalized,
            context,
            target=target,
            secondary_target=chat_target,
            summary=f"{verb} {target.label} in {chat_target.label}",
        )

    async def _parse_chat_permissions_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        english_match = re.match(
            r'(?iu)^(?:set|change|update)\s+(?:default\s+)?(?:chat|group|channel)\s+permissions\s+(?:to\s+)?(?P<preset>.+?)'
            r'(?:\s+(?:in|for)\s+(?P<target>.+))?$',
            normalized,
        )
        if english_match is None:
            english_match = re.match(
                r'(?iu)^(?:set|change|update)\s+permissions\s+(?:for|in)\s+(?P<target>.+?)\s+(?:to\s+)?(?P<preset>.+)$',
                normalized,
            )
        russian_match = re.match(
            r'(?iu)^(?:\u043f\u043e\u0441\u0442\u0430\u0432\u044c|\u0441\u043c\u0435\u043d\u0438|\u0438\u0437\u043c\u0435\u043d\u0438|\u043e\u0431\u043d\u043e\u0432\u0438)\s+'
            r'(?:(?:\u043f\u0440\u0430\u0432\u0430|\u0440\u0430\u0437\u0440\u0435\u0448\u0435\u043d\u0438\u044f)\s+(?:\u0447\u0430\u0442\u0430|\u043a\u0430\u043d\u0430\u043b\u0430|\u0433\u0440\u0443\u043f\u043f\u044b)|\u043f\u0440\u0430\u0432\u0430 \u043f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e)\s+'
            r'(?:\u043d\u0430\s+)?(?P<preset>.+?)(?:\s+(?:\u0432|\u0434\u043b\u044f)\s+(?P<target>.+))?$',
            normalized,
        )
        match = english_match or russian_match
        if match is None:
            return None
        preset = self._permission_preset_from_text(match.group("preset"))
        if preset is None:
            return None
        preset_label, permissions = preset
        target_ref = self._resolve_chat_target_reference_or_current(match.groupdict().get("target"), context)
        target = await self._build_chat_target(target_ref, context)
        return ActionRequest(
            action_name="set_chat_permissions",
            raw_prompt=normalized,
            context=context,
            target=target,
            arguments={"permissions": permissions, "preset_label": preset_label},
            summary=f"Set default permissions for {target.label} to {preset_label}",
        )

    async def _parse_member_restrictions_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        english_unrestrict = re.match(
            r'(?iu)^(?:unrestrict|unmute|restore permissions for)\s+(?P<user>.+?)(?:\s+(?:in|for)\s+(?P<chat>.+))?$',
            normalized,
        )
        russian_unrestrict = re.match(
            r'(?iu)^(?:\u0440\u0430\u0437\u043c\u0443\u0442\u044c|\u0441\u043d\u0438\u043c\u0438 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f \u0441|\u0443\u0431\u0435\u0440\u0438 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f \u0441)\s+(?P<user>.+?)(?:\s+(?:\u0432|\u0434\u043b\u044f)\s+(?P<chat>.+))?$',
            normalized,
        )
        match = english_unrestrict or russian_unrestrict
        if match is not None:
            user_ref = self._normalize_member_reference(match.group("user"))
            target = await self._build_user_target(user_ref, context)
            chat_ref = self._resolve_chat_target_reference_or_current(match.groupdict().get("chat"), context)
            chat_target = await self._build_chat_target(chat_ref, context)
            return ActionRequest(
                action_name="unrestrict_chat_member",
                raw_prompt=normalized,
                context=context,
                target=target,
                secondary_target=chat_target,
                summary=f"Lift restrictions for {target.label} in {chat_target.label}",
            )

        english_restrict = re.match(
            r'(?iu)^(?:restrict|mute)\s+(?P<user>.+?)(?:\s+(?:to|as)\s+(?P<preset>.+?))?(?:\s+(?:in|for)\s+(?P<chat>.+))?$',
            normalized,
        )
        russian_restrict = re.match(
            r'(?iu)^(?:\u043e\u0433\u0440\u0430\u043d\u0438\u0447\u044c|\u0437\u0430\u043c\u0443\u0442\u044c|\u043c\u0443\u0442)\s+(?P<user>.+?)(?:\s+(?:\u043d\u0430|\u0432 \u0440\u0435\u0436\u0438\u043c)\s+(?P<preset>.+?))?(?:\s+(?:\u0432|\u0434\u043b\u044f)\s+(?P<chat>.+))?$',
            normalized,
        )
        match = english_restrict or russian_restrict
        if match is None:
            return None
        preset = self._permission_preset_from_text(match.groupdict().get("preset"), default_key="read_only")
        if preset is None:
            return None
        preset_label, permissions = preset
        user_ref = self._normalize_member_reference(match.group("user"))
        target = await self._build_user_target(user_ref, context)
        chat_ref = self._resolve_chat_target_reference_or_current(match.groupdict().get("chat"), context)
        chat_target = await self._build_chat_target(chat_ref, context)
        return ActionRequest(
            action_name="restrict_chat_member",
            raw_prompt=normalized,
            context=context,
            target=target,
            secondary_target=chat_target,
            arguments={"permissions": permissions, "preset_label": preset_label},
            summary=f"Restrict {target.label} in {chat_target.label} to {preset_label}",
        )

    async def _parse_admin_management_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        english_demote = re.match(
            r'(?iu)^(?:demote)\s+(?P<user>.+?)(?:\s+(?:in|for)\s+(?P<chat>.+))?$',
            normalized,
        )
        if english_demote is None:
            english_demote = re.match(
                r'(?iu)^(?:remove\s+admin(?:istrator)?(?:\s+rights)?\s+from)\s+(?P<user>.+?)(?:\s+(?:in|for)\s+(?P<chat>.+))?$',
                normalized,
            )
        russian_demote = re.match(
            r'(?iu)^(?:\u0441\u043d\u0438\u043c\u0438 \u0430\u0434\u043c\u0438\u043d\u043a\u0443 \u0441|\u0443\u0431\u0435\u0440\u0438 \u0430\u0434\u043c\u0438\u043d\u043a\u0443 \u0443|\u0440\u0430\u0437\u0436\u0430\u043b\u0443\u0439)\s+(?P<user>.+?)(?:\s+(?:\u0432|\u0434\u043b\u044f)\s+(?P<chat>.+))?$',
            normalized,
        )
        match = english_demote or russian_demote
        if match is not None:
            user_ref = self._normalize_member_reference(match.group("user"))
            target = await self._build_user_target(user_ref, context)
            chat_ref = self._resolve_chat_target_reference_or_current(match.groupdict().get("chat"), context)
            chat_target = await self._build_chat_target(chat_ref, context)
            return ActionRequest(
                action_name="demote_chat_member",
                raw_prompt=normalized,
                context=context,
                target=target,
                secondary_target=chat_target,
                summary=f"Remove admin rights from {target.label} in {chat_target.label}",
            )

        english_make_admin = re.match(
            r'(?iu)^(?:make)\s+(?P<user>.+?)\s+(?:an?\s+)?(?P<preset>full admin|admin|administrator|moderator)(?:\s+(?:in|for)\s+(?P<chat>.+))?$',
            normalized,
        )
        english_promote = re.match(
            r'(?iu)^(?:promote)\s+(?P<user>.+?)(?:\s+(?:to|as)\s+(?P<preset>.+?))?(?:\s+(?:in|for)\s+(?P<chat>.+))?$',
            normalized,
        )
        russian_make_admin = re.match(
            r'(?iu)^(?:\u0441\u0434\u0435\u043b\u0430\u0439|\u043d\u0430\u0437\u043d\u0430\u0447\u044c)\s+(?P<user>.+?)\s+(?P<preset>\u0430\u0434\u043c\u0438\u043d\u043e\u043c|\u043f\u043e\u043b\u043d\u044b\u043c \u0430\u0434\u043c\u0438\u043d\u043e\u043c|\u043c\u043e\u0434\u0435\u0440\u0430\u0442\u043e\u0440\u043e\u043c)(?:\s+(?:\u0432|\u0434\u043b\u044f)\s+(?P<chat>.+))?$',
            normalized,
        )
        russian_promote = re.match(
            r'(?iu)^(?:\u043f\u043e\u0432\u044b\u0441\u044c|\u043d\u0430\u0437\u043d\u0430\u0447\u044c)\s+(?P<user>.+?)(?:\s+(?:\u0434\u043e|\u043a\u0430\u043a)\s+(?P<preset>.+?))?(?:\s+(?:\u0432|\u0434\u043b\u044f)\s+(?P<chat>.+))?$',
            normalized,
        )
        match = english_make_admin or english_promote or russian_make_admin or russian_promote
        if match is not None:
            preset = self._admin_privilege_preset_from_text(match.groupdict().get("preset"), default_key="basic")
            if preset is None:
                return None
            preset_label, privileges = preset
            user_ref = self._normalize_member_reference(match.group("user"))
            target = await self._build_user_target(user_ref, context)
            chat_ref = self._resolve_chat_target_reference_or_current(match.groupdict().get("chat"), context)
            chat_target = await self._build_chat_target(chat_ref, context)
            return ActionRequest(
                action_name="promote_chat_member",
                raw_prompt=normalized,
                context=context,
                target=target,
                secondary_target=chat_target,
                arguments={"privileges": privileges, "preset_label": preset_label},
                summary=f"Promote {target.label} in {chat_target.label} as {preset_label}",
            )

        english_clear_title = re.match(
            r'(?iu)^(?:remove|clear)\s+(?:administrator|admin)\s+title(?:\s+for\s+(?P<user>.+?))?(?:\s+(?:in|for)\s+(?P<chat>.+))?$',
            normalized,
        )
        russian_clear_title = re.match(
            r'(?iu)^(?:\u0443\u0431\u0435\u0440\u0438|\u0441\u043d\u0438\u043c\u0438|\u043e\u0447\u0438\u0441\u0442\u0438)\s+(?:\u0442\u0438\u0442\u0443\u043b \u0430\u0434\u043c\u0438\u043d\u0430|\u0442\u0438\u0442\u0443\u043b \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u0430)(?:\s+(?:\u0443|\u0434\u043b\u044f)\s+(?P<user>.+?))?(?:\s+\u0432\s+(?P<chat>.+))?$',
            normalized,
        )
        match = english_clear_title or russian_clear_title
        if match is not None:
            user_ref = self._normalize_member_reference(match.groupdict().get("user"))
            target = await self._build_user_target(user_ref, context)
            chat_ref = self._resolve_chat_target_reference_or_current(match.groupdict().get("chat"), context)
            chat_target = await self._build_chat_target(chat_ref, context)
            return ActionRequest(
                action_name="set_administrator_title",
                raw_prompt=normalized,
                context=context,
                target=target,
                secondary_target=chat_target,
                arguments={"title": ""},
                summary=f"Clear administrator title for {target.label} in {chat_target.label}",
            )

        english_set_title = re.match(
            r'(?iu)^(?:set|change|update)\s+(?:administrator|admin)\s+title\s+(?:to\s+)?(?P<title>".*?"|\'.*?\'|\S(?:.*?\S)?)(?:\s+for\s+(?P<user>.+?))?(?:\s+in\s+(?P<chat>.+))?$',
            normalized,
        )
        russian_set_title = re.match(
            r'(?iu)^(?:\u043f\u043e\u0441\u0442\u0430\u0432\u044c|\u0437\u0430\u0434\u0430\u0439|\u0438\u0437\u043c\u0435\u043d\u0438)\s+(?:\u0442\u0438\u0442\u0443\u043b \u0430\u0434\u043c\u0438\u043d\u0430|\u0442\u0438\u0442\u0443\u043b \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u0430)\s+(?:\u043d\u0430\s+)?(?P<title>".*?"|\'.*?\'|\S(?:.*?\S)?)(?:\s+(?:\u0434\u043b\u044f|\u0443)\s+(?P<user>.+?))?(?:\s+\u0432\s+(?P<chat>.+))?$',
            normalized,
        )
        match = english_set_title or russian_set_title
        if match is None:
            return None
        title = self._strip_wrapping_quotes((match.group("title") or "").strip())
        if not title:
            return None
        user_ref = self._normalize_member_reference(match.groupdict().get("user"))
        target = await self._build_user_target(user_ref, context)
        chat_ref = self._resolve_chat_target_reference_or_current(match.groupdict().get("chat"), context)
        chat_target = await self._build_chat_target(chat_ref, context)
        return ActionRequest(
            action_name="set_administrator_title",
            raw_prompt=normalized,
            context=context,
            target=target,
            secondary_target=chat_target,
            arguments={"title": title},
            summary=f'Set administrator title for {target.label} in {chat_target.label} to "{title}"',
        )

    async def _parse_invite_link_management_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        export_match = re.match(
            r'(?iu)^(?:export|get|generate)\s+(?:primary\s+)?(?:invite\s+link|chat\s+invite\s+link)(?:\s+(?:for|in)\s+(?P<target>.+))?$',
            normalized,
        )
        if export_match is None:
            export_match = re.match(
                r'(?iu)^(?:\u044d\u043a\u0441\u043f\u043e\u0440\u0442\u0438\u0440\u0443\u0439|\u043f\u043e\u043b\u0443\u0447\u0438|\u0441\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u0443\u0439)\s+(?:\u043e\u0441\u043d\u043e\u0432\u043d\u0443\u044e\s+)?(?:\u0441\u0441\u044b\u043b\u043a\u0443 \u043f\u0440\u0438\u0433\u043b\u0430\u0448\u0435\u043d\u0438\u044f|\u0438\u043d\u0432\u0430\u0439\u0442[- ]?\u0441\u0441\u044b\u043b\u043a\u0443)(?:\s+(?:\u0434\u043b\u044f|\u0432)\s+(?P<target>.+))?$',
                normalized,
            )
        if export_match is not None:
            target_ref = self._resolve_chat_target_reference_or_current(export_match.groupdict().get("target"), context)
            target = await self._build_chat_target(target_ref, context)
            return ActionRequest(
                action_name="export_chat_invite_link",
                raw_prompt=normalized,
                context=context,
                target=target,
                summary=f"Export primary invite link for {target.label}",
            )

        create_match = re.match(
            r'(?iu)^(?:create|make|generate)\s+(?:new|additional\s+)?(?:invite\s+link|chat\s+invite\s+link)(?P<body>.*?)(?:\s+(?:for|in)\s+(?P<target>.+))?$',
            normalized,
        )
        if create_match is None:
            create_match = re.match(
                r'(?iu)^(?:\u0441\u043e\u0437\u0434\u0430\u0439|\u0441\u0434\u0435\u043b\u0430\u0439|\u0441\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u0443\u0439)\s+(?:\u043d\u043e\u0432\u0443\u044e|(?:\u0434\u043e\u043f(?:\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u0443\u044e)?)\s+)?(?:\u0441\u0441\u044b\u043b\u043a\u0443 \u043f\u0440\u0438\u0433\u043b\u0430\u0448\u0435\u043d\u0438\u044f|\u0438\u043d\u0432\u0430\u0439\u0442[- ]?\u0441\u0441\u044b\u043b\u043a\u0443)(?P<body>.*?)(?:\s+(?:\u0434\u043b\u044f|\u0432)\s+(?P<target>.+))?$',
                normalized,
            )
        if create_match is not None:
            body = create_match.group("body") or ""
            target_ref = self._resolve_chat_target_reference_or_current(create_match.groupdict().get("target"), context)
            target = await self._build_chat_target(target_ref, context)
            return ActionRequest(
                action_name="create_chat_invite_link",
                raw_prompt=normalized,
                context=context,
                target=target,
                arguments={
                    "name": self._extract_invite_link_name(body),
                    "expire_date": self._extract_invite_link_expire_date(body),
                    "member_limit": self._extract_invite_link_limit(body),
                    "creates_join_request": self._extract_invite_link_join_request_flag(body),
                },
                summary=f"Create invite link for {target.label}",
            )

        edit_match = re.match(
            r'(?iu)^(?:edit|update|change)\s+(?:invite\s+link|chat\s+invite\s+link)\s+(?P<link>\S+|".*?"|\'.*?\')(?P<body>.*?)(?:\s+(?:for|in)\s+(?P<target>.+))?$',
            normalized,
        )
        if edit_match is None:
            edit_match = re.match(
                r'(?iu)^(?:\u0438\u0437\u043c\u0435\u043d\u0438|\u043e\u0431\u043d\u043e\u0432\u0438|\u043f\u043e\u043c\u0435\u043d\u044f\u0439)\s+(?:\u0441\u0441\u044b\u043b\u043a\u0443 \u043f\u0440\u0438\u0433\u043b\u0430\u0448\u0435\u043d\u0438\u044f|\u0438\u043d\u0432\u0430\u0439\u0442[- ]?\u0441\u0441\u044b\u043b\u043a\u0443)\s+(?P<link>\S+|".*?"|\'.*?\')(?P<body>.*?)(?:\s+(?:\u0434\u043b\u044f|\u0432)\s+(?P<target>.+))?$',
                normalized,
            )
        if edit_match is not None:
            invite_link = self._strip_wrapping_quotes(edit_match.group("link").strip())
            body = edit_match.group("body") or ""
            if not invite_link:
                return None
            options = {
                "name": self._extract_invite_link_name(body),
                "expire_date": self._extract_invite_link_expire_date(body),
                "member_limit": self._extract_invite_link_limit(body),
                "creates_join_request": self._extract_invite_link_join_request_flag(body),
            }
            if all(value is None for value in options.values()):
                return None
            target_ref = self._resolve_chat_target_reference_or_current(edit_match.groupdict().get("target"), context)
            target = await self._build_chat_target(target_ref, context)
            options["invite_link"] = invite_link
            return ActionRequest(
                action_name="edit_chat_invite_link",
                raw_prompt=normalized,
                context=context,
                target=target,
                arguments=options,
                summary=f"Edit invite link for {target.label}",
            )

        revoke_match = re.match(
            r'(?iu)^(?:revoke|disable|invalidate)\s+(?:invite\s+link|chat\s+invite\s+link)\s+(?P<link>\S+|".*?"|\'.*?\')(?:\s+(?:for|in)\s+(?P<target>.+))?$',
            normalized,
        )
        if revoke_match is None:
            revoke_match = re.match(
                r'(?iu)^(?:\u043e\u0442\u0437\u043e\u0432\u0438|\u0430\u043d\u043d\u0443\u043b\u0438\u0440\u0443\u0439|\u043e\u0442\u043a\u043b\u044e\u0447\u0438)\s+(?:\u0441\u0441\u044b\u043b\u043a\u0443 \u043f\u0440\u0438\u0433\u043b\u0430\u0448\u0435\u043d\u0438\u044f|\u0438\u043d\u0432\u0430\u0439\u0442[- ]?\u0441\u0441\u044b\u043b\u043a\u0443)\s+(?P<link>\S+|".*?"|\'.*?\')(?:\s+(?:\u0434\u043b\u044f|\u0432)\s+(?P<target>.+))?$',
                normalized,
            )
        if revoke_match is None:
            return None
        invite_link = self._strip_wrapping_quotes(revoke_match.group("link").strip())
        if not invite_link:
            return None
        target_ref = self._resolve_chat_target_reference_or_current(revoke_match.groupdict().get("target"), context)
        target = await self._build_chat_target(target_ref, context)
        return ActionRequest(
            action_name="revoke_chat_invite_link",
            raw_prompt=normalized,
            context=context,
            target=target,
            arguments={"invite_link": invite_link},
            summary=f"Revoke invite link for {target.label}",
        )

    async def _parse_join_request_management_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        pattern_specs = (
            (
                "approve_chat_join_request",
                (
                    r'(?iu)^(?:approve|accept)\s+(?:the\s+)?(?:join\s+request|request\s+to\s+join)(?:\s+(?:for|from)\s+(?P<user>.+?))?(?:\s+(?:in|for)\s+(?P<chat>.+))?$',
                    r'(?iu)^(?:approve|accept)\s+(?P<user>.+?)\s+(?:join\s+request|request\s+to\s+join)(?:\s+(?:in|for)\s+(?P<chat>.+))?$',
                    '(?iu)^(?:\\u043e\\u0434\\u043e\\u0431\\u0440\\u0438|\\u043f\\u0440\\u0438\\u043c\\u0438)\\s+(?:\\u0437\\u0430\\u044f\\u0432\\u043a\\w*|\\u0437\\u0430\\u043f\\u0440\\u043e\\u0441\\w*)(?:\\s+\\u043d\\u0430\\s+\\u0432\\u0441\\u0442\\u0443\\u043f\\u043b\\u0435\\u043d\\w*)?(?:\\s+(?:\\u0434\\u043b\\u044f|\\u043e\\u0442)\\s+(?P<user>.+?))?(?:\\s+\\u0432\\s+(?P<chat>.+))?$',
                    '(?iu)^(?:\\u043e\\u0434\\u043e\\u0431\\u0440\\u0438|\\u043f\\u0440\\u0438\\u043c\\u0438)\\s+(?P<user>.+?)\\s+(?:\\u0437\\u0430\\u044f\\u0432\\u043a\\w*|\\u0437\\u0430\\u043f\\u0440\\u043e\\u0441\\w*)(?:\\s+\\u043d\\u0430\\s+\\u0432\\u0441\\u0442\\u0443\\u043f\\u043b\\u0435\\u043d\\w*)?(?:\\s+\\u0432\\s+(?P<chat>.+))?$',
                ),
            ),
            (
                "decline_chat_join_request",
                (
                    r'(?iu)^(?:decline|reject|deny)\s+(?:the\s+)?(?:join\s+request|request\s+to\s+join)(?:\s+(?:for|from)\s+(?P<user>.+?))?(?:\s+(?:in|for)\s+(?P<chat>.+))?$',
                    r'(?iu)^(?:decline|reject|deny)\s+(?P<user>.+?)\s+(?:join\s+request|request\s+to\s+join)(?:\s+(?:in|for)\s+(?P<chat>.+))?$',
                    '(?iu)^(?:\\u043e\\u0442\\u043a\\u043b\\u043e\\u043d\\u0438|\\u043e\\u0442\\u0432\\u0435\\u0440\\u0433\\u043d\\u0438)\\s+(?:\\u0437\\u0430\\u044f\\u0432\\u043a\\w*|\\u0437\\u0430\\u043f\\u0440\\u043e\\u0441\\w*)(?:\\s+\\u043d\\u0430\\s+\\u0432\\u0441\\u0442\\u0443\\u043f\\u043b\\u0435\\u043d\\w*)?(?:\\s+(?:\\u0434\\u043b\\u044f|\\u043e\\u0442)\\s+(?P<user>.+?))?(?:\\s+\\u0432\\s+(?P<chat>.+))?$',
                    '(?iu)^(?:\\u043e\\u0442\\u043a\\u043b\\u043e\\u043d\\u0438|\\u043e\\u0442\\u0432\\u0435\\u0440\\u0433\\u043d\\u0438)\\s+(?P<user>.+?)\\s+(?:\\u0437\\u0430\\u044f\\u0432\\u043a\\w*|\\u0437\\u0430\\u043f\\u0440\\u043e\\u0441\\w*)(?:\\s+\\u043d\\u0430\\s+\\u0432\\u0441\\u0442\\u0443\\u043f\\u043b\\u0435\\u043d\\w*)?(?:\\s+\\u0432\\s+(?P<chat>.+))?$',
                ),
            ),
        )
        for action_name, patterns in pattern_specs:
            for pattern in patterns:
                match = re.match(pattern, normalized)
                if match is None:
                    continue
                user_ref = self._normalize_member_reference(match.groupdict().get("user"))
                if user_ref is None and context.reply_to_user_id is None:
                    session_target = self.get_selected_target(context.request_chat_id)
                    if session_target is None or session_target.kind != "user":
                        return None
                target = await self._build_user_target(user_ref, context)
                chat_ref = self._resolve_chat_target_reference_or_current(match.groupdict().get("chat"), context)
                chat_target = await self._build_chat_target(chat_ref, context)
                verb = "Approve" if action_name == "approve_chat_join_request" else "Decline"
                return ActionRequest(
                    action_name=action_name,
                    raw_prompt=normalized,
                    context=context,
                    target=target,
                    secondary_target=chat_target,
                    summary=f"{verb} join request for {target.label} in {chat_target.label}",
                )
        return None

    async def _parse_chat_photo_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        current_chat_aliases = {
            "this chat",
            "current chat",
            "\u044d\u0442\u043e\u0442 \u0447\u0430\u0442",
            "\u0432 \u044d\u0442\u043e\u0442 \u0447\u0430\u0442",
            "\u0432 \u044d\u0442\u043e\u043c \u0447\u0430\u0442\u0435",
            "\u044d\u0442\u043e\u043c \u0447\u0430\u0442\u0435",
            "\u0442\u0435\u043a\u0443\u0449\u0438\u0439 \u0447\u0430\u0442",
            "\u0432 \u0442\u0435\u043a\u0443\u0449\u0435\u043c \u0447\u0430\u0442\u0435",
            "\u0442\u0435\u043a\u0443\u0449\u0435\u043c \u0447\u0430\u0442\u0435",
        }

        delete_markers = (
            "delete chat photo",
            "remove chat photo",
            "clear chat photo",
            "delete group photo",
            "remove group photo",
            "delete channel photo",
            "remove channel photo",
            "delete chat avatar",
            "remove chat avatar",
            "\u0443\u0434\u0430\u043b\u0438 \u0444\u043e\u0442\u043e \u0447\u0430\u0442\u0430",
            "\u0443\u0431\u0435\u0440\u0438 \u0444\u043e\u0442\u043e \u0447\u0430\u0442\u0430",
            "\u0443\u0434\u0430\u043b\u0438 \u0430\u0432\u0430\u0442\u0430\u0440 \u0447\u0430\u0442\u0430",
            "\u0443\u0431\u0435\u0440\u0438 \u0430\u0432\u0430\u0442\u0430\u0440 \u0447\u0430\u0442\u0430",
            "\u0443\u0434\u0430\u043b\u0438 \u0444\u043e\u0442\u043e \u043a\u0430\u043d\u0430\u043b\u0430",
            "\u0443\u0434\u0430\u043b\u0438 \u0444\u043e\u0442\u043e \u0433\u0440\u0443\u043f\u043f\u044b",
        )
        if any(marker in lowered for marker in delete_markers):
            raw_target_ref = self._extract_target_after_preposition(
                normalized,
                (
                    "for chat",
                    "for channel",
                    "for group",
                    "for",
                    "in chat",
                    "in channel",
                    "in group",
                    "in",
                    "\u0434\u043b\u044f \u0447\u0430\u0442\u0430",
                    "\u0434\u043b\u044f \u043a\u0430\u043d\u0430\u043b\u0430",
                    "\u0434\u043b\u044f \u0433\u0440\u0443\u043f\u043f\u044b",
                    "\u0434\u043b\u044f",
                    "\u0432 \u0447\u0430\u0442\u0435",
                    "\u0432 \u043a\u0430\u043d\u0430\u043b\u0435",
                    "\u0432 \u0433\u0440\u0443\u043f\u043f\u0435",
                    "\u0432",
                ),
            )
            normalized_target_ref = self._normalize_target_reference(raw_target_ref)
            if normalized_target_ref is None and raw_target_ref is not None:
                raw_target_lower = " ".join(raw_target_ref.casefold().split())
                target_ref = context.request_chat_id if raw_target_lower in current_chat_aliases else None
            else:
                target_ref = normalized_target_ref
            target = await self._build_chat_target(target_ref, context)
            return ActionRequest(
                action_name="delete_chat_photo",
                raw_prompt=normalized,
                context=context,
                target=target,
                summary=f"Delete chat photo for {target.label}",
            )

        english_match = re.match(
            r'(?iu)^(?:set|change|update|replace)\s+(?:chat|group|channel)\s+'
            r'(?P<kind>photo|avatar|video)\s+(?:to\s+)?(?P<media>".*?"|\'.*?\'|\S+)'
            r'(?:\s+(?:for|in|to)\s+(?P<target>.+))?$',
            normalized,
        )
        if english_match is None:
            english_match = re.match(
                r'(?iu)^(?:set|change|update|replace)\s+'
                r'(?P<kind>chat\s+photo|chat\s+avatar|chat\s+video|group\s+photo|channel\s+photo)\s+'
                r'(?:to\s+)?(?P<media>".*?"|\'.*?\'|\S+)'
                r'(?:\s+(?:for|in|to)\s+(?P<target>.+))?$',
                normalized,
            )
        russian_match = re.match(
            r'(?iu)^(?:\u043f\u043e\u0441\u0442\u0430\u0432\u044c|\u0441\u043c\u0435\u043d\u0438|\u0438\u0437\u043c\u0435\u043d\u0438|\u043e\u0431\u043d\u043e\u0432\u0438)\s+'
            r'(?P<kind>\u0444\u043e\u0442\u043e\s+\u0447\u0430\u0442\u0430|\u0430\u0432\u0430\u0442\u0430\u0440\s+\u0447\u0430\u0442\u0430|\u0444\u043e\u0442\u043e\s+\u043a\u0430\u043d\u0430\u043b\u0430|\u0444\u043e\u0442\u043e\s+\u0433\u0440\u0443\u043f\u043f\u044b|\u0432\u0438\u0434\u0435\u043e\s+\u0430\u0432\u0430\u0442\u0430\u0440\s+\u0447\u0430\u0442\u0430|\u0432\u0438\u0434\u0435\u043e\s+\u0447\u0430\u0442\u0430)\s+'
            r'(?:\u043d\u0430\s+)?(?P<media>".*?"|\'.*?\'|\S+)'
            r'(?:\s+(?:\u0432|\u0434\u043b\u044f)\s+(?P<target>.+))?$',
            normalized,
        )
        match = english_match or russian_match
        if match is None:
            return None

        raw_kind = " ".join((match.group("kind") or "").casefold().split())
        media = self._strip_wrapping_quotes(match.group("media").strip())
        if not media:
            return None
        raw_target_ref = match.groupdict().get("target")
        normalized_target_ref = self._normalize_target_reference(raw_target_ref)
        if normalized_target_ref is None and raw_target_ref is not None:
            raw_target_lower = " ".join(raw_target_ref.casefold().split())
            target_ref = context.request_chat_id if raw_target_lower in current_chat_aliases else None
        else:
            target_ref = normalized_target_ref
        target = await self._build_chat_target(target_ref, context)
        arguments = {"video": media} if "video" in raw_kind or "\u0432\u0438\u0434\u0435\u043e" in raw_kind else {"photo": media}
        media_label = "video avatar" if "video" in arguments else "chat photo"
        return ActionRequest(
            action_name="set_chat_photo",
            raw_prompt=normalized,
            context=context,
            target=target,
            arguments=arguments,
            summary=f"Set {media_label} for {target.label}",
        )

    async def _parse_title_description(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        title_match = re.match(r'(?iu)^(?:set|change|rename|измени|смени)\s+(?:chat\s+)?title\s+(?:to\s+)?(.+)$', normalized)
        if title_match is None:
            title_match = re.match(r'(?iu)^(?:измени|смени|поменяй)\s+название\s+(?:чата\s+)?(?:на\s+)?(.+)$', normalized)
        if title_match is not None:
            target = await self._build_chat_target(None, context)
            title = self._strip_wrapping_quotes(title_match.group(1).strip())
            return ActionRequest(
                action_name="set_chat_title",
                raw_prompt=normalized,
                context=context,
                target=target,
                arguments={"title": title},
                summary=f"Set title of {target.label} to {title}",
            )
        description_match = re.match(r'(?iu)^(?:set|change|edit|измени|смени)\s+(?:chat\s+)?description\s+(?:to\s+)?(.+)$', normalized)
        if description_match is None:
            description_match = re.match(r'(?iu)^(?:измени|смени|поменяй)\s+описание\s+(?:чата\s+)?(?:на\s+)?(.+)$', normalized)
        if description_match is not None:
            target = await self._build_chat_target(None, context)
            description = self._strip_wrapping_quotes(description_match.group(1).strip())
            return ActionRequest(
                action_name="set_chat_description",
                raw_prompt=normalized,
                context=context,
                target=target,
                arguments={"description": description},
                summary=f"Set description of {target.label}",
            )
        return None

    async def _parse_delete(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not any(marker in lowered for marker in ("delete", "remove", "удали", "сотри", "убери", "снеси", "стереть", "удалить сообщ")):
            return None

        # "Ã‘Æ’ÃÂ´ÃÂ°ÃÂ»ÃÂ¸ ÃÂ¿ÃÂ¾Ã‘ÂÃÂ»ÃÂµÃÂ´ÃÂ½ÃÂµÃÂµ Ã‘ÂÃÂ¾ÃÂ¾ÃÂ±Ã‘â€°ÃÂµÃÂ½ÃÂ¸ÃÂµ ÃÂºÃÂ¾Ã‘â€šÃÂ¾Ã‘â‚¬ÃÂ¾ÃÂµ ÃÂ¼ÃÂ½ÃÂµ ÃÂ¾Ã‘â€šÃÂ¿Ã‘â‚¬ÃÂ°ÃÂ²ÃÂ¸ÃÂ» X" / "Ã‘Æ’ÃÂ´ÃÂ°ÃÂ»ÃÂ¸ ÃÂ¿ÃÂ¾Ã‘ÂÃÂ»ÃÂµÃÂ´ÃÂ½ÃÂµÃÂµ ÃÂ¾Ã‘â€š X"
        _from_markers = ("которое мне отправил", "которое отправил", "написал", "прислал")
        has_from_phrase = any(m in lowered for m in _from_markers)
        has_from_prep = bool(re.search(r"(?iu)\bот\s+\S|\bfrom\s+\S", lowered))
        if (has_from_phrase or has_from_prep) and any(m in lowered for m in ("последн", "сообщени", "last", "message")):
            user_ref: str | None = None
            for marker in _from_markers:
                if marker in lowered:
                    idx = lowered.index(marker) + len(marker)
                    rest = normalized[idx:].strip()
                    user_ref = rest.split()[0] if rest else None
                    break
            if user_ref is None:
                m = re.search(r"(?iu)\b(?:от|from)\s+(\S+)", normalized)
                if m:
                    user_ref = m.group(1).strip()
            limit = self._extract_count(normalized, default=1)
            filter_user_id: int | None = None
            if user_ref:
                ref_clean = user_ref.lstrip("@").rstrip(".,;")
                if ref_clean.lstrip("-").isdigit():
                    filter_user_id = int(ref_clean)
                elif self._user_memory_store is not None:
                    filter_user_id = await self._user_memory_store.find_user_id_by_username(ref_clean)
            target = await self._build_chat_target(None, context)
            return ActionRequest(
                "delete_multiple_messages",
                normalized,
                context,
                target=target,
                arguments={"limit": limit, "mode": "recent", "filter_user_id": filter_user_id},
                summary=f"Delete last {limit} message(s) from {filter_user_id or user_ref} in {target.label}",
            )

        if any(marker in lowered for marker in ("last", "recent", "последн")):
            limit = self._extract_count(normalized, default=5)
            target = await self._build_chat_target(None, context)
            return ActionRequest(
                "delete_multiple_messages",
                normalized,
                context,
                target=target,
                arguments={"limit": limit, "mode": "recent"},
                summary=f"Delete the last {limit} accessible messages in {target.label}",
            )
        if context.reply_to_message_id is not None and any(marker in lowered for marker in ("this", "это", "этот")):
            target = ResolvedActionTarget(
                kind="message",
                lookup=context.request_chat_id,
                label=f"message #{context.reply_to_message_id}",
                chat_id=context.request_chat_id,
                message_id=context.reply_to_message_id,
                source="reply_context",
            )
            return ActionRequest("delete_message", normalized, context, target=target, summary=f"Delete message #{context.reply_to_message_id}")
        message_ids = [int(match.group(1)) for match in MESSAGE_ID_RE.finditer(normalized)]
        if len(message_ids) >= 2:
            target = await self._build_chat_target(None, context)
            return ActionRequest(
                "delete_multiple_messages",
                normalized,
                context,
                target=target,
                arguments={"message_ids": message_ids},
                summary=f"Delete {len(message_ids)} specific messages in {target.label}",
            )
        if len(message_ids) == 1:
            target = ResolvedActionTarget(
                kind="message",
                lookup=context.request_chat_id,
                label=f"message #{message_ids[0]}",
                chat_id=context.request_chat_id,
                message_id=message_ids[0],
            )
            return ActionRequest("delete_message", normalized, context, target=target, summary=f"Delete message #{message_ids[0]}")
        return None

    async def _parse_edit_caption(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        edit_markers = ("edit", "change", "update", "замени", "измени", "обнови", "редакт")
        if not any(marker in lowered for marker in edit_markers):
            return None
        if not any(marker in lowered for marker in ("caption", "подпис")):
            return None
        message_id = self._extract_message_id(normalized) or context.reply_to_message_id
        if message_id is None:
            return None
        caption = self._extract_quoted_text(normalized)
        if caption is None:
            match = re.search(r'(?iu)\b(?:to|as|на)\s+(.+)$', normalized)
            caption = match.group(1).strip() if match else None
        if not caption:
            return None
        target = ResolvedActionTarget(
            kind="message",
            lookup=context.request_chat_id,
            label=f"message #{message_id}",
            chat_id=context.request_chat_id,
            message_id=message_id,
            source="reply_context" if context.reply_to_message_id is not None else "explicit",
        )
        return ActionRequest(
            "edit_message_caption",
            normalized,
            context,
            target=target,
            arguments={"caption": self._strip_wrapping_quotes(caption)},
            summary=f"Edit caption of message #{message_id}",
        )

    async def _parse_edit_media(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        edit_markers = ("edit", "change", "replace", "update", "замени", "измени", "обнови", "редакт")
        media_markers = ("media", "attachment", "photo", "video", "animation", "gif", "document", "file", "audio", "медиа", "влож", "фото", "видео", "анимац", "гиф", "документ", "файл", "аудио")
        if not any(marker in lowered for marker in edit_markers):
            return None
        if not any(marker in lowered for marker in media_markers):
            return None
        message_id = self._extract_message_id(normalized) or context.reply_to_message_id
        if message_id is None:
            return None
        media_match = re.search(
            r'(?iu)(?:to|with|на)\s+'
            r'(photo|image|picture|video|animation|gif|document|file|doc|audio|track|music|song|'
            r'фот\w*|картин\w*|изображен\w*|видео\w*|ролик\w*|гиф\w*|анимац\w*|документ\w*|файл\w*|аудио\w*|трек\w*|музык\w*)\s+'
            r'(.+?)(?=(?:\s+(?:caption|with\s+caption|подпись|с\s+подписью)\s+|$))'
            r'(?:\s+(?:caption|with\s+caption|подпись|с\s+подписью)\s+(.+))?$',
            normalized,
        )
        if not media_match:
            return None
        media_kind = self._canonicalize_media_kind(media_match.group(1))
        if media_kind not in {"photo", "video", "animation", "document", "audio"}:
            return None
        media = self._strip_wrapping_quotes(media_match.group(2).strip())
        caption_raw = (media_match.group(3) or "").strip()
        if not media:
            return None
        arguments: dict[str, object] = {
            "media_kind": media_kind,
            "media": media,
        }
        if caption_raw:
            arguments["caption"] = self._strip_wrapping_quotes(caption_raw)
        target = ResolvedActionTarget(
            kind="message",
            lookup=context.request_chat_id,
            label=f"message #{message_id}",
            chat_id=context.request_chat_id,
            message_id=message_id,
            source="reply_context" if context.reply_to_message_id is not None else "explicit",
        )
        return ActionRequest(
            "edit_message_media",
            normalized,
            context,
            target=target,
            arguments=arguments,
            summary=f"Replace media in message #{message_id}",
        )

    async def _parse_edit_caption_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        edit_markers = (
            "edit",
            "change",
            "update",
            "\u0437\u0430\u043c\u0435\u043d\u0438",
            "\u0438\u0437\u043c\u0435\u043d\u0438",
            "\u043e\u0431\u043d\u043e\u0432\u0438",
            "\u0440\u0435\u0434\u0430\u043a\u0442",
        )
        if not any(marker in lowered for marker in edit_markers):
            return None
        if not any(marker in lowered for marker in ("caption", "\u043f\u043e\u0434\u043f\u0438\u0441")):
            return None
        message_id = self._extract_message_id(normalized) or context.reply_to_message_id
        if message_id is None:
            return None
        caption = self._extract_quoted_text(normalized)
        if caption is None:
            match = re.search(r'(?iu)\b(?:to|as|\u043d\u0430)\s+(.+)$', normalized)
            caption = match.group(1).strip() if match else None
        if not caption:
            return None
        target = ResolvedActionTarget(
            kind="message",
            lookup=context.request_chat_id,
            label=f"message #{message_id}",
            chat_id=context.request_chat_id,
            message_id=message_id,
            source="reply_context" if context.reply_to_message_id is not None else "explicit",
        )
        return ActionRequest(
            "edit_message_caption",
            normalized,
            context,
            target=target,
            arguments={"caption": self._strip_wrapping_quotes(caption)},
            summary=f"Edit caption of message #{message_id}",
        )

    async def _parse_edit_media_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        edit_markers = (
            "edit",
            "change",
            "replace",
            "update",
            "\u0437\u0430\u043c\u0435\u043d\u0438",
            "\u0438\u0437\u043c\u0435\u043d\u0438",
            "\u043e\u0431\u043d\u043e\u0432\u0438",
            "\u0440\u0435\u0434\u0430\u043a\u0442",
        )
        media_markers = (
            "media",
            "attachment",
            "photo",
            "video",
            "animation",
            "gif",
            "document",
            "file",
            "audio",
            "\u043c\u0435\u0434\u0438\u0430",
            "\u0432\u043b\u043e\u0436",
            "\u0444\u043e\u0442\u043e",
            "\u0432\u0438\u0434\u0435\u043e",
            "\u0430\u043d\u0438\u043c\u0430\u0446",
            "\u0433\u0438\u0444",
            "\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442",
            "\u0444\u0430\u0439\u043b",
            "\u0430\u0443\u0434\u0438\u043e",
        )
        if not any(marker in lowered for marker in edit_markers):
            return None
        if not any(marker in lowered for marker in media_markers):
            return None
        message_id = self._extract_message_id(normalized) or context.reply_to_message_id
        if message_id is None:
            return None
        media_match = re.search(
            r'(?iu)(?:to|with|\u043d\u0430)\s+'
            r'(photo|image|picture|video|animation|gif|document|file|doc|audio|track|music|song|'
            r'\u0444\u043e\u0442\w*|\u043a\u0430\u0440\u0442\u0438\u043d\w*|\u0438\u0437\u043e\u0431\u0440\u0430\u0436\u0435\u043d\w*|'
            r'\u0432\u0438\u0434\u0435\u043e\w*|\u0440\u043e\u043b\u0438\u043a\w*|\u0433\u0438\u0444\w*|\u0430\u043d\u0438\u043c\u0430\u0446\w*|'
            r'\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\w*|\u0444\u0430\u0439\u043b\w*|\u0430\u0443\u0434\u0438\u043e\w*|\u0442\u0440\u0435\u043a\w*|\u043c\u0443\u0437\u044b\u043a\w*)\s+'
            r'(.+?)(?=(?:\s+(?:caption|with\s+caption|\u043f\u043e\u0434\u043f\u0438\u0441\u044c|\u0441\s+\u043f\u043e\u0434\u043f\u0438\u0441\u044c\u044e)\s+|$))'
            r'(?:\s+(?:caption|with\s+caption|\u043f\u043e\u0434\u043f\u0438\u0441\u044c|\u0441\s+\u043f\u043e\u0434\u043f\u0438\u0441\u044c\u044e)\s+(.+))?$',
            normalized,
        )
        if not media_match:
            return None
        media_kind = self._canonicalize_media_kind(media_match.group(1))
        if media_kind not in {"photo", "video", "animation", "document", "audio"}:
            return None
        media = self._strip_wrapping_quotes(media_match.group(2).strip())
        caption_raw = (media_match.group(3) or "").strip()
        if not media:
            return None
        arguments: dict[str, object] = {
            "media_kind": media_kind,
            "media": media,
        }
        if caption_raw:
            arguments["caption"] = self._strip_wrapping_quotes(caption_raw)
        target = ResolvedActionTarget(
            kind="message",
            lookup=context.request_chat_id,
            label=f"message #{message_id}",
            chat_id=context.request_chat_id,
            message_id=message_id,
            source="reply_context" if context.reply_to_message_id is not None else "explicit",
        )
        return ActionRequest(
            "edit_message_media",
            normalized,
            context,
            target=target,
            arguments=arguments,
            summary=f"Replace media in message #{message_id}",
        )

    async def _parse_edit_reply_markup_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        markup_markers = (
            "reply markup",
            "inline keyboard",
            "keyboard",
            "buttons",
            "button",
            "\u043a\u043d\u043e\u043f",
            "\u043a\u043b\u0430\u0432\u0438\u0430\u0442\u0443\u0440",
            "\u0440\u0430\u0437\u043c\u0435\u0442",
        )
        if not any(marker in lowered for marker in markup_markers):
            return None
        message_id = self._extract_message_id(normalized) or context.reply_to_message_id
        if message_id is None:
            return None

        clear_markers = (
            "remove",
            "clear",
            "delete",
            "\u0443\u0431\u0435\u0440\u0438",
            "\u043e\u0447\u0438\u0441\u0442\u0438",
            "\u0443\u0434\u0430\u043b\u0438",
        )
        if any(marker in lowered for marker in clear_markers):
            target = ResolvedActionTarget(
                kind="message",
                lookup=context.request_chat_id,
                label=f"message #{message_id}",
                chat_id=context.request_chat_id,
                message_id=message_id,
                source="reply_context" if context.reply_to_message_id == message_id else "explicit",
            )
            return ActionRequest(
                "edit_message_reply_markup",
                normalized,
                context,
                target=target,
                arguments={"buttons": []},
                summary=f"Clear inline buttons on message #{message_id}",
            )

        button_match = re.search(
            r'(?iu)(?:button|\u043a\u043d\u043e\u043f\w*)\s+(".*?"|\'.*?\')\s+'
            r'(?:url|link|\u0441\u0441\u044b\u043b\w*|callback)\s+(".*?"|\'.*?\'|\S+)',
            normalized,
        )
        if not button_match:
            return None
        button_text = self._strip_wrapping_quotes(button_match.group(1).strip())
        target_value = self._strip_wrapping_quotes(button_match.group(2).strip())
        if not button_text or not target_value:
            return None
        button_payload: dict[str, str] = {"text": button_text}
        if re.search(r'(?iu)(?:callback)\s+(".*?"|\'.*?\'|\S+)', normalized):
            button_payload["callback_data"] = target_value
        else:
            button_payload["url"] = target_value
        target = ResolvedActionTarget(
            kind="message",
            lookup=context.request_chat_id,
            label=f"message #{message_id}",
            chat_id=context.request_chat_id,
            message_id=message_id,
            source="reply_context" if context.reply_to_message_id == message_id else "explicit",
        )
        return ActionRequest(
            "edit_message_reply_markup",
            normalized,
            context,
            target=target,
            arguments={"buttons": [button_payload]},
            summary=f"Update inline buttons on message #{message_id}",
        )

    async def _parse_delete_own_recent_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        delete_markers = (
            "delete",
            "remove",
            "\u0443\u0434\u0430\u043b\u0438",
            "\u0443\u0431\u0435\u0440\u0438",
            "\u043e\u0447\u0438\u0441\u0442\u0438",
        )
        own_markers = (
            " my ",
            "my last",
            "my recent",
            "my sent",
            "my outgoing",
            "outgoing",
            "sent messages",
            "\u043c\u043e\u0438",
            "\u043c\u043e\u0451",
            "\u043c\u043e\u0438 \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435",
            "\u043c\u043e\u0438 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043d\u044b\u0435",
            "\u0441\u0432\u043e\u0438",
            "\u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043d",
        )
        if not any(marker in lowered for marker in delete_markers):
            return None
        if not any(marker in lowered for marker in own_markers):
            return None
        target_reference: str | int | None = context.request_chat_id
        raw_target_reference = self._extract_target_after_preposition(
            normalized,
            (
                "in chat",
                "in dialog",
                "in channel",
                "in",
                "for chat",
                "for dialog",
                "for channel",
                "for",
                "from chat",
                "from dialog",
                "from channel",
                "from",
                "\u0432 \u0447\u0430\u0442\u0435",
                "\u0432 \u0434\u0438\u0430\u043b\u043e\u0433\u0435",
                "\u0432 \u043a\u0430\u043d\u0430\u043b\u0435",
                "\u0432",
                "\u0438\u0437 \u0447\u0430\u0442\u0430",
                "\u0438\u0437 \u0434\u0438\u0430\u043b\u043e\u0433\u0430",
                "\u0438\u0437 \u043a\u0430\u043d\u0430\u043b\u0430",
                "\u0438\u0437",
            ),
        )
        normalized_target_reference = self._normalize_target_reference(raw_target_reference)
        if normalized_target_reference is not None:
            saved_aliases = {
                "saved",
                "saved messages",
                "me",
                "\u0438\u0437\u0431\u0440\u0430\u043d\u043d\u043e\u0435",
                "\u0432 \u0438\u0437\u0431\u0440\u0430\u043d\u043d\u043e\u0435",
                "\u0432 \u0438\u0437\u0431\u0440\u0430\u043d\u043d\u043e\u043c",
                "\u0438\u0437\u0431\u0440\u0430\u043d\u043d\u043e\u043c",
                "\u0438\u0437 \u0438\u0437\u0431\u0440\u0430\u043d\u043d\u043e\u0433\u043e",
                "\u0438\u0437\u0431\u0440\u0430\u043d\u043d\u043e\u0433\u043e",
            }
            current_chat_aliases = {
                "this chat",
                "current chat",
                "\u044d\u0442\u043e\u0442 \u0447\u0430\u0442",
                "\u0432 \u044d\u0442\u043e\u0442 \u0447\u0430\u0442",
                "\u0432 \u044d\u0442\u043e\u043c \u0447\u0430\u0442\u0435",
                "\u044d\u0442\u043e\u043c \u0447\u0430\u0442\u0435",
                "\u0442\u0435\u043a\u0443\u0449\u0438\u0439 \u0447\u0430\u0442",
                "\u0432 \u0442\u0435\u043a\u0443\u0449\u0435\u043c \u0447\u0430\u0442\u0435",
                "\u0442\u0435\u043a\u0443\u0449\u0435\u043c \u0447\u0430\u0442\u0435",
            }
            target_lowered = " ".join(normalized_target_reference.casefold().split())
            if target_lowered in saved_aliases:
                target_reference = "me"
            elif target_lowered in current_chat_aliases:
                target_reference = context.request_chat_id
            else:
                target_reference = normalized_target_reference
        target = await self._build_chat_target(target_reference, context)
        singular_markers = (
            "last message",
            "last sent message",
            "last outgoing message",
            "\u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0435\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435",
            "\u043c\u043e\u0451 \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0435\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435",
            "\u043c\u043e\u0435 \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0435\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435",
            "\u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043d\u043e\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435",
        )
        default_limit = 1 if any(marker in lowered for marker in singular_markers) else 5
        limit = self._extract_count(normalized, default=default_limit)
        return ActionRequest(
            "delete_multiple_messages",
            normalized,
            context,
            target=target,
            arguments={
                "limit": limit,
                "mode": "recent",
                "filter_user_id": context.requester_user_id,
            },
            summary=f"Delete last {limit} own outgoing message(s) in {target.label}",
        )

    async def _parse_edit(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        markers = ("edit", "change message", "ÃÂ¸ÃÂ·ÃÂ¼ÃÂµÃÂ½ÃÂ¸ Ã‘ÂÃÂ¾ÃÂ¾ÃÂ±Ã‘â€°ÃÂµÃÂ½ÃÂ¸ÃÂµ", "ÃÂ¾Ã‘â€šÃ‘â‚¬ÃÂµÃÂ´ÃÂ°ÃÂºÃ‘â€šÃÂ¸Ã‘â‚¬Ã‘Æ’ÃÂ¹")
        if not any(marker in lowered for marker in markers):
            return None
        new_text = self._extract_quoted_text(normalized)
        if new_text is None:
            match = re.search(r"(?iu)\b(?:to|ÃÂ½ÃÂ°)\s+(.+)$", normalized)
            new_text = match.group(1).strip() if match else None
        if not new_text:
            return None
        message_id = context.reply_to_message_id or self._extract_message_id(normalized)
        if message_id is None:
            return None
        target = ResolvedActionTarget(
            kind="message",
            lookup=context.request_chat_id,
            label=f"message #{message_id}",
            chat_id=context.request_chat_id,
            message_id=message_id,
            source="reply_context" if context.reply_to_message_id is not None else "explicit",
        )
        return ActionRequest(
            "edit_own_message",
            normalized,
            context,
            target=target,
            arguments={"text": self._strip_wrapping_quotes(new_text)},
            summary=f"Edit message #{message_id}",
        )

    async def _parse_pin(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if any(m in lowered for m in ("pin", "ÃÂ·ÃÂ°ÃÂºÃ‘â‚¬ÃÂµÃÂ¿", "ÃÂ·ÃÂ°ÃÂºÃ‘â‚¬ÃÂµÃÂ¿ÃÂ¸", "ÃÂ¿Ã‘â‚¬ÃÂ¸ÃÂºÃ‘â‚¬ÃÂµÃÂ¿ÃÂ¸", "ÃÂ·ÃÂ°Ã‘â€žÃÂ¸ÃÂºÃ‘ÂÃÂ¸Ã‘â‚¬Ã‘Æ’ÃÂ¹")):
            if any(m in lowered for m in ("unpin", "ÃÂ¾Ã‘â€šÃÂºÃ‘â‚¬ÃÂµÃÂ¿", "ÃÂ¾Ã‘â€šÃÂºÃ‘â‚¬ÃÂµÃÂ¿ÃÂ¸", "Ã‘Æ’ÃÂ±ÃÂµÃ‘â‚¬ÃÂ¸ ÃÂ·ÃÂ°ÃÂºÃ‘â‚¬ÃÂµÃÂ¿", "Ã‘ÂÃÂ½Ã‘ÂÃ‘â€šÃ‘Å’ ÃÂ·ÃÂ°ÃÂºÃ‘â‚¬ÃÂµÃÂ¿")):
                action_name = "unpin_message"
            else:
                action_name = "pin_message"
            message_id = context.reply_to_message_id or self._extract_message_id(normalized)
            target = await self._build_chat_target(None, context)
            if action_name == "unpin_message" and message_id is None:
                return ActionRequest(action_name, normalized, context, target=target, summary=f"Unpin all messages in {target.label}")
            if message_id is None:
                return None
            target.message_id = message_id
            return ActionRequest(action_name, normalized, context, target=target, summary=f"{'Unpin' if action_name == 'unpin_message' else 'Pin'} message #{message_id} in {target.label}")
        return None

    async def _parse_reaction(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if context.reply_to_message_id is None:
            return None
        if not any(marker in lowered for marker in ("react", "reaction", "Ã‘â‚¬ÃÂµÃÂ°ÃÂºÃ‘â€ ", "Ã‘ÂÃÂ¼ÃÂ¾ÃÂ´ÃÂ·ÃÂ¸", "ÃÂ¿ÃÂ¾Ã‘ÂÃ‘â€šÃÂ°ÃÂ²Ã‘Å’ Ã‘â‚¬ÃÂµÃÂ°ÃÂºÃ‘â€ ÃÂ¸Ã‘Å½", "ÃÂ»ÃÂ°ÃÂ¹ÃÂº", "ÃÂ»ÃÂ°ÃÂ¹ÃÂºÃÂ½ÃÂ¸", "like", "send reaction", "ÃÂ¾Ã‘â€šÃ‘â‚¬ÃÂµÃÂ°ÃÂ³ÃÂ¸Ã‘â‚¬Ã‘Æ’ÃÂ¹")):
            return None
        emoji = self._extract_quoted_text(normalized) or "Ã°Å¸â€˜Â"
        target = ResolvedActionTarget(
            kind="message",
            lookup=context.request_chat_id,
            label=f"message #{context.reply_to_message_id}",
            chat_id=context.request_chat_id,
            message_id=context.reply_to_message_id,
            source="reply_context",
        )
        return ActionRequest(
            "send_reaction",
            normalized,
            context,
            target=target,
            arguments={"emoji": self._strip_wrapping_quotes(emoji)},
            summary=f"React to message #{context.reply_to_message_id} with {emoji}",
        )

    async def _parse_reply(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if context.reply_to_message_id is None:
            return None
        if not any(marker in lowered for marker in ("reply", "answer", "ÃÂ¾Ã‘â€šÃÂ²ÃÂµÃ‘â€šÃ‘Å’", "ÃÂ½ÃÂ°ÃÂ¿ÃÂ¸Ã‘Ë†ÃÂ¸ ÃÂ² ÃÂ¾Ã‘â€šÃÂ²ÃÂµÃ‘â€š", "ÃÂ¾Ã‘â€šÃÂ²ÃÂµÃ‘â€¡ÃÂ°ÃÂ¹", "ÃÂ½ÃÂ°ÃÂ¿ÃÂ¸Ã‘Ë†ÃÂ¸ ÃÂ¾Ã‘â€šÃÂ²ÃÂµÃ‘â€š", "ÃÂ¾Ã‘â€šÃÂ²ÃÂµÃ‘â€šÃÂ¸Ã‘â€šÃ‘Å’")):
            return None
        text = self._extract_quoted_text(normalized)
        if text is None:
            match = re.search(r"(?iu)\b(?:reply|answer|ÃÂ¾Ã‘â€šÃÂ²ÃÂµÃ‘â€šÃ‘Å’)\b\s+(.+)$", normalized)
            text = match.group(1).strip() if match else None
        if not text:
            return None
        target = ResolvedActionTarget(
            kind="message",
            lookup=context.request_chat_id,
            label=f"message #{context.reply_to_message_id}",
            chat_id=context.request_chat_id,
            message_id=context.reply_to_message_id,
            source="reply_context",
        )
        return ActionRequest(
            "reply_to_message",
            normalized,
            context,
            target=target,
            arguments={"text": self._strip_wrapping_quotes(text)},
            summary=f"Reply to message #{context.reply_to_message_id}",
        )

    async def _parse_send(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not any(marker in lowered for marker in ("send", "write", "ÃÂ½ÃÂ°ÃÂ¿ÃÂ¸Ã‘Ë†ÃÂ¸", "ÃÂ¾Ã‘â€šÃÂ¿Ã‘â‚¬ÃÂ°ÃÂ²Ã‘Å’", "Ã‘ÂÃÂºÃÂ¸ÃÂ½Ã‘Å’", "ÃÂ¿ÃÂ¾Ã‘Ë†ÃÂ»ÃÂ¸", "ÃÂ·ÃÂ°ÃÂºÃÂ¸ÃÂ½Ã‘Å’", "ÃÂ½ÃÂ°ÃÂ¿ÃÂ¸Ã‘ÂÃÂ°Ã‘â€šÃ‘Å’", "Ã‘ÂÃÂºÃÂ°ÃÂ¶ÃÂ¸", "ÃÂ¿ÃÂµÃ‘â‚¬ÃÂµÃÂ´ÃÂ°ÃÂ¹", "ÃÂ¾Ã‘â€šÃÂ¾Ã‘Ë†ÃÂ»ÃÂ¸")):
            return None
        quoted = self._extract_quoted_text(normalized)
        target_ref = self._extract_send_target_reference(normalized)
        if quoted is None and target_ref is None:
            return None
        text = quoted
        if text is None:
            head, _, tail = normalized.partition(" ÃÂ² ")
            if not tail:
                head, _, tail = normalized.partition(" to ")
            if not tail:
                return None
            text = re.sub(r"(?iu)^(?:send|write|ÃÂ½ÃÂ°ÃÂ¿ÃÂ¸Ã‘Ë†ÃÂ¸|ÃÂ¾Ã‘â€šÃÂ¿Ã‘â‚¬ÃÂ°ÃÂ²Ã‘Å’|Ã‘ÂÃÂºÃÂ¸ÃÂ½Ã‘Å’)(?:\s+(?:Ã‘â€šÃÂµÃÂºÃ‘ÂÃ‘â€š|Ã‘ÂÃÂ¾ÃÂ¾ÃÂ±Ã‘â€°ÃÂµÃÂ½ÃÂ¸ÃÂµ|Ã‘â€žÃ‘â‚¬ÃÂ°ÃÂ·Ã‘Æ’))?\s+", "", head).strip()
            target_ref = tail.strip()
        if not text:
            return None
        target = await self._build_chat_target(target_ref, context)
        return ActionRequest(
            "send_message",
            normalized,
            context,
            target=target,
            arguments={"text": self._strip_wrapping_quotes(text)},
            summary=f"Send a message to {target.label}",
        )

    async def _parse_forward_or_copy(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if context.reply_to_message_id is None:
            return None
        if not any(marker in lowered for marker in ("forward", "copy", "ÃÂ¿ÃÂµÃ‘â‚¬ÃÂµÃ‘Ë†ÃÂ»ÃÂ¸", "ÃÂ¿ÃÂµÃ‘â‚¬ÃÂµÃÂºÃÂ¸ÃÂ½Ã‘Å’", "Ã‘ÂÃÂºÃÂ¾ÃÂ¿ÃÂ¸Ã‘â‚¬Ã‘Æ’ÃÂ¹", "ÃÂ¿ÃÂµÃ‘â‚¬ÃÂµÃ‘ÂÃÂ»ÃÂ°Ã‘â€šÃ‘Å’", "Ã‘ÂÃÂºÃÂ¸ÃÂ½Ã‘Å’ Ã‘ÂÃ‘â€šÃÂ¾", "forward this", "copy this", "ÃÂ¿ÃÂµÃ‘â‚¬ÃÂµÃ‘Ë†ÃÂ»Ã‘â€˜Ã‘â€š", "ÃÂ¿ÃÂµÃ‘â‚¬ÃÂµÃ‘â€žÃÂ¾Ã‘â‚¬ÃÂ²ÃÂ°Ã‘â‚¬ÃÂ´Ã‘Å’")):
            return None
        action_name = "copy_message" if any(marker in lowered for marker in ("copy", "Ã‘ÂÃÂºÃÂ¾ÃÂ¿ÃÂ¸Ã‘â‚¬Ã‘Æ’ÃÂ¹", "Ã‘ÂÃÂºÃÂ¾ÃÂ¿ÃÂ¸Ã‘â‚¬ÃÂ¾ÃÂ²ÃÂ°Ã‘â€šÃ‘Å’")) else "forward_message"
        target_ref = self._extract_target_after_preposition(normalized, ("to", "ÃÂ²", "chat", "Ã‘â€¡ÃÂ°Ã‘â€š"))
        target = await self._build_chat_target(target_ref, context)
        source = ResolvedActionTarget(
            kind="message",
            lookup=context.request_chat_id,
            label=f"message #{context.reply_to_message_id}",
            chat_id=context.request_chat_id,
            message_id=context.reply_to_message_id,
            source="reply_context",
        )
        return ActionRequest(
            action_name,
            normalized,
            context,
            target=source,
            secondary_target=target,
            summary=f"{'Copy' if action_name == 'copy_message' else 'Forward'} message #{context.reply_to_message_id} to {target.label}",
        )

    async def _parse_copy_with_caption_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        copy_markers = (
            "copy",
            "resend",
            "repost",
            "\u0441\u043a\u043e\u043f\u0438\u0440\u0443\u0439",
            "\u043f\u0435\u0440\u0435\u043e\u0442\u043f\u0440\u0430\u0432\u044c",
            "\u043f\u0435\u0440\u0435\u0448\u043b\u0438 \u0437\u0430\u043d\u043e\u0432\u043e",
            "\u043e\u0442\u043f\u0440\u0430\u0432\u044c \u0437\u0430\u043d\u043e\u0432\u043e",
        )
        if not any(marker in lowered for marker in copy_markers):
            return None
        if not any(marker in lowered for marker in ("caption", "\u043f\u043e\u0434\u043f\u0438\u0441")):
            return None
        verb_match = re.match(
            r'(?iu)^(?:copy|resend|repost|\u0441\u043a\u043e\u043f\u0438\u0440\u0443\u0439|\u043f\u0435\u0440\u0435\u043e\u0442\u043f\u0440\u0430\u0432\u044c|\u043f\u0435\u0440\u0435\u0448\u043b\u0438\s+\u0437\u0430\u043d\u043e\u0432\u043e|\u043e\u0442\u043f\u0440\u0430\u0432\u044c\s+\u0437\u0430\u043d\u043e\u0432\u043e)\s+(.+)$',
            normalized,
        )
        if not verb_match:
            return None
        rest = verb_match.group(1).strip()
        if not rest:
            return None

        explicit_message_match = re.match(r'(?iu)^(?:message|msg|\u0441\u043e\u043e\u0431\u0449\u0435\u043d\w*|#)\s*#?\s*(-?\d+)\s+(.*)$', rest)
        message_id = None
        if explicit_message_match:
            try:
                message_id = int(explicit_message_match.group(1))
            except ValueError:
                return None
            rest = explicit_message_match.group(2).strip()
        else:
            rest = re.sub(
                r'(?iu)^(?:replied\s+message|this(?:\s+message)?|reply|replied|\u044d\u0442\u043e(?:\s+\u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435)?|\u0440\u0435\u043f\u043b\u0430[^\s]*)\s+',
                "",
                rest,
                count=1,
            ).strip()
        message_id = message_id or context.reply_to_message_id
        if message_id is None:
            return None

        target_ref = None
        caption = None

        target_then_caption = re.match(
            r'(?iu)^(?:to|into|\u0432)\s+(?:chat\s+|dialog\s+|channel\s+|\u0447\u0430\u0442\s+|\u0434\u0438\u0430\u043b\u043e\u0433\s+|\u043a\u0430\u043d\u0430\u043b\s+)?(.+?)\s+(?:caption|with\s+caption|\u043f\u043e\u0434\u043f\u0438\u0441\u044c|\u0441\s+\u043f\u043e\u0434\u043f\u0438\u0441\u044c\u044e)\s+(.+)$',
            rest,
        )
        if target_then_caption:
            target_ref = self._normalize_target_reference(target_then_caption.group(1))
            caption = self._strip_wrapping_quotes(target_then_caption.group(2).strip())
        else:
            caption_then_target = re.match(
                r'(?iu)^(?:caption|with\s+caption|\u043f\u043e\u0434\u043f\u0438\u0441\u044c|\u0441\s+\u043f\u043e\u0434\u043f\u0438\u0441\u044c\u044e)\s+(.+?)(?:\s+(?:to|into|\u0432)\s+(?:chat\s+|dialog\s+|channel\s+|\u0447\u0430\u0442\s+|\u0434\u0438\u0430\u043b\u043e\u0433\s+|\u043a\u0430\u043d\u0430\u043b\s+)?(.+))?$',
                rest,
            )
            if caption_then_target:
                caption = self._strip_wrapping_quotes(caption_then_target.group(1).strip())
                target_ref = self._normalize_target_reference(caption_then_target.group(2))

        if not caption:
            return None

        target = await self._build_chat_target(target_ref, context)
        source = ResolvedActionTarget(
            kind="message",
            lookup=context.request_chat_id,
            label=f"message #{message_id}",
            chat_id=context.request_chat_id,
            message_id=message_id,
            source="reply_context" if context.reply_to_message_id == message_id else "explicit",
        )
        return ActionRequest(
            "copy_message",
            normalized,
            context,
            target=source,
            secondary_target=target,
            arguments={"caption": caption},
            summary=f"Copy message #{message_id} to {target.label} with a modified caption",
        )

    async def _parse_draft(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not any(marker in lowered for marker in ("draft", "Ã‘â€¡ÃÂµÃ‘â‚¬ÃÂ½ÃÂ¾ÃÂ²ÃÂ¸ÃÂº", "preview", "ÃÂ¿ÃÂ»ÃÂ°ÃÂ½ ÃÂ´ÃÂµÃÂ¹Ã‘ÂÃ‘â€šÃÂ²ÃÂ¸Ã‘Â", "show plan")):
            return None
        return ActionRequest(
            "generate_draft",
            normalized,
            context,
            arguments={"text": normalized},
            summary="Generate a draft or execution preview without sending",
        )

    async def _build_cross_chat_target(self, reference: str | int, context: ActionContext) -> ResolvedActionTarget:
        chat = await self._tg_actions.resolve_chat(reference, current_chat_id=context.request_chat_id)
        return ResolvedActionTarget(
            kind=chat.kind,
            lookup=chat.lookup,
            label=chat.label,
            chat_id=chat.chat_id,
            user_id=chat.user_id,
        )

    async def _build_chat_target(self, reference: str | int | None, context: ActionContext) -> ResolvedActionTarget:
        if reference is None:
            session_target = self.get_selected_target(context.request_chat_id)
            if session_target is not None and session_target.kind in {"chat", "user"}:
                reference = session_target.reference
            else:
                # No session target Ã¢â‚¬â€ fall back to current chat
                reference = context.request_chat_id
        chat = await self._tg_actions.resolve_chat(reference, current_chat_id=context.request_chat_id)
        return ResolvedActionTarget(
            kind=chat.kind,
            lookup=chat.lookup,
            label=chat.label,
            chat_id=chat.chat_id,
            user_id=chat.user_id,
        )

    async def _build_user_target(self, reference: str | int | None, context: ActionContext) -> ResolvedActionTarget:
        if reference is None:
            if context.reply_to_user_id is not None:
                reference = context.reply_to_user_id
            else:
                session_target = self.get_selected_target(context.request_chat_id)
                if session_target is not None and session_target.kind == "user":
                    reference = session_target.reference
        user = await self._tg_actions.resolve_user(reference, fallback_user_id=context.reply_to_user_id)
        return ResolvedActionTarget(
            kind="user",
            lookup=user.lookup,
            label=user.label,
            chat_id=user.chat_id,
            user_id=user.user_id,
        )

    def _remember_request_target(self, request: ActionRequest) -> None:
        if request.action_name == "select_target" and request.target is not None:
            self.record_selected_target(request.context.request_chat_id, request.target)
            return
        if request.target is not None and request.target.lookup is not None and request.target.kind in {"chat", "user"}:
            self.record_selected_target(request.context.request_chat_id, request.target)
        elif request.secondary_target is not None and request.secondary_target.lookup is not None:
            self.record_selected_target(request.context.request_chat_id, request.secondary_target)

    def _extract_quoted_text(self, text: str) -> str | None:
        match = QUOTED_RE.search(text)
        if not match:
            return None
        return match.group(1).strip()

    def _extract_send_target_reference(self, text: str) -> str | None:
        patterns = (
            r'(?iu)\b(?:to|ÃÂ²)\s+(?:chat\s+|Ã‘â€¡ÃÂ°Ã‘â€š(?:\s+Ã‘Â\s+ÃÂ½ÃÂ°ÃÂ·ÃÂ²ÃÂ°ÃÂ½ÃÂ¸ÃÂµÃÂ¼)?\s+)?(.+)$',
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return self._strip_wrapping_quotes(match.group(1).strip())
        return None

    def _extract_target_after_preposition(self, text: str, tokens: tuple[str, ...]) -> str | None:
        lowered = text.casefold()
        for token in tokens:
            marker = f" {token.casefold()} "
            index = lowered.find(marker)
            if index >= 0:
                return self._strip_wrapping_quotes(text[index + len(marker):].strip())
        return None

    def _extract_blocking_target_reference(self, text: str, *, unblock: bool) -> str | None:
        verb_pattern = (
            r"(?:unblock|разблок(?:ируй|ировать)?)"
            if unblock
            else r"(?:block|заблок(?:ируй|ировать)?)"
        )
        match = re.match(
            rf'(?iu)^{verb_pattern}\s+(?:user\s+|пользовател(?:я|ей|ю)?\s+|юзер(?:а|у|ом)?\s+)?(?P<user>".*?"|\'.*?\'|.+?)$',
            (text or "").strip(),
        )
        if not match:
            return None
        return self._normalize_member_reference(match.group("user"))

    def _extract_count(self, text: str, *, default: int) -> int:
        match = COUNT_RE.search(text)
        if not match:
            return default
        try:
            return max(1, min(int(match.group(1)), 100))
        except ValueError:
            return default

    def _extract_message_id(self, text: str) -> int | None:
        match = MESSAGE_ID_RE.search(text)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    def _strip_wrapping_quotes(self, text: str) -> str:
        stripped = (text or "").strip()
        if len(stripped) >= 2 and stripped[0] in {'"', "'"} and stripped[-1] == stripped[0]:
            return stripped[1:-1].strip()
        return stripped

    def _looks_like_send_command(self, lowered: str) -> bool:
        return SEND_PREFIX_RE.match((lowered or "").strip()) is not None

    def _normalize_target_reference(self, raw: str | None) -> str | None:
        cleaned = self._strip_wrapping_quotes((raw or "").strip()) or None
        if cleaned is None:
            return None
        normalized = " ".join(cleaned.casefold().split())
        if normalized in {
            "here",
            "this chat",
            "current chat",
            "\u0441\u044e\u0434\u0430",
            "\u044d\u0442\u043e\u0442 \u0447\u0430\u0442",
            "\u0442\u0435\u043a\u0443\u0449\u0438\u0439 \u0447\u0430\u0442",
            "\u0432 \u044d\u0442\u043e\u0442 \u0447\u0430\u0442",
            "\u0432 \u0442\u0435\u043a\u0443\u0449\u0438\u0439 \u0447\u0430\u0442",
        }:
            return None
        return cleaned

    def _looks_like_linked_target_reference(self, raw: str | None) -> bool:
        cleaned = self._strip_wrapping_quotes((raw or "").strip())
        if not cleaned:
            return False
        normalized = " ".join(cleaned.casefold().split())
        markers = (
            "linked chat",
            "linked channel",
            "discussion chat",
            "discussion group",
            "\u0441\u0432\u044f\u0437\u0430\u043d",
            "\u0447\u0430\u0442 \u043e\u0431\u0441\u0443\u0436\u0434",
            "\u0433\u0440\u0443\u043f\u043f\u0430 \u043e\u0431\u0441\u0443\u0436\u0434",
            "\u043a\u0430\u043d\u0430\u043b \u043e\u0431\u0441\u0443\u0436\u0434",
        )
        return any(marker in normalized for marker in markers)

    def _looks_like_non_text_send_payload(self, raw_text: str | None) -> bool:
        cleaned = self._strip_wrapping_quotes((raw_text or "").strip())
        if not cleaned:
            return False
        normalized = " ".join(cleaned.casefold().split())
        parts = normalized.split()
        first_token = parts[0]
        first_two_tokens = " ".join(parts[:2])
        if self._canonicalize_media_kind(first_token) is not None or self._canonicalize_media_kind(first_two_tokens) is not None:
            return True
        structured_markers = (
            "media group",
            "album",
            "contact",
            "location",
            "geo",
            "point",
            "venue",
            "place",
            "poll",
            "survey",
            "dice",
            "throw",
            "roll",
            "\u0430\u043b\u044c\u0431\u043e\u043c",
            "\u043c\u0435\u0434\u0438\u0430\u0433\u0440\u0443\u043f\u043f",
            "\u043a\u043e\u043d\u0442\u0430\u043a\u0442",
            "\u043b\u043e\u043a\u0430\u0446",
            "\u0433\u0435\u043e",
            "\u0442\u043e\u0447\u043a",
            "\u043c\u0435\u0441\u0442",
            "\u043e\u043f\u0440\u043e\u0441",
            "\u0433\u043e\u043b\u043e\u0441\u043e\u0432\u0430\u043d",
            "\u043a\u0443\u0431\u0438\u043a",
            "\u0431\u0440\u043e\u0441",
        )
        return any(normalized.startswith(marker) for marker in structured_markers)

    def _canonicalize_media_kind(self, raw_kind: str) -> str | None:
        normalized = " ".join((raw_kind or "").casefold().split())
        exact_alias_map = {
            "photo": {"photo", "image", "picture"},
            "video": {"video", "clip"},
            "video_note": {"video note", "video_note", "round video", "circle video"},
            "animation": {"animation", "gif"},
            "document": {"document", "file", "doc"},
            "audio": {"audio", "track", "music", "song"},
            "voice": {"voice", "voice message", "voice note"},
            "sticker": {"sticker"},
        }
        for canonical, aliases in exact_alias_map.items():
            if normalized in aliases:
                return canonical
        stem_aliases = {
            "photo": ("\u0444\u043e\u0442", "\u043a\u0430\u0440\u0442\u0438\u043d", "\u0438\u0437\u043e\u0431\u0440\u0430\u0436\u0435\u043d"),
            "video": ("\u0432\u0438\u0434\u0435\u043e", "\u0440\u043e\u043b\u0438\u043a"),
            "video_note": ("\u043a\u0440\u0443\u0436\u043e\u043a", "\u0432\u0438\u0434\u0435\u043e\u0441\u043e\u043e\u0431\u0449\u0435\u043d"),
            "animation": ("\u0433\u0438\u0444", "\u0430\u043d\u0438\u043c\u0430\u0446"),
            "document": ("\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442", "\u0444\u0430\u0439\u043b"),
            "audio": ("\u0430\u0443\u0434\u0438\u043e", "\u0442\u0440\u0435\u043a", "\u043c\u0443\u0437\u044b\u043a"),
            "voice": ("\u0433\u043e\u043b\u043e\u0441\u043e\u0432",),
            "sticker": ("\u0441\u0442\u0438\u043a\u0435\u0440",),
        }
        for canonical, stems in stem_aliases.items():
            if any(normalized.startswith(stem) for stem in stems):
                return canonical
        return None

    def _canonicalize_media_group_kind(self, raw_kind: str) -> str | None:
        canonical = self._canonicalize_media_kind(raw_kind)
        if canonical in {"photo", "video", "audio", "document"}:
            return canonical
        return None

    def _canonicalize_dice_emoji(self, raw_text: str) -> str | None:
        text = " ".join((raw_text or "").strip().casefold().split())
        if not text:
            return None
        for emoji in ("🎲", "🎯", "🏀", "⚽", "🎳", "🎰"):
            if emoji in raw_text:
                return emoji
        alias_groups = (
            ("🎲", ("dice", "die", "кубик", "кость", "игральная кость")),
            ("🎯", ("dart", "darts", "bullseye", "дротик", "мишень")),
            ("🏀", ("basketball", "баскетбол")),
            ("⚽", ("football", "soccer", "футбол")),
            ("🎳", ("bowling", "боулинг")),
            ("🎰", ("slot", "slots", "slot machine", "casino", "слот", "автомат")),
        )
        for emoji, aliases in alias_groups:
            if any(alias in text for alias in aliases):
                return emoji
        return None

    def _resolve_chat_target_reference_or_current(self, raw_target_ref: str | None, context: ActionContext) -> str | int:
        current_chat_aliases = {
            "this chat",
            "current chat",
            "\u044d\u0442\u043e\u0442 \u0447\u0430\u0442",
            "\u0432 \u044d\u0442\u043e\u0442 \u0447\u0430\u0442",
            "\u0432 \u044d\u0442\u043e\u043c \u0447\u0430\u0442\u0435",
            "\u044d\u0442\u043e\u043c \u0447\u0430\u0442\u0435",
            "\u0442\u0435\u043a\u0443\u0449\u0438\u0439 \u0447\u0430\u0442",
            "\u0432 \u0442\u0435\u043a\u0443\u0449\u0435\u043c \u0447\u0430\u0442\u0435",
            "\u0442\u0435\u043a\u0443\u0449\u0435\u043c \u0447\u0430\u0442\u0435",
        }
        raw_target_lower = " ".join((raw_target_ref or "").casefold().split())
        if raw_target_lower in current_chat_aliases:
            return context.request_chat_id
        normalized_target = self._normalize_target_reference(raw_target_ref)
        if normalized_target is not None:
            return normalized_target
        return context.request_chat_id

    def _normalize_member_reference(self, raw_user_ref: str | None) -> str | None:
        cleaned = self._strip_wrapping_quotes((raw_user_ref or "").strip())
        if not cleaned:
            return None
        normalized = " ".join(cleaned.casefold().split())
        reply_aliases = {
            "reply",
            "reply user",
            "replied user",
            "this user",
            "that user",
            "him",
            "her",
            "\u0440\u0435\u043f\u043b\u0430\u0439",
            "\u0432 \u0440\u0435\u043f\u043b\u0430\u0435",
            "\u043f\u043e \u0440\u0435\u043f\u043b\u0430\u044e",
            "\u044d\u0442\u043e\u0433\u043e \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f",
            "\u044d\u0442\u043e\u0433\u043e \u044e\u0437\u0435\u0440\u0430",
            "\u0435\u0433\u043e",
            "\u0435\u0435",
            "\u0435\u0451",
        }
        if normalized in reply_aliases:
            return None
        for prefix in (
            "user ",
            "member ",
            "chat member ",
            "\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f ",
            "\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c ",
            "\u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u0430 ",
            "\u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a ",
            "\u044e\u0437\u0435\u0440\u0430 ",
            "\u044e\u0437\u0435\u0440 ",
        ):
            if normalized.startswith(prefix):
                return cleaned[len(prefix):].strip() or None
        return cleaned

    def _permission_preset_from_text(self, raw_text: str | None, *, default_key: str | None = None) -> tuple[str, dict[str, bool]] | None:
        normalized = " ".join((raw_text or "").casefold().split())
        full = {
            "can_send_messages": True,
            "can_send_media_messages": True,
            "can_send_other_messages": True,
            "can_send_polls": True,
            "can_add_web_page_previews": True,
            "can_change_info": True,
            "can_invite_users": True,
            "can_pin_messages": True,
        }
        text_only = {
            "can_send_messages": True,
            "can_send_media_messages": False,
            "can_send_other_messages": False,
            "can_send_polls": False,
            "can_add_web_page_previews": False,
            "can_change_info": False,
            "can_invite_users": False,
            "can_pin_messages": False,
        }
        standard = {
            "can_send_messages": True,
            "can_send_media_messages": True,
            "can_send_other_messages": True,
            "can_send_polls": True,
            "can_add_web_page_previews": True,
            "can_change_info": False,
            "can_invite_users": True,
            "can_pin_messages": False,
        }
        read_only = {
            "can_send_messages": False,
            "can_send_media_messages": False,
            "can_send_other_messages": False,
            "can_send_polls": False,
            "can_add_web_page_previews": False,
            "can_change_info": False,
            "can_invite_users": False,
            "can_pin_messages": False,
        }
        if any(marker in normalized for marker in ("read only", "readonly", "mute", "muted", "no messages", "silent", "\u0442\u043e\u043b\u044c\u043a\u043e \u0447\u0438\u0442\u0430\u0442\u044c", "\u0447\u0438\u0442\u0430\u0442\u044c \u0442\u043e\u043b\u044c\u043a\u043e", "\u0431\u0435\u0437 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0439", "\u0431\u0435\u0437 \u043f\u0440\u0430\u0432", "\u043c\u0443\u0442")):
            return ("read only", read_only)
        if any(marker in normalized for marker in ("text only", "only text", "messages only", "\u0442\u043e\u043b\u044c\u043a\u043e \u0442\u0435\u043a\u0441\u0442", "\u0442\u043e\u043b\u044c\u043a\u043e \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f")):
            return ("text only", text_only)
        if any(marker in normalized for marker in ("standard", "normal", "default", "regular", "media and text", "text and media", "\u0441\u0442\u0430\u043d\u0434\u0430\u0440\u0442", "\u043e\u0431\u044b\u0447\u043d", "\u043f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e")):
            return ("standard", standard)
        if any(marker in normalized for marker in ("all permissions", "full permissions", "full access", "allow all", "unrestricted", "open", "\u0432\u0441\u0435 \u043f\u0440\u0430\u0432\u0430", "\u043f\u043e\u043b\u043d\u044b\u0439 \u0434\u043e\u0441\u0442\u0443\u043f", "\u0431\u0435\u0437 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u0439", "\u0440\u0430\u0437\u0440\u0435\u0448\u0438 \u0432\u0441\u0435")):
            return ("all permissions", full)
        if default_key == "read_only":
            return ("read only", read_only)
        if default_key == "all":
            return ("all permissions", full)
        return None

    def _admin_privilege_preset_from_text(self, raw_text: str | None, *, default_key: str | None = None) -> tuple[str, dict[str, bool]] | None:
        normalized = " ".join((raw_text or "").casefold().split())
        full = {
            "can_manage_chat": True,
            "can_delete_messages": True,
            "can_manage_video_chats": True,
            "can_restrict_members": True,
            "can_promote_members": True,
            "can_change_info": True,
            "can_post_messages": True,
            "can_edit_messages": True,
            "can_invite_users": True,
            "can_pin_messages": True,
            "is_anonymous": False,
        }
        basic = {
            "can_manage_chat": True,
            "can_delete_messages": True,
            "can_manage_video_chats": True,
            "can_restrict_members": True,
            "can_promote_members": False,
            "can_change_info": False,
            "can_post_messages": False,
            "can_edit_messages": False,
            "can_invite_users": True,
            "can_pin_messages": True,
            "is_anonymous": False,
        }
        if any(marker in normalized for marker in ("full admin", "all admin rights", "full privileges", "super admin", "\u043f\u043e\u043b\u043d\u044b\u0439 \u0430\u0434\u043c\u0438\u043d", "\u0432\u0441\u0435 \u043f\u0440\u0430\u0432\u0430 \u0430\u0434\u043c\u0438\u043d\u0430")):
            return ("full admin", full)
        if any(marker in normalized for marker in ("admin", "administrator", "basic admin", "moderator", "mod", "\u0430\u0434\u043c\u0438\u043d", "\u0430\u0434\u043c\u0438\u043d\u043e\u043c", "\u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440", "\u043c\u043e\u0434\u0435\u0440\u0430\u0442\u043e\u0440", "\u043c\u043e\u0434\u0435\u0440\u0430\u0442\u043e\u0440\u043e\u043c")):
            return ("basic admin", basic)
        if default_key == "basic":
            return ("basic admin", basic)
        if default_key == "full":
            return ("full admin", full)
        return None

    def _extract_invite_link_token(self, text: str) -> str | None:
        match = re.search(r'(?iu)(https?://t\.me/\S+|https?://telegram\.me/\S+|t\.me/\S+)', text or "")
        if match:
            return self._strip_wrapping_quotes(match.group(1).strip())
        return None

    def _extract_invite_link_name(self, text: str) -> str | None:
        patterns = (
            r'(?iu)\b(?:name|title)\s+(".*?"|\'.*?\'|\S+)',
            r'(?iu)\b(?:\u0438\u043c\u044f|\u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435)\s+(".*?"|\'.*?\'|\S+)',
        )
        for pattern in patterns:
            match = re.search(pattern, text or "")
            if match:
                return self._strip_wrapping_quotes(match.group(1).strip()) or None
        return None

    def _extract_invite_link_limit(self, text: str) -> int | None:
        patterns = (
            r'(?iu)\b(?:member\s+limit|usage\s+limit|limit)\s+(\d{1,5})',
            r'(?iu)\b(?:\u043b\u0438\u043c\u0438\u0442)\s+(\d{1,5})',
        )
        for pattern in patterns:
            match = re.search(pattern, text or "")
            if match:
                try:
                    return max(1, min(int(match.group(1)), 99999))
                except ValueError:
                    return None
        return None

    def _extract_invite_link_expire_date(self, text: str) -> datetime | None:
        patterns = (
            r'(?iu)\b(?:expire|expires|until|expire_date)\s+(".*?"|\'.*?\'|\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2})?)',
            r'(?iu)\b(?:\u0434\u043e|\u0438\u0441\u0442\u0435\u043a\u0430\u0435\u0442|(?:\u0441\u0440\u043e\u043a(?:\s+\u0434\u043e)?))\s+(".*?"|\'.*?\'|\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2})?)',
        )
        for pattern in patterns:
            match = re.search(pattern, text or "")
            if not match:
                continue
            raw_value = self._strip_wrapping_quotes(match.group(1).strip())
            if not raw_value:
                continue
            try:
                return datetime.fromisoformat(raw_value.replace("T", " "))
            except ValueError:
                continue
        return None

    def _extract_invite_link_join_request_flag(self, text: str) -> bool | None:
        normalized = " ".join((text or "").casefold().split())
        if any(marker in normalized for marker in ("no join request", "without approval", "direct join", "without requests", "\u0431\u0435\u0437 \u0437\u0430\u044f\u0432\u043e\u043a", "\u0431\u0435\u0437 \u043e\u0434\u043e\u0431\u0440\u0435\u043d\u0438\u044f")):
            return False
        if any(marker in normalized for marker in ("join request", "approval", "request needed", "by request", "\u043f\u043e \u0437\u0430\u044f\u0432\u043a\u0435", "\u0441 \u043e\u0434\u043e\u0431\u0440\u0435\u043d\u0438\u0435\u043c", "\u0442\u0440\u0435\u0431\u0443\u0435\u0442 \u043e\u0434\u043e\u0431\u0440\u0435\u043d\u0438\u044f")):
            return True
        return None

    def _split_poll_options(self, raw_options: str) -> list[str]:
        text = (raw_options or "").strip()
        if "|" in text:
            parts = text.split("|")
        elif ";" in text:
            parts = text.split(";")
        else:
            parts = text.split(",")
        return [
            option
            for option in (
                self._strip_wrapping_quotes(part.strip())
                for part in parts
            )
            if option
        ]

    async def _parse_pin_v2(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        pin_markers = (
            "pin",
            "\u0437\u0430\u043a\u0440\u0435\u043f",
            "\u043f\u0440\u0438\u043a\u0440\u0435\u043f",
        )
        unpin_markers = (
            "unpin",
            "\u043e\u0442\u043a\u0440\u0435\u043f",
            "\u0441\u043d\u0438\u043c\u0438 \u0437\u0430\u043a\u0440\u0435\u043f",
            "\u0443\u0431\u0435\u0440\u0438 \u0437\u0430\u043a\u0440\u0435\u043f",
        )
        unpin_all_markers = (
            "unpin all",
            "unpin all messages",
            "unpin all pinned messages",
            "clear all pins",
            "remove all pins",
            "clear pinned messages",
            "remove pinned messages",
            "\u043e\u0442\u043a\u0440\u0435\u043f\u0438 \u0432\u0441\u0435",
            "\u043e\u0442\u043a\u0440\u0435\u043f\u0438 \u0432\u0441\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f",
            "\u0441\u043d\u0438\u043c\u0438 \u0432\u0441\u0435 \u0437\u0430\u043a\u0440\u0435\u043f\u044b",
            "\u0443\u0431\u0435\u0440\u0438 \u0432\u0441\u0435 \u0437\u0430\u043a\u0440\u0435\u043f\u044b",
            "\u043e\u0447\u0438\u0441\u0442\u0438 \u0432\u0441\u0435 \u0437\u0430\u043a\u0440\u0435\u043f\u044b",
        )
        if any(marker in lowered for marker in unpin_all_markers):
            raw_target_ref = self._extract_target_after_preposition(
                normalized,
                (
                    "in chat",
                    "in channel",
                    "in group",
                    "in",
                    "for chat",
                    "for channel",
                    "for group",
                    "for",
                    "\u0432 \u0447\u0430\u0442\u0435",
                    "\u0432 \u043a\u0430\u043d\u0430\u043b\u0435",
                    "\u0432 \u0433\u0440\u0443\u043f\u043f\u0435",
                    "\u0432",
                    "\u0434\u043b\u044f \u0447\u0430\u0442\u0430",
                    "\u0434\u043b\u044f \u043a\u0430\u043d\u0430\u043b\u0430",
                    "\u0434\u043b\u044f \u0433\u0440\u0443\u043f\u043f\u044b",
                    "\u0434\u043b\u044f",
                ),
            )
            target_ref = self._resolve_chat_target_reference_or_current(raw_target_ref, context)
            target = await self._build_chat_target(target_ref, context)
            return ActionRequest("unpin_message", normalized, context, target=target, summary=f"Unpin all messages in {target.label}")
        if not any(marker in lowered for marker in pin_markers):
            return None
        action_name = "unpin_message" if any(marker in lowered for marker in unpin_markers) else "pin_message"
        message_id = context.reply_to_message_id or self._extract_message_id(normalized)
        target = await self._build_chat_target(None, context)
        if action_name == "unpin_message" and message_id is None:
            return ActionRequest(action_name, normalized, context, target=target, summary=f"Unpin all messages in {target.label}")
        if message_id is None:
            return None
        target.message_id = message_id
        return ActionRequest(action_name, normalized, context, target=target, summary=f"{'Unpin' if action_name == 'unpin_message' else 'Pin'} message #{message_id} in {target.label}")

    async def _route_direct_action(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        request = await self._parse_chat_photo_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_chat_permissions_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_member_restrictions_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_admin_management_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_invite_link_management_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_join_request_management_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_delete_dialog_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_create_channel_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_create_group_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_select_target_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_delete_own_recent_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_history_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_clear_chat_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send_media_group(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send_structured(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send_dice_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send_media(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send_to_linked_chat_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_reply_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_copy_with_caption_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_forward_or_copy_to_linked_chat_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_forward_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_delete_shortcuts(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_select_target(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_read_reply_context(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_chat_history(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_member_lookup_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_linked_chat_lookup_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_info_lookup(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_mark_read(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_archive(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_blocking(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_join_leave(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_ban(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_title_description(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_add_contact(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_delete_contact(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_update_contact(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_edit_reply_markup_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_delete(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_edit_media_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_edit_caption_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_edit(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_pin_v2(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_pin(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_reaction(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_reply(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_send(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_forward_or_copy(normalized, lowered, context)
        if request is not None:
            return request
        request = await self._parse_draft(normalized, lowered, context)
        if request is not None:
            return request
        return None

    async def _parse_delete_dialog_shortcuts(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        dialog_markers = (
            "удали полностью чат",
            "удали чат полностью",
            "удали этот чат полностью",
            "удали полностью этот чат",
            "удали весь чат",
            "удали диалог",
            "удали переписку полностью",
            "удали чат",
            "удали этот чат",
            "удали диалог",
            "удали переписку",
            "delete this chat",
            "delete chat",
            "remove this chat",
            "delete this chat fully",
            "delete chat completely",
            "delete dialog",
            "remove this chat entirely",
        )
        if not any(marker in lowered for marker in dialog_markers):
            return None

        # Check if user explicitly means current chat
        current_chat_markers = (
            "этот чат", "этого чата", "текущий чат", "текущего чата",
            "this chat", "current chat",
        )
        refers_to_current = any(m in lowered for m in current_chat_markers)

        target_ref = self._extract_target_after_preposition(
            normalized,
            ("в", "for", "из", "from", "chat", "dialog", "чате"),
        )

        # If nothing explicit extracted but user said "Ã‘ÂÃ‘â€šÃÂ¾Ã‘â€š Ã‘â€¡ÃÂ°Ã‘â€š" Ã¢â‚¬â€ use current chat, not session target
        if target_ref is None and refers_to_current:
            target = await self._build_chat_target(context.request_chat_id, context)
        else:
            target = await self._build_chat_target(target_ref, context)

        return ActionRequest(
            action_name="delete_dialog",
            raw_prompt=normalized,
            context=context,
            target=target,
            summary=f"Delete the whole dialog for {target.label}",
        )

    async def _parse_clear_chat_shortcuts(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        explicit_current_chat = {
            "clear all messages in this chat",
            "delete all messages in this chat",
            "\u043e\u0447\u0438\u0441\u0442\u0438 \u0432\u0441\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f \u0432 \u044d\u0442\u043e\u043c \u0447\u0430\u0442\u0435",
            "\u0443\u0434\u0430\u043b\u0438 \u0432\u0441\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f \u0432 \u044d\u0442\u043e\u043c \u0447\u0430\u0442\u0435",
        }
        if lowered in explicit_current_chat:
            target = await self._build_chat_target(None, context)
            return ActionRequest(
                action_name="clear_history",
                raw_prompt=normalized,
                context=context,
                target=target,
                arguments={"limit": 200},
                summary=f"Clear recent messages in {target.label}",
            )
        if not any(
            marker in lowered
            for marker in (
                "clear chat",
                "clear history",
                "delete all messages",
                "clear all messages",
                "\u043e\u0447\u0438\u0441\u0442\u0438 \u0447\u0430\u0442",
                "\u043e\u0447\u0438\u0441\u0442\u0438 \u0438\u0441\u0442\u043e\u0440\u0438\u044e",
                "\u0443\u0434\u0430\u043b\u0438 \u0432\u0441\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f",
                "\u043e\u0447\u0438\u0441\u0442\u0438 \u0432\u0441\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f",
            )
        ):
            return None
        limit = 200 if any(marker in lowered for marker in ("all messages", "\u0432\u0441\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f")) else self._extract_count(normalized, default=50)
        target_ref = self._extract_target_after_preposition(
            normalized,
            ("to", "for", "from", "chat", "dialog", "channel", "\u0432", "\u0438\u0437", "\u0447\u0430\u0442\u0435", "\u0434\u0438\u0430\u043b\u043e\u0433\u0435", "\u043a\u0430\u043d\u0430\u043b\u0435"),
        )
        target = await self._build_chat_target(target_ref, context)
        return ActionRequest(
            action_name="clear_history",
            raw_prompt=normalized,
            context=context,
            target=target,
            arguments={"limit": limit},
            summary=f"Clear recent messages in {target.label}",
        )
    async def _parse_bulk_forward_shortcuts(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        """Parse 'ÃÂ¿ÃÂµÃ‘â‚¬ÃÂµÃ‘Ë†ÃÂ»ÃÂ¸/ÃÂ¿ÃÂµÃ‘â‚¬ÃÂµÃÂºÃÂ¸ÃÂ½Ã‘Å’/Ã‘ÂÃÂºÃÂ¾ÃÂ¿ÃÂ¸Ã‘â‚¬Ã‘Æ’ÃÂ¹ N Ã‘ÂÃÂ¾ÃÂ¾ÃÂ±Ã‘â€°ÃÂµÃÂ½ÃÂ¸ÃÂ¹ ÃÂ¸ÃÂ· X ÃÂ² Y' as cross_chat_request forward_last."""
        FORWARD_VERBS = ("ÃÂ¿ÃÂµÃ‘â‚¬ÃÂµÃ‘Ë†ÃÂ»ÃÂ¸", "ÃÂ¿ÃÂµÃ‘â‚¬ÃÂµÃÂºÃÂ¸ÃÂ½Ã‘Å’", "Ã‘ÂÃÂºÃÂ¾ÃÂ¿ÃÂ¸Ã‘â‚¬Ã‘Æ’ÃÂ¹", "Ã‘ÂÃÂºÃÂ¸ÃÂ½Ã‘Å’", "forward", "copy", "send last")
        if not any(v in lowered for v in FORWARD_VERBS):
            return None

        COUNT_RE_LOCAL = re.compile(r"(\d{1,4})\s*(?:Ã‘ÂÃÂ¾ÃÂ¾|Ã‘ÂÃÂ¾ÃÂ¾ÃÂ±Ã‘â€°\w*|msg\w*|message\w*)", re.IGNORECASE)
        count_match = COUNT_RE_LOCAL.search(normalized)
        if count_match is None:
            return None
        count = max(1, min(int(count_match.group(1)), 200))

        SAVED_ALIASES = {"ÃÂ¸ÃÂ·ÃÂ±Ã‘â‚¬ÃÂ°ÃÂ½ÃÂ½ÃÂ¾ÃÂµ", "saved", "saved messages", "me", "Ã‘ÂÃÂ¾Ã‘â€¦Ã‘â‚¬ÃÂ°ÃÂ½ÃÂµÃÂ½ÃÂ½Ã‘â€¹ÃÂµ", "Ã‘ÂÃÂ¾Ã‘â€¦Ã‘â‚¬ÃÂ°ÃÂ½Ã‘â€˜ÃÂ½ÃÂ½Ã‘â€¹ÃÂµ"}
        CURRENT_CHAT_ALIASES = {"ÃÂ¾Ã‘â€šÃ‘ÂÃ‘Å½ÃÂ´ÃÂ°", "ÃÂ¸ÃÂ· Ã‘ÂÃ‘â€šÃÂ¾ÃÂ³ÃÂ¾ Ã‘â€¡ÃÂ°Ã‘â€šÃÂ°", "Ã‘ÂÃ‘â€šÃÂ¾ÃÂ³ÃÂ¾ Ã‘â€¡ÃÂ°Ã‘â€šÃÂ°", "this chat", "here", "ÃÂ¸ÃÂ· Ã‘â€šÃÂµÃÂºÃ‘Æ’Ã‘â€°ÃÂµÃÂ³ÃÂ¾ Ã‘â€¡ÃÂ°Ã‘â€šÃÂ°"}

        source_reference: str | int = context.request_chat_id
        target_reference: str | int | None = None

        for alias in CURRENT_CHAT_ALIASES:
            if alias in lowered:
                source_reference = context.request_chat_id
                break

        for alias in SAVED_ALIASES:
            if alias in lowered:
                target_reference = "me"
                break

        if target_reference is None:
            target_ref_str = self._extract_target_after_preposition(normalized, ("ÃÂ²", "to", "ÃÂ² Ã‘â€¡ÃÂ°Ã‘â€š"))
            if target_ref_str:
                target_reference = target_ref_str

        if target_reference is None:
            return None

        source_target = await self._build_chat_target(source_reference, context)
        secondary_target = await self._build_chat_target(target_reference, context)

        return ActionRequest(
            action_name="cross_chat_request",
            raw_prompt=normalized,
            context=context,
            target=source_target,
            secondary_target=secondary_target,
            arguments={
                "subaction": "forward_last",
                "source_reference": source_reference,
                "target_reference": target_reference,
                "query": "",
                "message_limit": count,
                "within_hours": None,
                "prefix_text": None,
            },
            summary=f"Forward last {count} messages from {source_target.label} to {secondary_target.label}",
        )

    async def _parse_update_contact(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        if not any(m in lowered for m in (
            "измени имя контакта", "переименуй контакт", "rename contact",
            "смени имя контакта", "измени контакт", "update contact",
        )):
            return None

        new_name_match = re.search(r"(?iu)\b(?:на|в|to)\s+([^\n]+)$", normalized)
        if not new_name_match:
            return None
        new_name = self._strip_wrapping_quotes(new_name_match.group(1).strip())
        if not new_name:
            return None

        # Split into first/last name
        parts = new_name.split(None, 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

        old_ref_match = re.search(
            r"(?iu)(?:измени имя контакта|переименуй контакт|rename contact|смени имя контакта|измени контакт|update contact)\s+(.+?)\s+(?:на|в|to)\b",
            normalized,
        )
        old_ref = old_ref_match.group(1).strip() if old_ref_match else None
        target = await self._build_user_target(old_ref, context)

        return ActionRequest(
            action_name="update_contact",
            raw_prompt=normalized,
            context=context,
            target=target,
            arguments={"first_name": first_name, "last_name": last_name},
            summary=f"Rename contact {target.label} to {new_name}",
        )

    async def _parse_add_contact(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        """Parse add to contacts: 'добавь @user в контакты' / 'добавь контакт @user' / 'add @user to contacts'."""
        add_markers = (
            "добавь в контакты",
            "добавь контакт",
            "add to contacts",
            "add contact",
        )
        if not any(m in lowered for m in add_markers):
            return None

        # Extract reference (@username, user_id, or replied user)
        ref = None
        ref_match = re.search(r"(@[A-Za-z0-9_]{3,32}|-?\d{6,})", normalized)
        if ref_match:
            ref = ref_match.group(1)
        elif context.reply_to_user_id is not None:
            ref = str(context.reply_to_user_id)

        if not ref:
            return None

        target = await self._build_user_target(ref, context)

        # Optional name override: 'добавь @user в контакты как Имя Фамилия'
        name_match = re.search(r"(?iu)(?:как|as|имя|name)\s+([^\n]+)$", normalized)
        first_name = ""
        last_name = ""
        if name_match:
            parts = name_match.group(1).strip().split(None, 1)
            first_name = parts[0] if parts else ""
            last_name = parts[1] if len(parts) > 1 else ""

        return ActionRequest(
            action_name="add_contact",
            raw_prompt=normalized,
            context=context,
            target=target,
            arguments={"first_name": first_name, "last_name": last_name},
            summary=f"Add {target.label} to contacts",
        )

    async def _parse_delete_contact(self, normalized: str, lowered: str, context: ActionContext) -> ActionRequest | None:
        """Parse remove from contacts: 'удали из контактов @user' / 'удали контакт @user' / 'remove contact @user'."""
        delete_markers = (
            "удали из контактов",
            "удали контакт",
            "удалить из контактов",
            "удалить контакт",
            "убери из контактов",
            "убери контакт",
            "remove from contacts",
            "remove contact",
            "delete contact",
        )
        if not any(m in lowered for m in delete_markers):
            return None

        ref = None
        ref_match = re.search(r"(@[A-Za-z0-9_]{3,32}|-?\d{6,})", normalized)
        if ref_match:
            ref = ref_match.group(1)
        elif context.reply_to_user_id is not None:
            ref = str(context.reply_to_user_id)

        if not ref:
            return None

        target = await self._build_user_target(ref, context)

        return ActionRequest(
            action_name="delete_contact",
            raw_prompt=normalized,
            context=context,
            target=target,
            arguments={},
            summary=f"Remove {target.label} from contacts",
        )
