from __future__ import annotations

import logging

from .action_models import ActionResult, ActionStatus, ActionRequest
from .action_registry import ActionRegistry
from .cross_chat_actions import CrossChatActionService
from .tg_actions import TelegramActionService


LOGGER = logging.getLogger("assistant.actions")


class ActionExecutor:
    def __init__(
        self,
        registry: ActionRegistry,
        tg_actions: TelegramActionService,
        cross_chat_actions: CrossChatActionService | None = None,
    ) -> None:
        self._registry = registry
        self._tg_actions = tg_actions
        self._cross_chat_actions = cross_chat_actions

    def build_preview(self, request: ActionRequest) -> str:
        lines = [
            f"Action: {request.action_name}",
            f"Summary: {request.summary or 'No summary'}",
            f"Risk: {request.risk.value}",
        ]
        if request.target is not None:
            lines.append(f"Target: {request.target.label}")
        if request.secondary_target is not None:
            lines.append(f"Secondary target: {request.secondary_target.label}")
        if request.arguments:
            rendered_args = ", ".join(f"{key}={value}" for key, value in request.arguments.items() if value not in (None, "", [], {}))
            if rendered_args:
                lines.append(f"Args: {rendered_args}")
        if request.impact_summary:
            lines.append(f"Impact: {request.impact_summary}")
        return "\n".join(lines)

    def _invite_link_output(self, invite: object) -> dict[str, object]:
        return {
            "invite_link": getattr(invite, "invite_link", None) or getattr(invite, "link", None),
            "name": getattr(invite, "name", None),
            "creates_join_request": getattr(invite, "creates_join_request", None),
            "expire_date": getattr(invite, "expire_date", None),
            "member_limit": getattr(invite, "member_limit", None),
            "is_revoked": getattr(invite, "is_revoked", None),
            "is_primary": getattr(invite, "is_primary", None),
        }

    def _normalize_optional_username(self, value: object) -> str | None:
        text = "" if value is None else str(value).strip()
        if not text:
            return None
        text = text.lstrip("@").strip()
        if not text:
            return None
        if text.casefold() in {"none", "null", "no", "n/a", "na", "Ð½ÐµÑ‚"}:
            return None
        return text

    def _request_wants_created_chat_link(self, request: ActionRequest) -> bool:
        explicit = request.arguments.get("return_link")
        if isinstance(explicit, bool):
            return explicit
        text = " ".join(
            str(request.raw_prompt or request.context.raw_prompt or "").casefold().split()
        )
        if not text:
            return False
        return any(
            marker in text
            for marker in (
                "invite link",
                "chat invite",
                "send link",
                "share link",
                "drop link",
                "link to group",
                "link to channel",
                "\u0441\u0441\u044b\u043b",
                "\u0438\u043d\u0432\u0430\u0439\u0442",
                "\u043f\u0440\u0438\u0433\u043b\u0430\u0448\u0435\u043d",
            )
        )

    def _looks_like_raw_sticker_reference(self, value: str) -> bool:
        normalized = str(value or "").strip()
        if not normalized:
            return False
        lowered = normalized.casefold()
        if lowered.startswith(("http://", "https://", "file://", "tg://")):
            return True
        if any(sep in normalized for sep in ("\\", "/")):
            return True
        if lowered.endswith(
            (".webp", ".tgs", ".webm", ".png", ".jpg", ".jpeg", ".gif", ".mp4")
        ):
            return True
        if normalized.startswith(("CAA", "BQAC", "AgAC", "AwAC")):
            return True
        if len(normalized) >= 20 and all(ch.isalnum() or ch in "-_:" for ch in normalized):
            return True
        return False

    async def _build_created_chat_result(
        self,
        request: ActionRequest,
        *,
        noun: str,
        created_title: str,
        created_chat_id: int | None,
        requested_username: str | None,
        applied_username: str | None,
        wants_link: bool,
        username_error: str | None = None,
    ) -> ActionResult:
        link: str | None = None
        link_error: str | None = None
        if wants_link and created_chat_id is not None:
            if applied_username:
                link = f"https://t.me/{applied_username}"
            else:
                try:
                    link = await self._tg_actions.export_chat_invite_link(created_chat_id)
                except Exception as exc:
                    link_error = str(exc)

        output: dict[str, object] = {"chat_id": created_chat_id, "title": created_title}
        if applied_username:
            output["username"] = applied_username
        if link:
            output["invite_link"] = link

        message = f'Created {noun} "{created_title}"'
        if applied_username:
            message += f" with username @{applied_username}"
        if link:
            message += f". Link: {link}"
        else:
            message += "."

        issues: list[str] = []
        if requested_username and username_error:
            issues.append(f"could not set username @{requested_username}: {username_error}")
        if wants_link and not link:
            if link_error:
                issues.append(f"could not generate invite link: {link_error}")
            else:
                issues.append("could not generate invite link")
        if issues:
            message += " However, " + "; ".join(issues) + "."

        return ActionResult(
            request.action_name,
            ActionStatus.COMPLETED,
            message,
            output=output,
        )

    def _format_member_identity(self, member: dict[str, object]) -> str:
        display_name = str(member.get("display_name") or "unknown member").strip()
        username = str(member.get("username") or "").strip()
        user_id = member.get("user_id")
        extras: list[str] = []
        if username:
            extras.append(f"@{username}")
        if user_id not in (None, ""):
            extras.append(f"id={user_id}")
        if extras:
            return f"{display_name} ({', '.join(extras)})"
        return display_name

    def _format_enabled_flags(self, values: object) -> str | None:
        if not isinstance(values, dict):
            return None
        enabled = [str(key) for key, flag in values.items() if flag]
        if not enabled:
            return None
        return ", ".join(enabled)

    def _format_member_line(self, member: dict[str, object]) -> str:
        parts = [self._format_member_identity(member)]
        status = str(member.get("status") or "").strip()
        if status:
            parts.append(f"status={status}")
        custom_title = str(member.get("custom_title") or "").strip()
        if custom_title:
            parts.append(f"title={custom_title}")
        privileges = self._format_enabled_flags(member.get("privileges"))
        if privileges:
            parts.append(f"privileges={privileges}")
        permissions = self._format_enabled_flags(member.get("permissions"))
        if permissions:
            parts.append(f"permissions={permissions}")
        until_date = str(member.get("until_date") or "").strip()
        if until_date:
            parts.append(f"until={until_date}")
        return " - ".join(parts)

    def _format_user_brief(self, user: object) -> str | None:
        if not isinstance(user, dict):
            return None
        display_name = str(user.get("display_name") or "").strip()
        username = str(user.get("username") or "").strip()
        user_id = user.get("user_id")
        extras: list[str] = []
        if username:
            extras.append(f"@{username}")
        if user_id not in (None, ""):
            extras.append(f"id={user_id}")
        if not display_name and not extras:
            return None
        if extras:
            return f"{display_name or 'user'} ({', '.join(extras)})"
        return display_name or "user"

    async def execute(
        self,
        request: ActionRequest,
        *,
        style_instruction: str = "",
        response_mode: str = "ai_prefixed",
        response_style_mode: str = "NORMAL",
        excluded_message_ids: set[int] | None = None,
    ) -> ActionResult:
        definition = self._registry.require(request.action_name)
        if not definition.supported:
            return ActionResult(
                action_name=request.action_name,
                status=ActionStatus.FAILED,
                message=f"Action {request.action_name} is registered but not supported in this build.",
                error="unsupported",
            )
        handler = getattr(self, f"_exec_{request.action_name}", None)
        if handler is None:
            return ActionResult(
                action_name=request.action_name,
                status=ActionStatus.FAILED,
                message=f"No executor handler for action {request.action_name}.",
                error="missing_handler",
            )
        try:
            return await handler(
                request,
                style_instruction=style_instruction,
                response_mode=response_mode,
                response_style_mode=response_style_mode,
                excluded_message_ids=excluded_message_ids or set(),
            )
        except Exception as exc:
            LOGGER.exception("action_execution_failed action=%s", request.action_name)
            return ActionResult(
                action_name=request.action_name,
                status=ActionStatus.FAILED,
                message=f"Action failed: {exc}",
                error=str(exc),
            )

    async def _exec_select_target(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        return ActionResult(
            action_name=request.action_name,
            status=ActionStatus.COMPLETED,
            message=f"Active target set to {target.label}." if target is not None else "Active target updated.",
        )

    async def _exec_read_reply_context(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None or target.message_id is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "No replied message target found.", error="missing_target")
        text = await self._tg_actions.get_message_text(target.chat_id or request.context.request_chat_id, target.message_id)
        return ActionResult(
            action_name=request.action_name,
            status=ActionStatus.COMPLETED,
            message=text or "The replied message has no readable text.",
        )

    async def _exec_generate_draft(self, request: ActionRequest, **_: object) -> ActionResult:
        return ActionResult(
            action_name=request.action_name,
            status=ActionStatus.COMPLETED,
            message=self.build_preview(request),
        )

    async def _exec_get_chat_history(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        history = await self._tg_actions.get_chat_history(
            target.lookup if target is not None else request.context.request_chat_id,
            limit=int(request.arguments.get("limit", 10) or 10),
            within_hours=request.arguments.get("within_hours"),
        )
        message = "\n".join(history) if history else "No readable history found."
        return ActionResult(request.action_name, ActionStatus.COMPLETED, message)

    async def _exec_get_chat_members(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing chat target.", error="missing_target")
        limit = int(request.arguments.get("limit", 20) or 20)
        query = str(request.arguments.get("query", "") or "").strip()
        filter_name = str(request.arguments.get("filter_name", "") or "").strip()
        members = await self._tg_actions.get_chat_members(
            target.lookup,
            query=query,
            limit=limit,
            filter_name=filter_name,
        )
        filter_label = str(request.arguments.get("filter_label", "members") or "members").strip()
        if not members:
            if query:
                return ActionResult(request.action_name, ActionStatus.COMPLETED, f'No {filter_label} found in {target.label} for "{query}".', output={"members": []})
            return ActionResult(request.action_name, ActionStatus.COMPLETED, f"No {filter_label} found in {target.label}.", output={"members": []})
        lines = [f"Found {len(members)} {filter_label} in {target.label}:"]
        for member in members:
            lines.append(f"- {self._format_member_line(member)}")
        return ActionResult(request.action_name, ActionStatus.COMPLETED, "\n".join(lines), output={"members": members})

    async def _exec_get_chat_member(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        chat_target = request.secondary_target
        if target is None or chat_target is None or target.lookup is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing member or chat target.", error="missing_target")
        member = await self._tg_actions.get_chat_member(chat_target.lookup, target.lookup)
        lines = [f"Member in {chat_target.label}: {self._format_member_line(member)}"]
        joined_date = str(member.get("joined_date") or "").strip()
        if joined_date:
            lines.append(f"Joined: {joined_date}")
        invited_by = self._format_user_brief(member.get("invited_by"))
        if invited_by:
            lines.append(f"Invited by: {invited_by}")
        promoted_by = self._format_user_brief(member.get("promoted_by"))
        if promoted_by:
            lines.append(f"Promoted by: {promoted_by}")
        restricted_by = self._format_user_brief(member.get("restricted_by"))
        if restricted_by:
            lines.append(f"Restricted by: {restricted_by}")
        is_member = member.get("is_member")
        if is_member is not None:
            lines.append(f"Is member now: {bool(is_member)}")
        can_be_edited = member.get("can_be_edited")
        if can_be_edited is not None:
            lines.append(f"Can be edited: {bool(can_be_edited)}")
        return ActionResult(request.action_name, ActionStatus.COMPLETED, "\n".join(lines), output=member)

    async def _exec_get_linked_chat_info(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing chat target.", error="missing_target")
        info = await self._tg_actions.get_linked_chat_info(target.lookup)
        source = info.get("source_chat") if isinstance(info, dict) else None
        linked = info.get("linked_chat") if isinstance(info, dict) else None
        source_label = target.label
        if isinstance(source, dict):
            source_title = str(source.get("title") or "").strip()
            source_username = str(source.get("username") or "").strip()
            if source_title:
                source_label = source_title
            if source_username:
                source_label = f"{source_label} (@{source_username})" if source_label else f"@{source_username}"
        if not isinstance(linked, dict) or not linked:
            return ActionResult(request.action_name, ActionStatus.COMPLETED, f"No linked discussion chat or linked channel found for {source_label}.", output=info if isinstance(info, dict) else {})
        linked_title = str(linked.get("title") or "").strip()
        linked_username = str(linked.get("username") or "").strip()
        linked_type = str(linked.get("type") or "chat").strip()
        linked_id = linked.get("id")
        lines = [f"Linked chat for {source_label}:"]
        if linked_title:
            lines.append(f"Title: {linked_title}")
        if linked_username:
            lines.append(f"Username: @{linked_username}")
        if linked_type:
            lines.append(f"Type: {linked_type}")
        if linked_id not in (None, ""):
            lines.append(f"ID: {linked_id}")
        linked_description = str(linked.get("description") or "").strip()
        if linked_description:
            lines.append(f"Description: {linked_description}")
        return ActionResult(request.action_name, ActionStatus.COMPLETED, "\n".join(lines), output=info if isinstance(info, dict) else {})

    async def _exec_get_post_comments(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        message_id = request.arguments.get("message_id")
        if target is None or message_id is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing source chat or post id.", error="missing_target")
        result = await self._tg_actions.get_post_comments(
            target.lookup,
            int(message_id),
            limit=int(request.arguments.get("limit", 5) or 5),
        )
        discussion_message = result.get("discussion_message") if isinstance(result, dict) else None
        if not isinstance(discussion_message, dict) or not discussion_message:
            return ActionResult(
                request.action_name,
                ActionStatus.COMPLETED,
                f"No discussion thread or comments found for post #{message_id} in {target.label}.",
                output=result if isinstance(result, dict) else {},
            )
        discussion_chat = result.get("discussion_chat") if isinstance(result, dict) else None
        discussion_label = ""
        if isinstance(discussion_chat, dict):
            discussion_title = str(discussion_chat.get("title") or "").strip()
            discussion_username = str(discussion_chat.get("username") or "").strip()
            discussion_label = discussion_title or (f"@{discussion_username}" if discussion_username else "")
        replies = result.get("replies") if isinstance(result, dict) else []
        replies_count = int(result.get("replies_count", 0) or 0) if isinstance(result, dict) else 0
        lines = [f"Comments for post #{message_id} in {target.label}:"]
        if discussion_label:
            lines.append(f"Discussion chat: {discussion_label}")
        lines.append(f"Total replies: {replies_count}")
        if not isinstance(replies, list) or not replies:
            lines.append("No comments yet.")
            return ActionResult(request.action_name, ActionStatus.COMPLETED, "\n".join(lines), output=result if isinstance(result, dict) else {})
        lines.append(f"Showing {len(replies)} comments:")
        for reply in replies:
            if not isinstance(reply, dict):
                continue
            author = str(reply.get("author_name") or reply.get("author_username") or "unknown").strip()
            date = str(reply.get("date") or "").strip()
            text = str(reply.get("text") or "").strip() or "[no readable text]"
            prefix = f"- {author}"
            if date:
                prefix += f" [{date}]"
            lines.append(f"{prefix}: {text}")
        return ActionResult(request.action_name, ActionStatus.COMPLETED, "\n".join(lines), output=result if isinstance(result, dict) else {})

    async def _resolve_linked_destination(
        self,
        source_chat_lookup: str | int,
        *,
        source_label: str,
    ) -> tuple[str | int | None, str, dict[str, object]]:
        info = await self._tg_actions.get_linked_chat_info(source_chat_lookup)
        linked = info.get("linked_chat") if isinstance(info, dict) else None
        if not isinstance(linked, dict) or not linked:
            return None, source_label, info if isinstance(info, dict) else {}
        linked_username = str(linked.get("username") or "").strip()
        linked_id = linked.get("id")
        linked_lookup: str | int | None = f"@{linked_username}" if linked_username else linked_id
        linked_title = str(linked.get("title") or "").strip()
        linked_label = linked_title or (f"@{linked_username}" if linked_username else (str(linked_id) if linked_id not in (None, "") else "linked chat"))
        return linked_lookup, linked_label, info if isinstance(info, dict) else {}

    async def _exec_get_chat_info(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        info = await self._tg_actions.get_chat_info(target.lookup if target is not None else request.context.request_chat_id)
        lines = [f"{key}: {value}" for key, value in info.items() if value not in (None, "", [], {})]
        return ActionResult(request.action_name, ActionStatus.COMPLETED, "\n".join(lines) or "No chat info available.", output=info)

    async def _exec_get_user_info(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None or target.user_id is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "No user target found.", error="missing_target")
        info = await self._tg_actions.get_user_info(target.user_id)
        lines = [f"{key}: {value}" for key, value in info.items() if value not in (None, "", [], {})]
        return ActionResult(request.action_name, ActionStatus.COMPLETED, "\n".join(lines) or "No user info available.", output=info)

    async def _exec_mark_read(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        await self._tg_actions.mark_read(target.lookup if target is not None else request.context.request_chat_id)
        label = target.label if target is not None else "current chat"
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Marked {label} as read.")

    async def _exec_archive_chat(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None or target.chat_id is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "No chat target found.", error="missing_target")
        await self._tg_actions.archive_chat(target.chat_id)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Archived {target.label}.")

    async def _exec_unarchive_chat(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None or target.chat_id is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "No chat target found.", error="missing_target")
        await self._tg_actions.unarchive_chat(target.chat_id)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Unarchived {target.label}.")

    async def _exec_send_message(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        text = str(request.arguments.get("text", "")).strip()
        if target is None or not text:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing send target or text.", error="missing_target_or_text")
        sent = await self._tg_actions.send_message(target.lookup, text)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Sent message to {target.label}.", output={"message_id": getattr(sent, 'id', None)})

    async def _exec_send_to_linked_chat(self, request: ActionRequest, **_: object) -> ActionResult:
        source_chat = request.target
        text = str(request.arguments.get("text", "")).strip()
        if source_chat is None or not text:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing source chat or text.", error="missing_target_or_text")
        linked_lookup, linked_label, info = await self._resolve_linked_destination(source_chat.lookup, source_label=source_chat.label)
        if linked_lookup in (None, ""):
            return ActionResult(
                request.action_name,
                ActionStatus.FAILED,
                f"No linked discussion chat or linked channel found for {source_chat.label}.",
                output=info,
                error="linked_chat_not_found",
            )
        sent = await self._tg_actions.send_message(linked_lookup, text)
        return ActionResult(
            request.action_name,
            ActionStatus.COMPLETED,
            f"Sent message to linked chat {linked_label} for {source_chat.label}.",
            output={"message_id": getattr(sent, "id", None), "linked_chat": info.get("linked_chat"), "source_chat": info.get("source_chat")},
        )

    async def _exec_comment_channel_post(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        message_id = request.arguments.get("message_id")
        text = str(request.arguments.get("text", "")).strip()
        if target is None or message_id is None or not text:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing source chat, post id, or comment text.", error="missing_target_or_text")
        try:
            result = await self._tg_actions.comment_channel_post(target.lookup, int(message_id), text)
        except ValueError as exc:
            return ActionResult(request.action_name, ActionStatus.FAILED, str(exc), error="discussion_not_found")
        discussion_chat = result.get("discussion_chat") if isinstance(result, dict) else None
        discussion_label = "linked discussion chat"
        if isinstance(discussion_chat, dict):
            discussion_title = str(discussion_chat.get("title") or "").strip()
            discussion_username = str(discussion_chat.get("username") or "").strip()
            discussion_label = discussion_title or (f"@{discussion_username}" if discussion_username else discussion_label)
        return ActionResult(
            request.action_name,
            ActionStatus.COMPLETED,
            f"Posted a comment under post #{message_id} in {target.label} via {discussion_label}.",
            output=result if isinstance(result, dict) else {},
        )

    async def _exec_send_photo(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        photo = str(request.arguments.get("photo", "")).strip()
        caption = str(request.arguments.get("caption", "")).strip() or None
        if target is None or not photo:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing send target or photo.", error="missing_target_or_photo")
        sent = await self._tg_actions.send_photo(target.lookup, photo, caption=caption)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Sent photo to {target.label}.", output={"message_id": getattr(sent, "id", None)})

    async def _exec_send_video(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        video = str(request.arguments.get("video", "")).strip()
        caption = str(request.arguments.get("caption", "")).strip() or None
        if target is None or not video:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing send target or video.", error="missing_target_or_video")
        sent = await self._tg_actions.send_video(target.lookup, video, caption=caption)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Sent video to {target.label}.", output={"message_id": getattr(sent, "id", None)})

    async def _exec_send_video_note(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        video_note = str(request.arguments.get("video_note", "")).strip()
        if target is None or not video_note:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing send target or video note.", error="missing_target_or_video_note")
        sent = await self._tg_actions.send_video_note(target.lookup, video_note)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Sent video note to {target.label}.", output={"message_id": getattr(sent, "id", None)})

    async def _exec_send_animation(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        animation = str(request.arguments.get("animation", "")).strip()
        caption = str(request.arguments.get("caption", "")).strip() or None
        if target is None or not animation:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing send target or animation.", error="missing_target_or_animation")
        sent = await self._tg_actions.send_animation(target.lookup, animation, caption=caption)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Sent animation to {target.label}.", output={"message_id": getattr(sent, "id", None)})

    async def _exec_send_document(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        document = str(request.arguments.get("document", "")).strip()
        caption = str(request.arguments.get("caption", "")).strip() or None
        if target is None or not document:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing send target or document.", error="missing_target_or_document")
        sent = await self._tg_actions.send_document(target.lookup, document, caption=caption)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Sent document to {target.label}.", output={"message_id": getattr(sent, "id", None)})

    async def _exec_send_audio(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        audio = str(request.arguments.get("audio", "")).strip()
        caption = str(request.arguments.get("caption", "")).strip() or None
        if target is None or not audio:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing send target or audio.", error="missing_target_or_audio")
        sent = await self._tg_actions.send_audio(target.lookup, audio, caption=caption)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Sent audio to {target.label}.", output={"message_id": getattr(sent, "id", None)})

    async def _exec_send_voice(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        voice = str(request.arguments.get("voice", "")).strip()
        caption = str(request.arguments.get("caption", "")).strip() or None
        if target is None or not voice:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing send target or voice.", error="missing_target_or_voice")
        sent = await self._tg_actions.send_voice(target.lookup, voice, caption=caption)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Sent voice message to {target.label}.", output={"message_id": getattr(sent, "id", None)})

    async def _exec_send_sticker(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        sticker = str(request.arguments.get("sticker", "")).strip()
        if target is None or not sticker:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing send target or sticker.", error="missing_target_or_sticker")
        if self._looks_like_raw_sticker_reference(sticker):
            sent = await self._tg_actions.send_sticker(target.lookup, sticker)
            return ActionResult(
                request.action_name,
                ActionStatus.COMPLETED,
                f"Sent sticker to {target.label}.",
                output={"message_id": getattr(sent, "id", None)},
            )
        sent, candidate = await self._tg_actions.send_sticker_by_query(target.lookup, sticker)
        if sent is None or candidate is None:
            return ActionResult(
                request.action_name,
                ActionStatus.FAILED,
                f'Could not find a suitable sticker for "{sticker}".',
                error="sticker_not_found",
            )
        return ActionResult(
            request.action_name,
            ActionStatus.COMPLETED,
            f'Sent a matching sticker to {target.label} for "{sticker}".',
            output={
                "message_id": getattr(sent, "id", None),
                "sticker_query": sticker,
                "sticker_candidate": candidate,
            },
        )

    async def _exec_send_media_group(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        items = request.arguments.get("items")
        caption = str(request.arguments.get("caption", "")).strip() or None
        if target is None or not isinstance(items, list) or not items:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing send target or media group items.", error="missing_target_or_media_group")
        sent = await self._tg_actions.send_media_group(target.lookup, items, caption=caption)
        message_ids = [getattr(message, "id", None) for message in sent if getattr(message, "id", None) is not None]
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Sent media group to {target.label}.", output={"message_ids": message_ids})

    async def _exec_send_contact(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        phone_number = str(request.arguments.get("phone_number", "")).strip()
        first_name = str(request.arguments.get("first_name", "")).strip()
        last_name = str(request.arguments.get("last_name", "")).strip() or None
        if target is None or not phone_number or not first_name:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing send target or contact fields.", error="missing_target_or_contact")
        sent = await self._tg_actions.send_contact(target.lookup, phone_number, first_name, last_name=last_name)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Sent contact to {target.label}.", output={"message_id": getattr(sent, "id", None)})

    async def _exec_send_location(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        latitude = request.arguments.get("latitude")
        longitude = request.arguments.get("longitude")
        if target is None or latitude is None or longitude is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing send target or coordinates.", error="missing_target_or_coordinates")
        sent = await self._tg_actions.send_location(target.lookup, float(latitude), float(longitude))
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Sent location to {target.label}.", output={"message_id": getattr(sent, "id", None)})

    async def _exec_send_venue(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        latitude = request.arguments.get("latitude")
        longitude = request.arguments.get("longitude")
        title = str(request.arguments.get("title", "")).strip()
        address = str(request.arguments.get("address", "")).strip()
        if target is None or latitude is None or longitude is None or not title or not address:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing send target or venue fields.", error="missing_target_or_venue")
        sent = await self._tg_actions.send_venue(target.lookup, float(latitude), float(longitude), title, address)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Sent venue to {target.label}.", output={"message_id": getattr(sent, "id", None)})

    async def _exec_send_poll(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        question = str(request.arguments.get("question", "")).strip()
        options = request.arguments.get("options")
        if target is None or not question or not isinstance(options, list) or len(options) < 2:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing send target or poll fields.", error="missing_target_or_poll")
        cleaned_options = [str(option).strip() for option in options if str(option).strip()]
        if len(cleaned_options) < 2:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Poll needs at least two options.", error="not_enough_poll_options")
        sent = await self._tg_actions.send_poll(
            target.lookup,
            question,
            cleaned_options,
        )
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Sent poll to {target.label}.", output={"message_id": getattr(sent, "id", None)})

    async def _exec_send_dice(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        emoji = str(request.arguments.get("emoji", "ðŸŽ²")).strip() or "ðŸŽ²"
        if target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing send target.", error="missing_target")
        sent = await self._tg_actions.send_dice(target.lookup, emoji=emoji)
        return ActionResult(
            request.action_name,
            ActionStatus.COMPLETED,
            f"Sent dice {emoji} to {target.label}.",
            output={"message_id": getattr(sent, "id", None), "emoji": emoji},
        )

    async def _exec_reply_to_message(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        text = str(request.arguments.get("text", "")).strip()
        if target is None or target.message_id is None or not text:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing reply target or text.", error="missing_target_or_text")
        sent = await self._tg_actions.send_message(target.chat_id or request.context.request_chat_id, text, reply_to_message_id=target.message_id)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Replied to message #{target.message_id}.", output={"message_id": getattr(sent, 'id', None)})

    async def _exec_edit_own_message(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        text = str(request.arguments.get("text", "")).strip()
        if target is None or target.message_id is None or not text:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing edit target or text.", error="missing_target_or_text")
        await self._tg_actions.edit_message(target.chat_id or request.context.request_chat_id, target.message_id, text)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Edited message #{target.message_id}.")

    async def _exec_edit_message_caption(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        caption = str(request.arguments.get("caption", "")).strip()
        if target is None or target.message_id is None or not caption:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing caption target or text.", error="missing_target_or_caption")
        await self._tg_actions.edit_message_caption(target.chat_id or request.context.request_chat_id, target.message_id, caption)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Edited caption of message #{target.message_id}.")

    async def _exec_edit_message_media(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        media_kind = str(request.arguments.get("media_kind", "")).strip()
        media = str(request.arguments.get("media", "")).strip()
        caption = str(request.arguments.get("caption", "")).strip() or None
        if target is None or target.message_id is None or not media_kind or not media:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing media edit target or replacement media.", error="missing_target_or_media")
        await self._tg_actions.edit_message_media(
            target.chat_id or request.context.request_chat_id,
            target.message_id,
            media_kind,
            media,
            caption=caption,
        )
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Replaced media in message #{target.message_id}.")

    async def _exec_edit_message_reply_markup(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None or target.message_id is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing reply markup target.", error="missing_target")
        buttons = request.arguments.get("buttons")
        normalized_buttons = buttons if isinstance(buttons, list) else None
        await self._tg_actions.edit_message_reply_markup(
            target.chat_id or request.context.request_chat_id,
            target.message_id,
            buttons=normalized_buttons,
        )
        if normalized_buttons:
            return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Updated inline buttons on message #{target.message_id}.")
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Cleared inline buttons on message #{target.message_id}.")

    async def _exec_delete_message(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None or target.message_id is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing delete target.", error="missing_target")
        await self._tg_actions.delete_messages(target.chat_id or request.context.request_chat_id, [target.message_id])
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Deleted message #{target.message_id}.")

    async def _exec_delete_multiple_messages(self, request: ActionRequest, *, excluded_message_ids: set[int], **_: object) -> ActionResult:
        target = request.target
        if target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing delete target.", error="missing_target")
        message_ids = [int(value) for value in request.arguments.get("message_ids", []) if int(value) not in excluded_message_ids]
        if not message_ids and request.arguments.get("mode") == "recent":
            filter_user_id = request.arguments.get("filter_user_id")
            if filter_user_id is not None:
                filter_user_id = int(filter_user_id)
            deleted = await self._tg_actions.clear_history(
                target.lookup,
                limit=int(request.arguments.get("limit", 5) or 5),
                exclude_message_ids=excluded_message_ids,
                filter_user_id=filter_user_id,
            )
            who = f" from user {filter_user_id}" if filter_user_id else ""
            return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Deleted {deleted} recent messages{who} in {target.label}.")
        if not message_ids:
            return ActionResult(request.action_name, ActionStatus.FAILED, "No message ids to delete after exclusions.", error="empty_target")
        await self._tg_actions.delete_messages(target.lookup, message_ids)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Deleted {len(message_ids)} messages in {target.label}.")

    async def _exec_forward_message(self, request: ActionRequest, **_: object) -> ActionResult:
        source = request.target
        destination = request.secondary_target
        if source is None or source.message_id is None or destination is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing forward source or target.", error="missing_target")
        await self._tg_actions.forward_messages(destination.lookup, source.chat_id or request.context.request_chat_id, [source.message_id])
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Forwarded message #{source.message_id} to {destination.label}.")

    async def _exec_forward_to_linked_chat(self, request: ActionRequest, **_: object) -> ActionResult:
        source = request.target
        source_chat = request.secondary_target
        if source is None or source.message_id is None or source_chat is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing forward source or linked-chat source.", error="missing_target")
        linked_lookup, linked_label, info = await self._resolve_linked_destination(source_chat.lookup, source_label=source_chat.label)
        if linked_lookup in (None, ""):
            return ActionResult(
                request.action_name,
                ActionStatus.FAILED,
                f"No linked discussion chat or linked channel found for {source_chat.label}.",
                output=info,
                error="linked_chat_not_found",
            )
        await self._tg_actions.forward_messages(linked_lookup, source.chat_id or request.context.request_chat_id, [source.message_id])
        return ActionResult(
            request.action_name,
            ActionStatus.COMPLETED,
            f"Forwarded message #{source.message_id} to linked chat {linked_label} for {source_chat.label}.",
            output={"linked_chat": info.get("linked_chat"), "source_chat": info.get("source_chat")},
        )

    async def _exec_copy_message(self, request: ActionRequest, **_: object) -> ActionResult:
        source = request.target
        destination = request.secondary_target
        if source is None or source.message_id is None or destination is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing copy source or target.", error="missing_target")
        caption = str(request.arguments.get("caption", "")).strip() or None
        await self._tg_actions.copy_message(
            destination.lookup,
            source.chat_id or request.context.request_chat_id,
            source.message_id,
            caption=caption,
        )
        if caption:
            return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Copied message #{source.message_id} to {destination.label} with a new caption.")
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Copied message #{source.message_id} to {destination.label}.")

    async def _exec_copy_to_linked_chat(self, request: ActionRequest, **_: object) -> ActionResult:
        source = request.target
        source_chat = request.secondary_target
        if source is None or source.message_id is None or source_chat is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing copy source or linked-chat source.", error="missing_target")
        linked_lookup, linked_label, info = await self._resolve_linked_destination(source_chat.lookup, source_label=source_chat.label)
        if linked_lookup in (None, ""):
            return ActionResult(
                request.action_name,
                ActionStatus.FAILED,
                f"No linked discussion chat or linked channel found for {source_chat.label}.",
                output=info,
                error="linked_chat_not_found",
            )
        await self._tg_actions.copy_message(linked_lookup, source.chat_id or request.context.request_chat_id, source.message_id)
        return ActionResult(
            request.action_name,
            ActionStatus.COMPLETED,
            f"Copied message #{source.message_id} to linked chat {linked_label} for {source_chat.label}.",
            output={"linked_chat": info.get("linked_chat"), "source_chat": info.get("source_chat")},
        )

    async def _exec_send_reaction(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        emoji = str(request.arguments.get("emoji", "ðŸ‘")).strip()
        if target is None or target.message_id is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing reaction target.", error="missing_target")
        await self._tg_actions.send_reaction(target.chat_id or request.context.request_chat_id, target.message_id, emoji)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Reacted to message #{target.message_id} with {emoji}.")

    async def _exec_pin_message(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None or target.message_id is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing pin target.", error="missing_target")
        await self._tg_actions.pin_message(target.chat_id or request.context.request_chat_id, target.message_id)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Pinned message #{target.message_id}.")

    async def _exec_unpin_message(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing unpin target.", error="missing_target")
        await self._tg_actions.unpin_message(target.lookup, target.message_id)
        if target.message_id is None:
            return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Unpinned all messages in {target.label}.")
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Unpinned message #{target.message_id}.")

    async def _exec_block_user(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None or target.user_id is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing block target.", error="missing_target")
        await self._tg_actions.block_user(target.user_id)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Blocked {target.label}.")

    async def _exec_unblock_user(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None or target.user_id is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing unblock target.", error="missing_target")
        await self._tg_actions.unblock_user(target.user_id)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Unblocked {target.label}.")

    async def _exec_join_chat(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing join target.", error="missing_target")
        await self._tg_actions.join_chat(target.lookup)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Joined {target.label}.")

    async def _exec_leave_chat(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing leave target.", error="missing_target")
        await self._tg_actions.leave_chat(target.lookup)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Left {target.label}.")

    async def _exec_create_group(self, request: ActionRequest, **_: object) -> ActionResult:
        title = str(request.arguments.get("title", "")).strip()
        description = str(request.arguments.get("description", "")).strip()
        requested_username = self._normalize_optional_username(
            request.arguments.get("username")
        )
        wants_link = self._request_wants_created_chat_link(request)
        if not title:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing group title.", error="missing_title")
        chat = await self._tg_actions.create_supergroup(title, description=description)
        created_chat_id = getattr(chat, "id", None)
        created_title = getattr(chat, "title", None) or title
        applied_username: str | None = None
        username_error: str | None = None
        if requested_username and created_chat_id is not None:
            try:
                await self._tg_actions.set_chat_username(created_chat_id, requested_username)
                applied_username = requested_username
            except Exception as exc:
                username_error = str(exc)
        return await self._build_created_chat_result(
            request,
            noun="group",
            created_title=created_title,
            created_chat_id=created_chat_id,
            requested_username=requested_username,
            applied_username=applied_username,
            wants_link=wants_link,
            username_error=username_error,
        )

    async def _exec_create_channel(self, request: ActionRequest, **_: object) -> ActionResult:
        title = str(request.arguments.get("title", "")).strip()
        description = str(request.arguments.get("description", "")).strip()
        requested_username = self._normalize_optional_username(
            request.arguments.get("username")
        )
        wants_link = self._request_wants_created_chat_link(request)
        if not title:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing channel title.", error="missing_title")
        chat = await self._tg_actions.create_channel(title, description=description)
        created_chat_id = getattr(chat, "id", None)
        created_title = getattr(chat, "title", None) or title
        applied_username: str | None = None
        username_error: str | None = None
        if requested_username and created_chat_id is not None:
            try:
                await self._tg_actions.set_chat_username(
                    created_chat_id, requested_username
                )
                applied_username = requested_username
            except Exception as exc:
                username_error = str(exc)
        return await self._build_created_chat_result(
            request,
            noun="channel",
            created_title=created_title,
            created_chat_id=created_chat_id,
            requested_username=requested_username,
            applied_username=applied_username,
            wants_link=wants_link,
            username_error=username_error,
        )

    async def _exec_ban_user(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        chat_target = request.secondary_target
        if target is None or target.user_id is None or chat_target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing ban target.", error="missing_target")
        await self._tg_actions.ban_chat_member(chat_target.lookup, target.user_id)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Banned {target.label} in {chat_target.label}.")

    async def _exec_unban_user(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        chat_target = request.secondary_target
        if target is None or target.user_id is None or chat_target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing unban target.", error="missing_target")
        await self._tg_actions.unban_chat_member(chat_target.lookup, target.user_id)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Unbanned {target.label} in {chat_target.label}.")

    async def _exec_export_chat_invite_link(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing invite-link target chat.", error="missing_target")
        invite_link = await self._tg_actions.export_chat_invite_link(target.lookup)
        return ActionResult(
            request.action_name,
            ActionStatus.COMPLETED,
            f"Exported primary invite link for {target.label}: {invite_link}",
            output={"invite_link": invite_link},
        )

    async def _exec_create_chat_invite_link(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing invite-link target chat.", error="missing_target")
        invite = await self._tg_actions.create_chat_invite_link(
            target.lookup,
            name=request.arguments.get("name"),
            expire_date=request.arguments.get("expire_date"),
            member_limit=request.arguments.get("member_limit"),
            creates_join_request=request.arguments.get("creates_join_request"),
        )
        output = self._invite_link_output(invite)
        invite_link = output.get("invite_link") or "invite link"
        return ActionResult(
            request.action_name,
            ActionStatus.COMPLETED,
            f"Created invite link for {target.label}: {invite_link}",
            output=output,
        )

    async def _exec_edit_chat_invite_link(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        invite_link = str(request.arguments.get("invite_link", "")).strip()
        if target is None or not invite_link:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing target chat or invite link.", error="missing_target_or_link")
        invite = await self._tg_actions.edit_chat_invite_link(
            target.lookup,
            invite_link,
            name=request.arguments.get("name"),
            expire_date=request.arguments.get("expire_date"),
            member_limit=request.arguments.get("member_limit"),
            creates_join_request=request.arguments.get("creates_join_request"),
        )
        output = self._invite_link_output(invite)
        result_link = output.get("invite_link") or invite_link
        return ActionResult(
            request.action_name,
            ActionStatus.COMPLETED,
            f"Edited invite link for {target.label}: {result_link}",
            output=output,
        )

    async def _exec_revoke_chat_invite_link(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        invite_link = str(request.arguments.get("invite_link", "")).strip()
        if target is None or not invite_link:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing target chat or invite link.", error="missing_target_or_link")
        invite = await self._tg_actions.revoke_chat_invite_link(target.lookup, invite_link)
        output = self._invite_link_output(invite)
        result_link = output.get("invite_link") or invite_link
        return ActionResult(
            request.action_name,
            ActionStatus.COMPLETED,
            f"Revoked invite link for {target.label}: {result_link}",
            output=output,
        )

    async def _exec_approve_chat_join_request(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        chat_target = request.secondary_target
        if target is None or target.user_id is None or chat_target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing join-request user or chat target.", error="missing_target")
        await self._tg_actions.approve_chat_join_request(chat_target.lookup, target.user_id)
        return ActionResult(
            request.action_name,
            ActionStatus.COMPLETED,
            f"Approved join request for {target.label} in {chat_target.label}.",
        )

    async def _exec_decline_chat_join_request(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        chat_target = request.secondary_target
        if target is None or target.user_id is None or chat_target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing join-request user or chat target.", error="missing_target")
        await self._tg_actions.decline_chat_join_request(chat_target.lookup, target.user_id)
        return ActionResult(
            request.action_name,
            ActionStatus.COMPLETED,
            f"Declined join request for {target.label} in {chat_target.label}.",
        )

    async def _exec_set_chat_permissions(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        permissions = request.arguments.get("permissions")
        if target is None or not isinstance(permissions, dict):
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing chat target or permissions preset.", error="missing_target_or_permissions")
        await self._tg_actions.set_chat_permissions(target.lookup, permissions)
        preset_label = str(request.arguments.get("preset_label", "updated permissions")).strip()
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Set default permissions for {target.label} to {preset_label}.")

    async def _exec_restrict_chat_member(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        chat_target = request.secondary_target
        permissions = request.arguments.get("permissions")
        if target is None or target.user_id is None or chat_target is None or not isinstance(permissions, dict):
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing restrict target, chat, or permissions preset.", error="missing_target")
        await self._tg_actions.restrict_chat_member(chat_target.lookup, target.user_id, permissions)
        preset_label = str(request.arguments.get("preset_label", "restricted")).strip()
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Restricted {target.label} in {chat_target.label} to {preset_label}.")

    async def _exec_unrestrict_chat_member(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        chat_target = request.secondary_target
        if target is None or target.user_id is None or chat_target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing unrestrict target or chat.", error="missing_target")
        await self._tg_actions.unrestrict_chat_member(chat_target.lookup, target.user_id)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Lifted restrictions for {target.label} in {chat_target.label}.")

    async def _exec_promote_chat_member(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        chat_target = request.secondary_target
        privileges = request.arguments.get("privileges")
        if target is None or target.user_id is None or chat_target is None or not isinstance(privileges, dict):
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing promote target, chat, or privileges preset.", error="missing_target")
        await self._tg_actions.promote_chat_member(chat_target.lookup, target.user_id, privileges)
        preset_label = str(request.arguments.get("preset_label", "basic admin")).strip()
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Promoted {target.label} in {chat_target.label} as {preset_label}.")

    async def _exec_demote_chat_member(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        chat_target = request.secondary_target
        if target is None or target.user_id is None or chat_target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing demote target or chat.", error="missing_target")
        await self._tg_actions.demote_chat_member(chat_target.lookup, target.user_id)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Removed admin rights from {target.label} in {chat_target.label}.")

    async def _exec_set_administrator_title(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        chat_target = request.secondary_target
        title = str(request.arguments.get("title", ""))
        if target is None or target.user_id is None or chat_target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing admin title target or chat.", error="missing_target")
        await self._tg_actions.set_administrator_title(chat_target.lookup, target.user_id, title)
        if title.strip():
            return ActionResult(request.action_name, ActionStatus.COMPLETED, f'Set administrator title for {target.label} in {chat_target.label} to "{title.strip()}".')
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Cleared administrator title for {target.label} in {chat_target.label}.")

    async def _exec_set_chat_title(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        title = str(request.arguments.get("title", "")).strip()
        if target is None or not title:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing title target or text.", error="missing_target_or_text")
        await self._tg_actions.set_chat_title(target.lookup, title)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Changed title of {target.label}.")

    async def _exec_set_chat_description(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        description = str(request.arguments.get("description", "")).strip()
        if target is None or not description:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing description target or text.", error="missing_target_or_text")
        await self._tg_actions.set_chat_description(target.lookup, description)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Changed description of {target.label}.")

    async def _exec_set_chat_photo(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        photo = str(request.arguments.get("photo", "")).strip() or None
        video = str(request.arguments.get("video", "")).strip() or None
        if target is None or (photo is None and video is None):
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing chat target or photo/video source.", error="missing_target_or_photo")
        await self._tg_actions.set_chat_photo(target.lookup, photo=photo, video=video)
        media_label = "video avatar" if video is not None else "photo"
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Changed chat {media_label} for {target.label}.")

    async def _exec_delete_chat_photo(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing chat target.", error="missing_target")
        await self._tg_actions.delete_chat_photo(target.lookup)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Deleted chat photo for {target.label}.")

    async def _exec_update_contact(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        first_name = str(request.arguments.get("first_name", "")).strip()
        last_name = str(request.arguments.get("last_name", "")).strip()
        if target is None or target.user_id is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Need user_id to update contact.", error="missing_target")
        if not first_name:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Need at least a first name.", error="missing_name")
        await self._tg_actions.update_contact(target.user_id, first_name=first_name, last_name=last_name)
        full = f"{first_name} {last_name}".strip()
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Contact updated: {target.label} â†’ {full}.")

    async def _exec_add_contact(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None or target.user_id is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Need user_id to add contact.", error="missing_target")
        first_name = str(request.arguments.get("first_name", "")).strip()
        last_name = str(request.arguments.get("last_name", "")).strip()
        if not first_name:
            try:
                user = await self._tg_actions._client.get_users(target.user_id)
                first_name = getattr(user, "first_name", "") or ""
                last_name = getattr(user, "last_name", "") or ""
            except Exception:
                first_name = target.label or str(target.user_id)
                last_name = ""
        if not first_name:
            first_name = str(target.user_id)
        await self._tg_actions.update_contact(target.user_id, first_name=first_name, last_name=last_name)
        full = f"{first_name} {last_name}".strip()
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Added to contacts: {full}.")

    async def _exec_delete_contact(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None or target.user_id is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Need user_id to delete contact.", error="missing_target")
        label = target.label or str(target.user_id)
        await self._tg_actions.delete_contact(target.user_id)
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Removed from contacts: {label}.")

    async def _exec_clear_history(self, request: ActionRequest, *, excluded_message_ids: set[int], **_: object) -> ActionResult:
        target = request.target
        if target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing history target.", error="missing_target")
        deleted = await self._tg_actions.clear_history(
            target.lookup,
            limit=int(request.arguments.get("limit", 30) or 30),
            exclude_message_ids=excluded_message_ids,
        )
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Deleted {deleted} recent messages in {target.label}.")

    async def _exec_delete_dialog(self, request: ActionRequest, **_: object) -> ActionResult:
        target = request.target
        if target is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Missing dialog target.", error="missing_target")
        details = await self._tg_actions.delete_dialog(target.lookup)
        mode = str(details.get("mode", "")).strip()
        if mode == "leave_channel":
            return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Left and removed {target.label} from your dialogs.")
        if mode == "leave_chat_delete":
            return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Left and deleted the dialog for {target.label}.")
        return ActionResult(request.action_name, ActionStatus.COMPLETED, f"Deleted the dialog history for {target.label}.")

    async def _exec_cross_chat_request(
        self,
        request: ActionRequest,
        *,
        style_instruction: str,
        response_mode: str,
        response_style_mode: str,
        excluded_message_ids: set[int],
    ) -> ActionResult:
        if self._cross_chat_actions is None:
            return ActionResult(request.action_name, ActionStatus.FAILED, "Cross-chat service is unavailable.", error="missing_service")
        reply_message = None
        reply_to_message_id = request.context.reply_to_message_id
        if reply_to_message_id is not None:
            try:
                reply_message = await self._tg_actions.get_message(
                    request.context.request_chat_id,
                    reply_to_message_id,
                )
            except Exception:
                reply_message = None
        text = await self._cross_chat_actions.maybe_execute(
            prompt=request.raw_prompt,
            current_chat_id=request.context.request_chat_id,
            excluded_message_ids=excluded_message_ids,
            reply_message=reply_message,
            style_instruction=style_instruction,
            response_mode=response_mode,
            response_style_mode=response_style_mode,
        )
        return ActionResult(
            action_name=request.action_name,
            status=ActionStatus.COMPLETED if text is not None else ActionStatus.FAILED,
            message=text or "Cross-chat action did not return a result.",
            error=None if text is not None else "no_result",
        )

