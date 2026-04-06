from __future__ import annotations

from .action_models import ActionDefinition, ActionRisk

ACTION_CATEGORY_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Messaging and media",
        (
            "send_message",
            "send_to_linked_chat",
            "comment_channel_post",
            "send_photo",
            "send_video",
            "send_video_note",
            "send_animation",
            "send_document",
            "send_audio",
            "send_voice",
            "send_sticker",
            "send_media_group",
            "send_contact",
            "send_location",
            "send_venue",
            "send_poll",
            "send_dice",
            "reply_to_message",
            "send_reaction",
        ),
    ),
    (
        "Editing and cleanup",
        (
            "edit_own_message",
            "edit_message_caption",
            "edit_message_media",
            "edit_message_reply_markup",
            "delete_message",
            "delete_multiple_messages",
            "clear_history",
            "delete_dialog",
        ),
    ),
    (
        "Forwarding and copying",
        (
            "forward_message",
            "forward_to_linked_chat",
            "copy_message",
            "copy_to_linked_chat",
        ),
    ),
    (
        "Reading and inspection",
        (
            "get_chat_history",
            "get_chat_members",
            "get_chat_member",
            "get_linked_chat_info",
            "get_post_comments",
            "get_chat_info",
            "get_user_info",
            "read_reply_context",
        ),
    ),
    (
        "Chat state and navigation",
        (
            "mark_read",
            "pin_message",
            "unpin_message",
            "archive_chat",
            "unarchive_chat",
            "join_chat",
            "leave_chat",
            "select_target",
        ),
    ),
    (
        "Invites and join requests",
        (
            "export_chat_invite_link",
            "create_chat_invite_link",
            "edit_chat_invite_link",
            "revoke_chat_invite_link",
            "approve_chat_join_request",
            "decline_chat_join_request",
        ),
    ),
    (
        "Creation and setup",
        (
            "create_group",
            "create_channel",
            "set_chat_title",
            "set_chat_description",
            "set_chat_photo",
            "delete_chat_photo",
            "set_chat_permissions",
        ),
    ),
    (
        "Members and admin control",
        (
            "block_user",
            "unblock_user",
            "ban_user",
            "unban_user",
            "restrict_chat_member",
            "unrestrict_chat_member",
            "promote_chat_member",
            "demote_chat_member",
            "set_administrator_title",
        ),
    ),
    (
        "Contacts and helper actions",
        (
            "update_contact",
            "add_contact",
            "delete_contact",
            "generate_draft",
            "cross_chat_request",
        ),
    ),
)


class ActionRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ActionDefinition] = {
            "send_message": ActionDefinition("send_message", "Send Message", "Send a message to a resolved chat or user.", ActionRisk.SENSITIVE),
            "send_to_linked_chat": ActionDefinition("send_to_linked_chat", "Send To Linked Chat", "Send a text message to the linked discussion chat or linked channel of a source chat.", ActionRisk.SENSITIVE),
            "comment_channel_post": ActionDefinition("comment_channel_post", "Comment Channel Post", "Leave a comment under a channel post via its linked discussion thread.", ActionRisk.SENSITIVE),
            "send_photo": ActionDefinition("send_photo", "Send Photo", "Send a photo to a resolved chat or user.", ActionRisk.SENSITIVE),
            "send_video": ActionDefinition("send_video", "Send Video", "Send a video to a resolved chat or user.", ActionRisk.SENSITIVE),
            "send_video_note": ActionDefinition("send_video_note", "Send Video Note", "Send a video note to a resolved chat or user.", ActionRisk.SENSITIVE),
            "send_animation": ActionDefinition("send_animation", "Send Animation", "Send an animation or GIF to a resolved chat or user.", ActionRisk.SENSITIVE),
            "send_document": ActionDefinition("send_document", "Send Document", "Send a document to a resolved chat or user.", ActionRisk.SENSITIVE),
            "send_audio": ActionDefinition("send_audio", "Send Audio", "Send an audio file to a resolved chat or user.", ActionRisk.SENSITIVE),
            "send_voice": ActionDefinition("send_voice", "Send Voice", "Send a voice message to a resolved chat or user.", ActionRisk.SENSITIVE),
            "send_sticker": ActionDefinition("send_sticker", "Send Sticker", "Send a sticker to a resolved chat or user.", ActionRisk.SENSITIVE),
            "send_media_group": ActionDefinition("send_media_group", "Send Media Group", "Send an album or media group to a resolved chat or user.", ActionRisk.SENSITIVE),
            "send_contact": ActionDefinition("send_contact", "Send Contact", "Send a contact card to a resolved chat or user.", ActionRisk.SENSITIVE),
            "send_location": ActionDefinition("send_location", "Send Location", "Send a location to a resolved chat or user.", ActionRisk.SENSITIVE),
            "send_venue": ActionDefinition("send_venue", "Send Venue", "Send a venue to a resolved chat or user.", ActionRisk.SENSITIVE),
            "send_poll": ActionDefinition("send_poll", "Send Poll", "Send a poll to a resolved chat or user.", ActionRisk.SENSITIVE),
            "send_dice": ActionDefinition("send_dice", "Send Dice", "Send a Telegram dice or game emoji to a resolved chat or user.", ActionRisk.SENSITIVE),
            "reply_to_message": ActionDefinition("reply_to_message", "Reply To Message", "Reply to a specific message.", ActionRisk.SENSITIVE),
            "edit_own_message": ActionDefinition("edit_own_message", "Edit Own Message", "Edit one of the owner's messages.", ActionRisk.SENSITIVE),
            "edit_message_caption": ActionDefinition("edit_message_caption", "Edit Message Caption", "Edit the caption of a media message.", ActionRisk.SENSITIVE),
            "edit_message_media": ActionDefinition("edit_message_media", "Edit Message Media", "Replace the media content of an existing message.", ActionRisk.SENSITIVE),
            "edit_message_reply_markup": ActionDefinition("edit_message_reply_markup", "Edit Message Reply Markup", "Edit or clear inline buttons on an existing message.", ActionRisk.SENSITIVE),
            "delete_message": ActionDefinition("delete_message", "Delete Message", "Delete a single message.", ActionRisk.DESTRUCTIVE),
            "delete_multiple_messages": ActionDefinition("delete_multiple_messages", "Delete Multiple Messages", "Delete several messages.", ActionRisk.DESTRUCTIVE),
            "forward_message": ActionDefinition("forward_message", "Forward Message", "Forward one or more messages.", ActionRisk.SENSITIVE),
            "forward_to_linked_chat": ActionDefinition("forward_to_linked_chat", "Forward To Linked Chat", "Forward one message to the linked discussion chat or linked channel of a source chat.", ActionRisk.SENSITIVE),
            "copy_message": ActionDefinition("copy_message", "Copy Message", "Copy one message to another chat.", ActionRisk.SENSITIVE),
            "copy_to_linked_chat": ActionDefinition("copy_to_linked_chat", "Copy To Linked Chat", "Copy one message to the linked discussion chat or linked channel of a source chat.", ActionRisk.SENSITIVE),
            "send_reaction": ActionDefinition("send_reaction", "Send Reaction", "Send a reaction to a message.", ActionRisk.SENSITIVE),
            "mark_read": ActionDefinition("mark_read", "Mark Read", "Mark a chat as read.", ActionRisk.SAFE),
            "pin_message": ActionDefinition("pin_message", "Pin Message", "Pin a message in a chat.", ActionRisk.SENSITIVE),
            "unpin_message": ActionDefinition("unpin_message", "Unpin Message", "Unpin one message or all messages.", ActionRisk.SENSITIVE),
            "archive_chat": ActionDefinition("archive_chat", "Archive Chat", "Archive a chat.", ActionRisk.SENSITIVE),
            "unarchive_chat": ActionDefinition("unarchive_chat", "Unarchive Chat", "Unarchive a chat.", ActionRisk.SENSITIVE),
            "clear_history": ActionDefinition("clear_history", "Clear History", "Delete recent accessible messages from a chat.", ActionRisk.DESTRUCTIVE),
            "delete_dialog": ActionDefinition("delete_dialog", "Delete Dialog", "Delete or remove the whole dialog from the owner's account where possible.", ActionRisk.DESTRUCTIVE),
            "get_chat_history": ActionDefinition("get_chat_history", "Get Chat History", "Read recent chat history.", ActionRisk.SAFE),
            "get_chat_members": ActionDefinition("get_chat_members", "Get Chat Members", "Inspect members of a chat, including search, admin and banned filters.", ActionRisk.SAFE),
            "get_chat_member": ActionDefinition("get_chat_member", "Get Chat Member", "Inspect one member inside a specific chat, including status and permissions.", ActionRisk.SAFE),
            "get_linked_chat_info": ActionDefinition("get_linked_chat_info", "Get Linked Chat Info", "Inspect the linked discussion chat or linked channel for a chat.", ActionRisk.SAFE),
            "get_post_comments": ActionDefinition("get_post_comments", "Get Post Comments", "Inspect the discussion replies/comments for a channel post.", ActionRisk.SAFE),
            "get_chat_info": ActionDefinition("get_chat_info", "Get Chat Info", "Lookup chat metadata.", ActionRisk.SAFE),
            "get_user_info": ActionDefinition("get_user_info", "Get User Info", "Lookup user metadata.", ActionRisk.SAFE),
            "block_user": ActionDefinition("block_user", "Block User", "Block a user account.", ActionRisk.DESTRUCTIVE),
            "unblock_user": ActionDefinition("unblock_user", "Unblock User", "Unblock a user account.", ActionRisk.SENSITIVE),
            "join_chat": ActionDefinition("join_chat", "Join Chat", "Join a chat, channel, or invite link.", ActionRisk.SENSITIVE),
            "leave_chat": ActionDefinition("leave_chat", "Leave Chat", "Leave a chat or channel.", ActionRisk.DESTRUCTIVE),
            "export_chat_invite_link": ActionDefinition("export_chat_invite_link", "Export Chat Invite Link", "Generate a new primary invite link for a chat.", ActionRisk.SENSITIVE),
            "create_chat_invite_link": ActionDefinition("create_chat_invite_link", "Create Chat Invite Link", "Create an additional invite link for a chat.", ActionRisk.SENSITIVE),
            "edit_chat_invite_link": ActionDefinition("edit_chat_invite_link", "Edit Chat Invite Link", "Edit an existing non-primary invite link.", ActionRisk.SENSITIVE),
            "revoke_chat_invite_link": ActionDefinition("revoke_chat_invite_link", "Revoke Chat Invite Link", "Revoke a previously created invite link.", ActionRisk.SENSITIVE),
            "approve_chat_join_request": ActionDefinition("approve_chat_join_request", "Approve Chat Join Request", "Approve a pending request to join a chat.", ActionRisk.SENSITIVE),
            "decline_chat_join_request": ActionDefinition("decline_chat_join_request", "Decline Chat Join Request", "Decline a pending request to join a chat.", ActionRisk.SENSITIVE),
            "create_group": ActionDefinition("create_group", "Create Group", "Create a new group or supergroup.", ActionRisk.SENSITIVE),
            "create_channel": ActionDefinition("create_channel", "Create Channel", "Create a new channel.", ActionRisk.SENSITIVE),
            "ban_user": ActionDefinition("ban_user", "Ban User", "Ban or kick a user from a chat.", ActionRisk.DESTRUCTIVE),
            "unban_user": ActionDefinition("unban_user", "Unban User", "Unban a user from a chat.", ActionRisk.SENSITIVE),
            "set_chat_permissions": ActionDefinition("set_chat_permissions", "Set Chat Permissions", "Change default permissions for members in a chat.", ActionRisk.SENSITIVE),
            "restrict_chat_member": ActionDefinition("restrict_chat_member", "Restrict Chat Member", "Restrict a member in a chat.", ActionRisk.DESTRUCTIVE),
            "unrestrict_chat_member": ActionDefinition("unrestrict_chat_member", "Unrestrict Chat Member", "Lift restrictions from a member in a chat.", ActionRisk.SENSITIVE),
            "promote_chat_member": ActionDefinition("promote_chat_member", "Promote Chat Member", "Promote a member to administrator in a chat.", ActionRisk.SENSITIVE),
            "demote_chat_member": ActionDefinition("demote_chat_member", "Demote Chat Member", "Remove administrator rights from a member in a chat.", ActionRisk.SENSITIVE),
            "set_administrator_title": ActionDefinition("set_administrator_title", "Set Administrator Title", "Set or clear a custom administrator title in a chat.", ActionRisk.SENSITIVE),
            "set_chat_title": ActionDefinition("set_chat_title", "Set Chat Title", "Change chat title.", ActionRisk.SENSITIVE),
            "set_chat_description": ActionDefinition("set_chat_description", "Set Chat Description", "Change chat description.", ActionRisk.SENSITIVE),
            "set_chat_photo": ActionDefinition("set_chat_photo", "Set Chat Photo", "Change chat photo or video avatar.", ActionRisk.SENSITIVE),
            "delete_chat_photo": ActionDefinition("delete_chat_photo", "Delete Chat Photo", "Delete the current chat photo.", ActionRisk.SENSITIVE),
            "update_contact": ActionDefinition("update_contact", "Update Contact", "Rename a contact in address book.", ActionRisk.SENSITIVE),
            "add_contact": ActionDefinition("add_contact", "Add Contact", "Add a user to the personal address book by user_id or @username.", ActionRisk.SENSITIVE),
            "delete_contact": ActionDefinition("delete_contact", "Delete Contact", "Remove a user from the personal address book.", ActionRisk.SENSITIVE),
            "select_target": ActionDefinition("select_target", "Select Target", "Save active chat or user target for later commands.", ActionRisk.SAFE),
            "read_reply_context": ActionDefinition("read_reply_context", "Read Reply Context", "Read information from the replied message.", ActionRisk.SAFE),
            "generate_draft": ActionDefinition("generate_draft", "Generate Draft", "Generate an action preview or draft without sending.", ActionRisk.SAFE),
            "cross_chat_request": ActionDefinition("cross_chat_request", "Cross Chat Request", "Execute an existing cross-chat Telegram operation through the registry.", ActionRisk.SENSITIVE),
        }

    def get(self, name: str) -> ActionDefinition | None:
        return self._definitions.get(name)

    def require(self, name: str) -> ActionDefinition:
        definition = self.get(name)
        if definition is None:
            raise KeyError(f"Unknown action: {name}")
        return definition

    def all(self) -> list[ActionDefinition]:
        return list(self._definitions.values())

    def grouped(self) -> list[tuple[str, list[ActionDefinition]]]:
        grouped: list[tuple[str, list[ActionDefinition]]] = []
        seen_names: set[str] = set()
        for category_label, action_names in ACTION_CATEGORY_SPECS:
            definitions = [
                self._definitions[name]
                for name in action_names
                if name in self._definitions
            ]
            if definitions:
                grouped.append((category_label, definitions))
                seen_names.update(definition.name for definition in definitions)

        leftovers = [
            definition
            for definition in self.all()
            if definition.name not in seen_names
        ]
        if leftovers:
            grouped.append(("Other actions", leftovers))
        return grouped

    def build_compact_reference(self) -> str:
        lines = ["Registered Telegram action capabilities:"]
        for category_label, definitions in self.grouped():
            lines.append(
                f"- {category_label}: "
                + ", ".join(definition.name for definition in definitions)
            )
        return "\n".join(lines)

    def build_detailed_reference(self) -> str:
        lines = ["Registered Telegram action capabilities with meaning:"]
        for category_label, definitions in self.grouped():
            lines.append(f"- {category_label}:")
            for definition in definitions:
                lines.append(f"  - {definition.name}: {definition.description}")
        return "\n".join(lines)
