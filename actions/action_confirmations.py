from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timedelta, timezone

from .action_models import ActionRequest, ActionStatus, PendingAction


class ActionConfirmationStore:
    def __init__(self, ttl_seconds: int = 45) -> None:
        self._ttl_seconds = max(30, min(ttl_seconds, 60))
        self._lock = asyncio.Lock()
        self._pending: dict[str, PendingAction] = {}
        self._latest_by_requester: dict[int, str] = {}

    async def create_pending(self, request: ActionRequest, preview_text: str) -> PendingAction:
        async with self._lock:
            self._expire_locked()
            action_id = self._generate_action_id_locked()
            created_at = datetime.now(timezone.utc)
            pending = PendingAction(
                action_id=action_id,
                request=request,
                status=ActionStatus.PENDING_CONFIRMATION,
                preview_text=preview_text,
                confirmation_phrase=f"CONFIRM {action_id}",
                rejection_phrase=f"REJECT {action_id}",
                created_at=created_at.isoformat(),
                expires_at=(created_at + timedelta(seconds=self._ttl_seconds)).isoformat(),
                requester_user_id=request.context.requester_user_id,
                request_chat_id=request.context.request_chat_id,
                request_message_id=request.context.request_message_id,
            )
            self._pending[action_id] = pending
            self._latest_by_requester[request.context.requester_user_id] = action_id
            return pending

    async def get(self, action_id: str) -> PendingAction | None:
        async with self._lock:
            self._expire_locked()
            pending = self._pending.get(action_id.upper())
            return self._copy_pending(pending)

    async def confirm(self, action_id: str, requester_user_id: int, phrase: str) -> PendingAction | None:
        async with self._lock:
            self._expire_locked()
            pending = self._pending.get(action_id.upper())
            if pending is None or pending.requester_user_id != requester_user_id:
                return None
            if phrase.strip() != pending.confirmation_phrase:
                return None
            pending.status = ActionStatus.CONFIRMED
            return self._copy_pending(pending)

    async def reject(self, action_id: str, requester_user_id: int, phrase: str) -> PendingAction | None:
        async with self._lock:
            self._expire_locked()
            pending = self._pending.get(action_id.upper())
            if pending is None or pending.requester_user_id != requester_user_id:
                return None
            if phrase.strip() != pending.rejection_phrase:
                return None
            pending.status = ActionStatus.REJECTED
            return self._copy_pending(pending)

    async def mark_queued(self, action_id: str) -> PendingAction | None:
        return await self._transition(action_id, ActionStatus.QUEUED)

    async def mark_running(self, action_id: str) -> PendingAction | None:
        return await self._transition(action_id, ActionStatus.RUNNING)

    async def mark_completed(self, action_id: str, message: str) -> PendingAction | None:
        async with self._lock:
            self._expire_locked()
            pending = self._pending.get(action_id.upper())
            if pending is None:
                return None
            pending.status = ActionStatus.COMPLETED
            pending.completed_message = message
            return self._copy_pending(pending)

    async def mark_failed(self, action_id: str, error: str) -> PendingAction | None:
        async with self._lock:
            self._expire_locked()
            pending = self._pending.get(action_id.upper())
            if pending is None:
                return None
            pending.status = ActionStatus.FAILED
            pending.error = error
            return self._copy_pending(pending)

    async def consume(self, action_id: str) -> PendingAction | None:
        async with self._lock:
            self._expire_locked()
            pending = self._pending.pop(action_id.upper(), None)
            if pending is not None and self._latest_by_requester.get(pending.requester_user_id) == action_id.upper():
                self._latest_by_requester.pop(pending.requester_user_id, None)
            return self._copy_pending(pending)

    async def consume_rejected(self, action_id: str) -> PendingAction | None:
        return await self.consume(action_id)

    def parse_confirmation_phrase(self, text: str) -> tuple[str, str] | None:
        normalized = " ".join((text or "").strip().split())
        if not normalized:
            return None
        upper = normalized.upper()
        if upper.startswith("CONFIRM "):
            return "confirm", upper.split(" ", 1)[1].strip()
        if upper.startswith("REJECT "):
            return "reject", upper.split(" ", 1)[1].strip()
        return None

    async def latest_for_requester(self, requester_user_id: int) -> PendingAction | None:
        async with self._lock:
            self._expire_locked()
            action_id = self._latest_by_requester.get(requester_user_id)
            if not action_id:
                return None
            return self._copy_pending(self._pending.get(action_id))

    async def _transition(self, action_id: str, status: ActionStatus) -> PendingAction | None:
        async with self._lock:
            self._expire_locked()
            pending = self._pending.get(action_id.upper())
            if pending is None:
                return None
            pending.status = status
            return self._copy_pending(pending)

    def _expire_locked(self) -> None:
        expired_ids = [action_id for action_id, pending in self._pending.items() if pending.is_expired()]
        for action_id in expired_ids:
            pending = self._pending[action_id]
            pending.status = ActionStatus.EXPIRED
            if self._latest_by_requester.get(pending.requester_user_id) == action_id:
                self._latest_by_requester.pop(pending.requester_user_id, None)
            self._pending.pop(action_id, None)

    def _generate_action_id_locked(self) -> str:
        while True:
            action_id = secrets.token_hex(3).upper()
            if action_id not in self._pending:
                return action_id

    def _copy_pending(self, pending: PendingAction | None) -> PendingAction | None:
        if pending is None:
            return None
        return PendingAction(
            action_id=pending.action_id,
            request=pending.request,
            status=pending.status,
            preview_text=pending.preview_text,
            confirmation_phrase=pending.confirmation_phrase,
            rejection_phrase=pending.rejection_phrase,
            created_at=pending.created_at,
            expires_at=pending.expires_at,
            requester_user_id=pending.requester_user_id,
            request_chat_id=pending.request_chat_id,
            request_message_id=pending.request_message_id,
            completed_message=pending.completed_message,
            error=pending.error,
        )
