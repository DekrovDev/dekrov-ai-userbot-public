from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ActionRisk(str, Enum):
    SAFE = "safe"
    SENSITIVE = "sensitive"
    DESTRUCTIVE = "destructive"
    CRITICAL = "critical"


class ActionStatus(str, Enum):
    DRAFT = "draft"
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class ActionContext:
    requester_user_id: int
    request_chat_id: int
    request_message_id: int | None
    raw_prompt: str
    reply_to_message_id: int | None = None
    reply_to_user_id: int | None = None
    reply_to_username: str | None = None
    current_chat_title: str | None = None
    current_chat_username: str | None = None


@dataclass(slots=True)
class ResolvedActionTarget:
    kind: str
    lookup: str | int | None
    label: str
    chat_id: int | None = None
    user_id: int | None = None
    message_id: int | None = None
    source: str = "explicit"


@dataclass(slots=True)
class ActionRequest:
    action_name: str
    raw_prompt: str
    context: ActionContext
    arguments: dict[str, Any] = field(default_factory=dict)
    target: ResolvedActionTarget | None = None
    secondary_target: ResolvedActionTarget | None = None
    risk: ActionRisk = ActionRisk.SAFE
    requires_confirmation: bool = False
    summary: str = ""
    impact_summary: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ActionResult:
    action_name: str
    status: ActionStatus
    message: str
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(slots=True)
class PendingAction:
    action_id: str
    request: ActionRequest
    status: ActionStatus
    preview_text: str
    confirmation_phrase: str
    rejection_phrase: str
    created_at: str
    expires_at: str
    requester_user_id: int
    request_chat_id: int
    request_message_id: int | None
    completed_message: str | None = None
    error: str | None = None

    def is_expired(self) -> bool:
        try:
            expires_at = datetime.fromisoformat(self.expires_at)
        except ValueError:
            return False
        now = datetime.now(timezone.utc)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return now >= expires_at


@dataclass(slots=True)
class ActionDefinition:
    name: str
    title: str
    description: str
    default_risk: ActionRisk
    supported: bool = True

