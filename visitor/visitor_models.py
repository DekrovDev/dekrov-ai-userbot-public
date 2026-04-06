from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class VisitorRole(str, Enum):
    VISITOR = "visitor"


class TopicCategory(str, Enum):
    ABOUT_OWNER = "about_owner"
    ABOUT_PROJECTS = "about_projects"
    TECHNICAL_QUESTION = "technical_question"
    PROJECT_SPECIFIC_QUESTION = "project_specific_question"
    FAQ = "faq"
    COLLABORATION = "collaboration"
    LINKS = "links"
    ASSISTANT_CAPABILITIES = "assistant_capabilities"
    GREETING = "greeting"
    GENERAL = "general"
    DISALLOWED_OFFTOPIC = "disallowed_offtopic"
    DISALLOWED_INTERNAL = "disallowed_internal"
    DISALLOWED_ADMIN = "disallowed_admin"
    DISALLOWED_PRIVATE = "disallowed_private"


@dataclass(slots=True)
class PolicyDecision:
    allowed: bool
    category: TopicCategory
    redirect_message: str | None = None


@dataclass
class VisitorContext:
    """In-memory context for one visitor conversation.
    Stores lightweight metadata plus active-session dialogue history.
    """
    user_id: int
    active: bool = False
    # Metadata
    username: str | None = None
    first_name: str | None = None
    started_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    message_count: int = 0
    topic_counts: dict = field(default_factory=dict)
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    # Rate limiting
    recent_message_timestamps: list[float] = field(default_factory=list)
    # AI wants to end
    ai_offered_end: bool = False
    # Boundary handling for "just chat / be my friend" attempts
    boundary_streak: int = 0
    last_boundary_at: float = 0.0
    # Low-signal / topic drift handling
    low_signal_streak: int = 0
    last_low_signal_at: float = 0.0
    # Short cooldown after forced consultation end
    restart_cooldown_until: float = 0.0
    # Moderation / abuse control
    abuse_strikes: int = 0
    last_abuse_at: float = 0.0
    last_abuse_reason: str | None = None
    last_abuse_text: str | None = None
    last_owner_alert_at: float = 0.0
    temp_blocked_until: float = 0.0

    def record_topic(self, category: str) -> None:
        self.topic_counts[category] = self.topic_counts.get(category, 0) + 1
        self.message_count += 1
        self.last_activity = time.time()

    def add_history_message(self, role: str, text: str) -> None:
        normalized = str(text or "").strip()
        if not normalized:
            return
        if role not in {"user", "assistant"}:
            return
        self.conversation_history.append(
            {
                "role": role,
                "content": normalized[:4000],
            }
        )
        self.last_activity = time.time()

    def clear_session_memory(self) -> None:
        self.message_count = 0
        self.topic_counts = {}
        self.conversation_history = []
        self.recent_message_timestamps = []
        self.ai_offered_end = False
        self.boundary_streak = 0
        self.last_boundary_at = 0.0
        self.low_signal_streak = 0
        self.last_low_signal_at = 0.0
        self.active = False

    def is_rate_limited(self, max_per_minute: int = 10) -> bool:
        now = time.time()
        self.recent_message_timestamps = [
            ts for ts in self.recent_message_timestamps if now - ts < 60
        ]
        if len(self.recent_message_timestamps) >= max_per_minute:
            return True
        self.recent_message_timestamps.append(now)
        return False

    def is_inactive(self, timeout_seconds: float = 600) -> bool:
        return (time.time() - self.last_activity) > timeout_seconds

    def is_temporarily_blocked(self) -> bool:
        return self.temp_blocked_until > time.time()

    def temporary_block_remaining_seconds(self) -> int:
        return max(0, int(self.temp_blocked_until - time.time()))

    def restart_cooldown_remaining_seconds(self) -> int:
        return max(0, int(self.restart_cooldown_until - time.time()))

    def register_abuse(
        self,
        reason: str,
        text: str,
        *,
        strike_window_seconds: int = 86400,
    ) -> int:
        now = time.time()
        if not self.last_abuse_at or (now - self.last_abuse_at) > strike_window_seconds:
            self.abuse_strikes = 0
        self.abuse_strikes += 1
        self.last_abuse_at = now
        self.last_abuse_reason = reason
        self.last_abuse_text = text
        self.last_activity = now
        return self.abuse_strikes

    def set_temporary_block(self, duration_seconds: int) -> None:
        now = time.time()
        self.temp_blocked_until = max(self.temp_blocked_until, now + duration_seconds)
        self.active = False
        self.ai_offered_end = False
        self.last_activity = now

    def clear_moderation_flags(self) -> None:
        self.abuse_strikes = 0
        self.last_abuse_at = 0.0
        self.last_abuse_reason = None
        self.last_abuse_text = None
        self.last_owner_alert_at = 0.0
        self.temp_blocked_until = 0.0

    def register_boundary_attempt(self, *, reset_window_seconds: int = 1800) -> int:
        now = time.time()
        if not self.last_boundary_at or (now - self.last_boundary_at) > reset_window_seconds:
            self.boundary_streak = 0
        self.boundary_streak += 1
        self.last_boundary_at = now
        self.last_activity = now
        return self.boundary_streak

    def reset_boundary_streak(self) -> None:
        self.boundary_streak = 0
        self.last_boundary_at = 0.0

    def register_low_signal(self, *, reset_window_seconds: int = 1800) -> int:
        now = time.time()
        if not self.last_low_signal_at or (now - self.last_low_signal_at) > reset_window_seconds:
            self.low_signal_streak = 0
        self.low_signal_streak += 1
        self.last_low_signal_at = now
        self.last_activity = now
        return self.low_signal_streak

    def reset_low_signal_streak(self) -> None:
        self.low_signal_streak = 0
        self.last_low_signal_at = 0.0

    def set_restart_cooldown(self, duration_seconds: int) -> None:
        now = time.time()
        self.restart_cooldown_until = max(self.restart_cooldown_until, now + duration_seconds)
        self.last_activity = now

    @property
    def display_name(self) -> str:
        if self.first_name:
            return self.first_name
        if self.username:
            return f"@{self.username}"
        return f"user_{self.user_id}"

    @property
    def duration_minutes(self) -> float:
        return round((time.time() - self.started_at) / 60, 1)
