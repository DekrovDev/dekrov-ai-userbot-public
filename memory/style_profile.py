from __future__ import annotations

import asyncio
import json
import re
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from infra.json_atomic import atomic_write_json_sync


OWNER_BATCH_SIZE = 3
USER_BATCH_SIZE = 5
RELATIONSHIP_BATCH_SIZE = 3
RECENT_SAMPLE_LIMIT = 6
TOPIC_LIMIT = 5

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁёІіЇїЄєҐґ0-9_@#:/.-]+", re.UNICODE)
TOPIC_WORD_RE = re.compile(
    r"[A-Za-zА-Яа-яЁёІіЇїЄєҐґ][A-Za-zА-Яа-яЁёІіЇїЄєҐґ0-9_-]{2,}", re.UNICODE
)
PROFANITY_RE = re.compile(
    r"(?iu)\b(?:бля|блять|сука|нахуй|хуй|еб|пизд|fuck|shit|bitch|cazzo|merda|mierda)\w*\b"
)
HUMOR_RE = re.compile(r"(?iu)(?:аха|хаха|лол|кек|ржу|xd|haha|hehe|jaja|lmao|\)\)\)+)")
FORMAL_RE = re.compile(
    r"(?iu)\b(?:здравствуйте|пожалуйста|благодарю|уважаемый|please|thank you|regards|grazie|bonjour)\b"
)
SLANG_RE = re.compile(
    r"(?iu)\b(?:ща|чё|че|типо|кароч|изи|кринж|жиза|имба|пж|pls|bro|bruh|wtf|omg)\b"
)
DIRECT_RE = re.compile(
    r"(?iu)\b(?:сделай|дай|скинь|напиши|скажи|ответь|go|do|send|tell|write|show|manda)\b"
)
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", re.UNICODE)
STOPWORDS = {
    "это",
    "этот",
    "как",
    "что",
    "чтобы",
    "если",
    "или",
    "когда",
    "который",
    "которые",
    "where",
    "what",
    "when",
    "with",
    "that",
    "this",
    "have",
    "just",
    "your",
    "about",
    "chat",
    "group",
    "message",
    "reply",
    "меня",
    "тебя",
    "него",
    "она",
    "они",
    "you",
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(text: str) -> str:
    return " ".join((text or "").strip().split())


def _is_meaningful(text: str) -> bool:
    normalized = _normalize_text(text)
    if len(normalized) < 4 or normalized.startswith("."):
        return False
    if not any(ch.isalnum() for ch in normalized):
        return False
    words = WORD_RE.findall(normalized)
    return len(words) >= 2 or len(normalized) >= 10


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _clip(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _weighted_average(
    old_value: float, old_count: int, new_value: float, new_count: int
) -> float:
    total = old_count + new_count
    if total <= 0:
        return 0.0
    return ((old_value * old_count) + (new_value * new_count)) / total


def _bucket_verbosity(avg_words: float) -> str:
    if avg_words <= 6:
        return "short"
    if avg_words >= 16:
        return "long"
    return "medium"


def _bucket_level(score: float, low: float = 0.25, high: float = 0.55) -> str:
    if score >= high:
        return "high"
    if score >= low:
        return "medium"
    return "low"


def _bucket_punctuation(density: float) -> str:
    if density >= 0.08:
        return "heavy"
    if density >= 0.035:
        return "balanced"
    return "light"


def _bucket_reply_shape(fragment_ratio: float, avg_words: float) -> str:
    if fragment_ratio >= 0.70 or avg_words <= 5:
        return "fragments"
    if avg_words <= 12:
        return "short_sentences"
    return "full_sentences"


def _bucket_tone(
    formality_score: float, humor_score: float, profanity_score: float
) -> str:
    if humor_score >= 0.45:
        return "playful"
    if formality_score >= 0.55 and profanity_score < 0.15:
        return "formal"
    return "casual"


def _bucket_directness(score: float) -> str:
    if score >= 0.65:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


def _score_from_level(value: str) -> float:
    mapping = {"low": 0.05, "medium": 0.35, "high": 0.75}
    return mapping.get((value or "").strip().casefold(), 0.35)


def _verbosity_to_words(value: str) -> float:
    mapping = {"short": 5.0, "medium": 11.0, "long": 18.0}
    return mapping.get((value or "").strip().casefold(), 11.0)


def _extract_topics(messages: list[str]) -> list[str]:
    counts: Counter[str] = Counter()
    for text in messages:
        for raw_word in TOPIC_WORD_RE.findall(text or ""):
            word = raw_word.casefold()
            if word in STOPWORDS or word.isdigit():
                continue
            counts[word] += 1
    return [word for word, _ in counts.most_common(TOPIC_LIMIT)]


def _merge_topics(existing: list[str], fresh: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for topic in [*(existing or []), *(fresh or [])]:
        normalized = (topic or "").strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(normalized)
        if len(merged) >= TOPIC_LIMIT:
            break
    return merged


def _limit_samples(existing: list[str], fresh: list[str]) -> list[str]:
    merged = [item for item in [*(existing or []), *(fresh or [])] if item]
    return merged[-RECENT_SAMPLE_LIMIT:]


def _combine_choice(
    primary: str, secondary: str | None, adaptation_strength: float
) -> str:
    if not secondary or secondary == primary or adaptation_strength < 0.33:
        return primary
    if adaptation_strength < 0.66:
        return f"{primary}->{secondary}"
    return secondary


def _blend_verbosity(
    owner_value: str,
    relationship_value: str | None,
    user_value: str | None,
    short_replies: bool,
) -> str:
    if short_replies:
        return "short"
    if relationship_value:
        return relationship_value
    if user_value and owner_value == "medium":
        return user_value
    return owner_value


def _summarize_traits(**traits: str) -> str:
    return "; ".join(f"{key}={value}" for key, value in traits.items())


def _analyze_messages(messages: list[str]) -> dict[str, Any]:
    normalized_messages = [
        _normalize_text(message) for message in messages if _is_meaningful(message)
    ]
    if not normalized_messages:
        return {
            "sample_size": 0,
            "avg_message_length": 0.0,
            "avg_words": 0.0,
            "punctuation_density": 0.0,
            "slang_score": 0.0,
            "formality_score": 0.0,
            "directness_score": 0.0,
            "profanity_score": 0.0,
            "humor_score": 0.0,
            "emoji_score": 0.0,
            "fragment_ratio": 0.0,
            "tone": "casual",
            "verbosity": "short",
            "profanity": "low",
            "humor": "low",
            "formality": "low",
            "punctuation": "light",
            "emoji_usage": "low",
            "reply_shape": "fragments",
            "directness": "medium",
            "topics": [],
            "samples": [],
        }

    sample_size = len(normalized_messages)
    total_chars = sum(len(message) for message in normalized_messages)
    word_counts = [len(WORD_RE.findall(message)) for message in normalized_messages]
    total_words = sum(word_counts)
    punctuation_count = sum(
        sum(1 for ch in message if ch in "!?.,:;") for message in normalized_messages
    )
    slang_hits = sum(len(SLANG_RE.findall(message)) for message in normalized_messages)
    formal_hits = sum(
        len(FORMAL_RE.findall(message)) for message in normalized_messages
    )
    direct_hits = sum(
        len(DIRECT_RE.findall(message)) for message in normalized_messages
    )
    profanity_hits = sum(
        len(PROFANITY_RE.findall(message)) for message in normalized_messages
    )
    humor_hits = sum(len(HUMOR_RE.findall(message)) for message in normalized_messages)
    emoji_hits = sum(len(EMOJI_RE.findall(message)) for message in normalized_messages)
    fragments = sum(1 for words in word_counts if words <= 6)
    avg_message_length = _safe_div(total_chars, sample_size)
    avg_words = _safe_div(total_words, sample_size)
    punctuation_density = _safe_div(punctuation_count, max(total_chars, 1))
    slang_score = _clip(_safe_div(slang_hits, sample_size), 0.0, 1.0)
    formality_score = _clip(_safe_div(formal_hits, sample_size), 0.0, 1.0)
    directness_score = _clip(
        (
            _safe_div(direct_hits, sample_size)
            + (0.22 if avg_words <= 9 else 0.0)
            + (0.12 if fragments / sample_size >= 0.65 else 0.0)
        ),
        0.0,
        1.0,
    )
    profanity_score = _clip(_safe_div(profanity_hits, sample_size), 0.0, 1.0)
    humor_score = _clip(_safe_div(humor_hits, sample_size), 0.0, 1.0)
    emoji_score = _clip(_safe_div(emoji_hits, sample_size), 0.0, 1.0)
    fragment_ratio = _clip(_safe_div(fragments, sample_size), 0.0, 1.0)
    return {
        "sample_size": sample_size,
        "avg_message_length": avg_message_length,
        "avg_words": avg_words,
        "punctuation_density": punctuation_density,
        "slang_score": slang_score,
        "formality_score": formality_score,
        "directness_score": directness_score,
        "profanity_score": profanity_score,
        "humor_score": humor_score,
        "emoji_score": emoji_score,
        "fragment_ratio": fragment_ratio,
        "tone": _bucket_tone(formality_score, humor_score, profanity_score),
        "verbosity": _bucket_verbosity(avg_words),
        "profanity": _bucket_level(profanity_score, low=0.10, high=0.30),
        "humor": _bucket_level(humor_score, low=0.15, high=0.40),
        "formality": _bucket_level(formality_score, low=0.20, high=0.55),
        "punctuation": _bucket_punctuation(punctuation_density),
        "emoji_usage": _bucket_level(emoji_score, low=0.08, high=0.25),
        "reply_shape": _bucket_reply_shape(fragment_ratio, avg_words),
        "directness": _bucket_directness(directness_score),
        "topics": _extract_topics(normalized_messages),
        "samples": normalized_messages[-RECENT_SAMPLE_LIMIT:],
    }


@dataclass(slots=True)
class OwnerStyleProfile:
    tone: str = "casual"
    verbosity: str = "short"
    profanity: str = "low"
    humor: str = "medium"
    formality: str = "low"
    punctuation: str = "light"
    emoji_usage: str = "low"
    reply_shape: str = "fragments"
    directness: str = "high"
    average_message_length: float = 0.0
    average_words: float = 0.0
    punctuation_density: float = 0.0
    slang_score: float = 0.0
    formality_score: float = 0.0
    directness_score: float = 0.0
    analyzed_messages: int = 0
    common_topics: list[str] = field(default_factory=list)
    recent_samples: list[str] = field(default_factory=list)
    last_updated: str | None = None

    @property
    def average_length(self) -> float:
        return self.average_message_length

    def build_instruction(self) -> str:
        return "Owner base style: " + self.to_summary()

    def to_summary(self) -> str:
        traits = _summarize_traits(
            tone=self.tone,
            verbosity=self.verbosity,
            profanity=self.profanity,
            humor=self.humor,
            formality=self.formality,
            punctuation=self.punctuation,
            emoji=self.emoji_usage,
            reply_shape=self.reply_shape,
            directness=self.directness,
        )
        topics = (
            f"; common_topics={', '.join(self.common_topics[:3])}"
            if self.common_topics
            else ""
        )
        return f"{traits}{topics}"


@dataclass(slots=True)
class UserStyleProfile:
    user_id: int
    username: str | None = None
    avg_message_length: float = 0.0
    tone: str = "casual"
    verbosity: str = "medium"
    profanity_tolerance: str = "medium"
    humor_level: str = "medium"
    formality: str = "low"
    punctuation_style: str = "light"
    emoji_usage: str = "low"
    common_topics: list[str] = field(default_factory=list)
    last_updated: str | None = None
    sample_size: int = 0

    def to_summary(self) -> str:
        prefix = f"username=@{self.username}; " if self.username else ""
        topics = (
            f"; common_topics={', '.join(self.common_topics[:3])}"
            if self.common_topics
            else ""
        )
        return (
            f"{prefix}tone={self.tone}; verbosity={self.verbosity}; profanity_tolerance={self.profanity_tolerance}; "
            f"humor={self.humor_level}; formality={self.formality}; punctuation={self.punctuation_style}; "
            f"emoji={self.emoji_usage}{topics}"
        )


@dataclass(slots=True)
class RelationshipProfile:
    user_id: int
    familiarity: str = "medium"
    trust_level: str = "medium"
    banter_allowed: bool = False
    preferred_reply_length: str = "medium"
    preferred_reply_tone: str = "casual"
    avoid_profanity: bool = False
    max_adaptation_strength: float = 0.45
    owner_directness: str = "medium"
    owner_formality: str = "low"
    owner_humor: str = "medium"
    owner_profanity: str = "low"
    common_topics: list[str] = field(default_factory=list)
    recent_samples: list[str] = field(default_factory=list)
    updated_at: str | None = None
    sample_size: int = 0

    def to_summary(self) -> str:
        topics = (
            f"; common_topics={', '.join(self.common_topics[:3])}"
            if self.common_topics
            else ""
        )
        return (
            f"familiarity={self.familiarity}; trust={self.trust_level}; banter_allowed={str(self.banter_allowed).lower()}; "
            f"preferred_reply_length={self.preferred_reply_length}; preferred_reply_tone={self.preferred_reply_tone}; "
            f"owner_directness={self.owner_directness}; owner_formality={self.owner_formality}; "
            f"owner_humor={self.owner_humor}; owner_profanity={self.owner_profanity}; "
            f"avoid_profanity={str(self.avoid_profanity).lower()}; max_adaptation_strength={self.max_adaptation_strength:.2f}{topics}"
        )


@dataclass(slots=True)
class StyleBlendResult:
    instruction: str
    owner_summary: str
    target_summary: str | None
    relationship_summary: str | None
    final_style_summary: str
    used_profiles: list[str]
    confidence: float
    adaptation_strength: float
    final_traits: dict[str, str]


@dataclass(slots=True)
class _StyleConfig:
    style_memory_enabled: bool = True
    style_owner_profile_enabled: bool = True
    style_user_profile_enabled: bool = True
    style_relationship_profile_enabled: bool = True
    style_context_analysis_enabled: bool = True
    style_auto_update_enabled: bool = True
    style_max_adaptation_strength: float = 0.45
    style_owner_weight: float = 0.60
    style_target_weight: float = 0.25
    style_context_weight: float = 0.15
    style_debug_logging: bool = False


class StyleProfileStore:
    def __init__(self, path: Path, config: Any | None = None) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._config = self._coerce_config(config)
        self._owner_profile = OwnerStyleProfile()
        self._user_profiles: dict[str, UserStyleProfile] = {}
        self._relationship_profiles: dict[str, RelationshipProfile] = {}
        self._pending_owner: dict[str, deque[str]] = {"owner": deque()}
        self._pending_user_messages: dict[str, deque[str]] = defaultdict(deque)
        self._pending_relationship_messages: dict[str, deque[str]] = defaultdict(deque)

    async def load(self) -> None:
        async with self._lock:
            if not self._path.exists():
                return
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                return
            if "owner_profile" not in payload:
                self._owner_profile = self._deserialize_owner_profile(payload)
                return
            self._owner_profile = self._deserialize_owner_profile(
                payload.get("owner_profile") or {}
            )
            self._user_profiles = {
                str(key): self._deserialize_user_profile(value)
                for key, value in (payload.get("user_profiles") or {}).items()
                if isinstance(value, dict)
            }
            self._relationship_profiles = {
                str(key): self._deserialize_relationship_profile(value)
                for key, value in (payload.get("relationship_profiles") or {}).items()
                if isinstance(value, dict)
            }

    async def get_snapshot(self) -> OwnerStyleProfile:
        async with self._lock:
            return OwnerStyleProfile(**asdict(self._owner_profile))

    async def update_from_owner_message(
        self,
        text: str,
        *,
        source_user_id: int | None = None,
        owner_user_id: int | None = None,
    ) -> None:
        del source_user_id, owner_user_id
        if (
            not self._config.style_memory_enabled
            or not self._config.style_owner_profile_enabled
        ):
            return
        if not self._config.style_auto_update_enabled or not _is_meaningful(text):
            return
        async with self._lock:
            queue = self._pending_owner["owner"]
            queue.append(text)
            if len(queue) < OWNER_BATCH_SIZE:
                return
            batch = list(queue)
            queue.clear()
            self._apply_owner_batch(batch)
            await self._save_locked()

    async def observe_user_message(
        self, user_id: int | None, username: str | None, text: str
    ) -> None:
        if (
            not self._config.style_memory_enabled
            or not self._config.style_user_profile_enabled
        ):
            return
        if (
            not self._config.style_auto_update_enabled
            or user_id is None
            or not _is_meaningful(text)
        ):
            return
        key = str(user_id)
        async with self._lock:
            self._pending_user_messages[key].append(text)
            if len(self._pending_user_messages[key]) < USER_BATCH_SIZE:
                return
            batch = list(self._pending_user_messages[key])
            self._pending_user_messages[key].clear()
            self._apply_user_batch(user_id=user_id, username=username, messages=batch)
            await self._save_locked()

    async def observe_owner_interaction(
        self, user_id: int | None, username: str | None, owner_text: str
    ) -> None:
        if (
            not self._config.style_memory_enabled
            or not self._config.style_relationship_profile_enabled
        ):
            return
        if (
            not self._config.style_auto_update_enabled
            or user_id is None
            or not _is_meaningful(owner_text)
        ):
            return
        key = str(user_id)
        async with self._lock:
            self._pending_relationship_messages[key].append(owner_text)
            if len(self._pending_relationship_messages[key]) < RELATIONSHIP_BATCH_SIZE:
                return
            batch = list(self._pending_relationship_messages[key])
            self._pending_relationship_messages[key].clear()
            self._apply_relationship_batch(
                user_id=user_id, username=username, messages=batch
            )
            await self._save_locked()

    async def build_owner_writing_style(self) -> str:
        """Build a rich, concrete style description for draft generation."""
        async with self._lock:
            profile = self._owner_profile
            samples = list(profile.recent_samples[-12:])  # last 12 messages

        if not samples:
            return "Стиль не определён — нет достаточно сообщений."

        # Analyze concrete patterns from real messages
        uses_uppercase_start = sum(1 for s in samples if s and s[0].isupper()) / max(
            len(samples), 1
        )
        ends_with_dot = sum(1 for s in samples if s.rstrip().endswith(".")) / max(
            len(samples), 1
        )
        ends_with_no_punct = sum(
            1 for s in samples if s.rstrip() and s.rstrip()[-1].isalnum()
        ) / max(len(samples), 1)
        avg_words = sum(len(s.split()) for s in samples) / max(len(samples), 1)
        uses_emoji = sum(1 for s in samples if EMOJI_RE.search(s)) / max(
            len(samples), 1
        )
        uses_slang = sum(1 for s in samples if SLANG_RE.search(s.lower())) / max(
            len(samples), 1
        )
        uses_profanity = sum(
            1 for s in samples if PROFANITY_RE.search(s.lower())
        ) / max(len(samples), 1)
        multi_messages = sum(1 for s in samples if len(s.split()) <= 4) / max(
            len(samples), 1
        )

        rules = []

        # Capitalization
        if uses_uppercase_start < 0.2:
            rules.append(
                "НИКОГДА не начинай с заглавной буквы — владелец пишет строчными"
            )
        elif uses_uppercase_start > 0.8:
            rules.append("Начинай с заглавной буквы")

        # Punctuation
        if ends_with_dot < 0.1:
            rules.append("НЕ ставь точку в конце — владелец её не ставит")
        elif ends_with_dot > 0.7:
            rules.append("Ставь точку в конце предложений")

        if ends_with_no_punct > 0.7:
            rules.append("Заканчивай без знаков препинания")

        # Length
        if avg_words <= 5:
            rules.append(f"Очень короткие сообщения — в среднем {avg_words:.0f} слов")
        elif avg_words <= 10:
            rules.append(f"Короткие сообщения — в среднем {avg_words:.0f} слов")
        else:
            rules.append(f"Средняя длина — {avg_words:.0f} слов")

        # Fragmentation
        if multi_messages > 0.6:
            rules.append("Пишет короткими фрагментами, не длинными предложениями")

        # Emoji
        if uses_emoji < 0.1:
            rules.append("Эмодзи не использует")
        elif uses_emoji > 0.5:
            rules.append("Часто использует эмодзи")

        # Slang
        if uses_slang > 0.3:
            rules.append("Использует сленг (кароч, типо, изи и т.д.)")

        # Profanity
        if uses_profanity > 0.2:
            rules.append("Матерится иногда")

        rules_str = "\n".join(f"• {r}" for r in rules)

        # Real examples
        examples = "\n".join(f'"{s}"' for s in samples[-6:])

        return (
            f"Правила стиля (выведены из реальных сообщений):\n{rules_str}\n\n"
            f"Реальные примеры сообщений владельца:\n{examples}\n\n"
            f"ВАЖНО: Копируй именно этот стиль — регистр, пунктуацию, длину. "
            f"Не добавляй то чего не было в примерах."
        )

    async def build_prompt_sections(
        self,
        *,
        target_user_id: int | None = None,
        target_username: str | None = None,
    ) -> dict[str, str | None]:
        async with self._lock:
            user_profile = self._resolve_user_profile_locked(
                target_user_id, target_username
            )
            relationship_profile = self._resolve_relationship_profile_locked(
                target_user_id, target_username
            )
            return {
                "owner": self._owner_profile.to_summary(),
                "target": user_profile.to_summary() if user_profile else None,
                "relationship": relationship_profile.to_summary()
                if relationship_profile
                else None,
            }

    async def build_style_blend(
        self,
        *,
        target_user_id: int | None = None,
        target_username: str | None = None,
        chat_context_summary: str | None = None,
    ) -> StyleBlendResult:
        async with self._lock:
            owner_profile = OwnerStyleProfile(**asdict(self._owner_profile))
            user_profile = self._resolve_user_profile_locked(
                target_user_id, target_username
            )
            relationship_profile = self._resolve_relationship_profile_locked(
                target_user_id, target_username
            )
            used_profiles = ["owner"]
            if user_profile is not None:
                used_profiles.append("target_user")
            if relationship_profile is not None:
                used_profiles.append("relationship")
            if chat_context_summary:
                used_profiles.append("chat_context")
            weights = self._effective_weights(
                bool(user_profile), bool(chat_context_summary)
            )
            target_confidence = min(
                1.0,
                _safe_div(float(user_profile.sample_size if user_profile else 0), 18.0),
            )
            relationship_confidence = min(
                1.0,
                _safe_div(
                    float(
                        relationship_profile.sample_size if relationship_profile else 0
                    ),
                    12.0,
                ),
            )
            base_adaptation = weights["target"] * (
                0.55 * target_confidence + 0.45 * relationship_confidence
            )
            max_adaptation = (
                relationship_profile.max_adaptation_strength
                if relationship_profile
                else self._config.style_max_adaptation_strength
            )
            adaptation_strength = _clip(base_adaptation, 0.0, max_adaptation)
            final_traits = self._blend_traits(
                owner_profile,
                user_profile,
                relationship_profile,
                chat_context_summary,
                adaptation_strength,
            )
            confidence = _clip(
                0.55 + (0.25 * target_confidence) + (0.20 * relationship_confidence),
                0.35,
                0.98,
            )
            owner_summary = owner_profile.to_summary()
            target_summary = user_profile.to_summary() if user_profile else None
            relationship_summary = (
                relationship_profile.to_summary() if relationship_profile else None
            )
            final_style_summary = _summarize_traits(**final_traits)
            parts = [
                "Layered style system:",
                f"Owner base style ({weights['owner']:.2f} dominant): {owner_summary}",
            ]
            if target_summary:
                parts.append(
                    f"Target user style ({weights['target']:.2f} moderate influence): {target_summary}"
                )
            if relationship_summary:
                parts.append(f"Relationship profile: {relationship_summary}")
            if relationship_profile and relationship_profile.recent_samples:
                parts.append(
                    "Recent owner-to-this-person style samples: "
                    + " | ".join(
                        sample[:90]
                        for sample in relationship_profile.recent_samples[-3:]
                    )
                )
            if chat_context_summary:
                parts.append(
                    f"Chat context ({weights['context']:.2f} situational): {chat_context_summary}"
                )
            parts.append(f"Final blended reply style: {final_style_summary}")
            parts.append(
                "Anti-mimic rules: keep owner voice dominant; adapt subtly; do not copy unique phrases too often; "
                "do not copy typos intentionally; do not mirror the other person 1:1."
            )
            return StyleBlendResult(
                instruction=" ".join(part for part in parts if part).strip(),
                owner_summary=owner_summary,
                target_summary=target_summary,
                relationship_summary=relationship_summary,
                final_style_summary=final_style_summary,
                used_profiles=used_profiles,
                confidence=confidence,
                adaptation_strength=adaptation_strength,
                final_traits=final_traits,
            )

    def _coerce_config(self, config: Any | None) -> _StyleConfig:
        if config is None:
            return _StyleConfig()
        return _StyleConfig(
            style_memory_enabled=getattr(config, "style_memory_enabled", True),
            style_owner_profile_enabled=getattr(
                config, "style_owner_profile_enabled", True
            ),
            style_user_profile_enabled=getattr(
                config, "style_user_profile_enabled", True
            ),
            style_relationship_profile_enabled=getattr(
                config, "style_relationship_profile_enabled", True
            ),
            style_context_analysis_enabled=getattr(
                config, "style_context_analysis_enabled", True
            ),
            style_auto_update_enabled=getattr(
                config, "style_auto_update_enabled", True
            ),
            style_max_adaptation_strength=float(
                getattr(config, "style_max_adaptation_strength", 0.45)
            ),
            style_owner_weight=float(getattr(config, "style_owner_weight", 0.60)),
            style_target_weight=float(getattr(config, "style_target_weight", 0.25)),
            style_context_weight=float(getattr(config, "style_context_weight", 0.15)),
            style_debug_logging=bool(getattr(config, "style_debug_logging", False)),
        )

    def _effective_weights(
        self, has_target: bool, has_context: bool
    ) -> dict[str, float]:
        owner = max(self._config.style_owner_weight, 0.0)
        target = max(self._config.style_target_weight if has_target else 0.0, 0.0)
        context = max(self._config.style_context_weight if has_context else 0.0, 0.0)
        total = owner + target + context
        if total <= 0:
            return {"owner": 1.0, "target": 0.0, "context": 0.0}
        return {
            "owner": owner / total,
            "target": target / total,
            "context": context / total,
        }

    def _apply_owner_batch(self, messages: list[str]) -> None:
        analysis = _analyze_messages(messages)
        if not analysis["sample_size"]:
            return
        old_count = self._owner_profile.analyzed_messages
        new_count = analysis["sample_size"]
        profile = OwnerStyleProfile(
            tone=analysis["tone"],
            verbosity=analysis["verbosity"],
            profanity=analysis["profanity"],
            humor=analysis["humor"],
            formality=analysis["formality"],
            punctuation=analysis["punctuation"],
            emoji_usage=analysis["emoji_usage"],
            reply_shape=analysis["reply_shape"],
            directness=analysis["directness"],
            average_message_length=_weighted_average(
                self._owner_profile.average_message_length,
                old_count,
                analysis["avg_message_length"],
                new_count,
            ),
            average_words=_weighted_average(
                self._owner_profile.average_words,
                old_count,
                analysis["avg_words"],
                new_count,
            ),
            punctuation_density=_weighted_average(
                self._owner_profile.punctuation_density,
                old_count,
                analysis["punctuation_density"],
                new_count,
            ),
            slang_score=_weighted_average(
                self._owner_profile.slang_score,
                old_count,
                analysis["slang_score"],
                new_count,
            ),
            formality_score=_weighted_average(
                self._owner_profile.formality_score,
                old_count,
                analysis["formality_score"],
                new_count,
            ),
            directness_score=_weighted_average(
                self._owner_profile.directness_score,
                old_count,
                analysis["directness_score"],
                new_count,
            ),
            analyzed_messages=old_count + new_count,
            common_topics=_merge_topics(
                self._owner_profile.common_topics, analysis["topics"]
            ),
            recent_samples=_limit_samples(
                self._owner_profile.recent_samples, analysis["samples"]
            ),
            last_updated=_utcnow_iso(),
        )
        profile.verbosity = _bucket_verbosity(profile.average_words)
        profile.formality = _bucket_level(profile.formality_score, low=0.20, high=0.55)
        profile.directness = _bucket_directness(profile.directness_score)
        profile.punctuation = _bucket_punctuation(profile.punctuation_density)
        profile.tone = _bucket_tone(
            profile.formality_score,
            _score_from_level(profile.humor),
            _score_from_level(profile.profanity),
        )
        self._owner_profile = profile

    def _apply_user_batch(
        self, *, user_id: int, username: str | None, messages: list[str]
    ) -> None:
        analysis = _analyze_messages(messages)
        if not analysis["sample_size"]:
            return
        key = str(user_id)
        existing = self._user_profiles.get(
            key, UserStyleProfile(user_id=user_id, username=username)
        )
        old_count = existing.sample_size
        new_count = analysis["sample_size"]
        self._user_profiles[key] = UserStyleProfile(
            user_id=user_id,
            username=username or existing.username,
            avg_message_length=_weighted_average(
                existing.avg_message_length,
                old_count,
                analysis["avg_message_length"],
                new_count,
            ),
            tone=analysis["tone"],
            verbosity=_bucket_verbosity(
                _weighted_average(
                    _verbosity_to_words(existing.verbosity),
                    old_count,
                    analysis["avg_words"],
                    new_count,
                )
            ),
            profanity_tolerance=analysis["profanity"],
            humor_level=analysis["humor"],
            formality=analysis["formality"],
            punctuation_style=analysis["punctuation"],
            emoji_usage=analysis["emoji_usage"],
            common_topics=_merge_topics(existing.common_topics, analysis["topics"]),
            last_updated=_utcnow_iso(),
            sample_size=old_count + new_count,
        )

    def _apply_relationship_batch(
        self, *, user_id: int, username: str | None, messages: list[str]
    ) -> None:
        del username
        analysis = _analyze_messages(messages)
        if not analysis["sample_size"]:
            return
        key = str(user_id)
        existing = self._relationship_profiles.get(
            key, RelationshipProfile(user_id=user_id)
        )
        old_count = existing.sample_size
        new_count = analysis["sample_size"]
        avg_words = _weighted_average(
            _verbosity_to_words(existing.preferred_reply_length),
            old_count,
            analysis["avg_words"],
            new_count,
        )
        familiarity_score = _clip(
            (analysis["directness_score"] * 0.45)
            + (0.25 if analysis["formality_score"] < 0.30 else 0.0)
            + (0.30 if avg_words <= 10 else 0.0),
            0.0,
            1.0,
        )
        trust_score = _clip(_safe_div(old_count + new_count, 12.0), 0.0, 1.0)
        max_adaptation = min(
            self._config.style_max_adaptation_strength,
            max(existing.max_adaptation_strength, 0.18 + (trust_score * 0.35)),
        )
        self._relationship_profiles[key] = RelationshipProfile(
            user_id=user_id,
            familiarity=_bucket_level(familiarity_score, low=0.33, high=0.66),
            trust_level=_bucket_level(trust_score, low=0.33, high=0.66),
            banter_allowed=analysis["humor_score"] >= 0.20
            or analysis["profanity_score"] >= 0.10,
            preferred_reply_length=_bucket_verbosity(avg_words),
            preferred_reply_tone=analysis["tone"],
            avoid_profanity=analysis["profanity_score"] < 0.08
            and analysis["formality_score"] >= 0.35,
            max_adaptation_strength=max_adaptation,
            owner_directness=analysis["directness"],
            owner_formality=analysis["formality"],
            owner_humor=analysis["humor"],
            owner_profanity=analysis["profanity"],
            common_topics=_merge_topics(existing.common_topics, analysis["topics"]),
            recent_samples=_limit_samples(existing.recent_samples, analysis["samples"]),
            updated_at=_utcnow_iso(),
            sample_size=old_count + new_count,
        )

    def _resolve_user_profile_locked(
        self, user_id: int | None, username: str | None
    ) -> UserStyleProfile | None:
        if not self._config.style_user_profile_enabled:
            return None
        if user_id is not None:
            profile = self._user_profiles.get(str(user_id))
            if profile:
                return profile
        if username:
            username_key = username.casefold().lstrip("@")
            for profile in self._user_profiles.values():
                if (
                    profile.username
                    and profile.username.casefold().lstrip("@") == username_key
                ):
                    return profile
        return None

    def _resolve_relationship_profile_locked(
        self, user_id: int | None, username: str | None
    ) -> RelationshipProfile | None:
        if not self._config.style_relationship_profile_enabled:
            return None
        if user_id is not None:
            profile = self._relationship_profiles.get(str(user_id))
            if profile:
                return profile
        if username:
            username_key = username.casefold().lstrip("@")
            for key, profile in self._user_profiles.items():
                if (
                    profile.username
                    and profile.username.casefold().lstrip("@") == username_key
                ):
                    return self._relationship_profiles.get(key)
        return None

    def _blend_traits(
        self,
        owner_profile: OwnerStyleProfile,
        user_profile: UserStyleProfile | None,
        relationship_profile: RelationshipProfile | None,
        chat_context_summary: str | None,
        adaptation_strength: float,
    ) -> dict[str, str]:
        short_replies = "short_replies=yes" in (chat_context_summary or "")
        formal_context = "tone=formal" in (chat_context_summary or "")
        playful_context = "tone=playful" in (chat_context_summary or "")
        target_tone = user_profile.tone if user_profile else None
        if (
            playful_context
            and relationship_profile
            and relationship_profile.banter_allowed
        ):
            target_tone = "playful"
        elif formal_context:
            target_tone = "formal"
        tone_source = target_tone or (
            relationship_profile.preferred_reply_tone if relationship_profile else None
        )
        relationship_humor = (
            relationship_profile.owner_humor if relationship_profile else None
        )
        relationship_formality = (
            relationship_profile.owner_formality if relationship_profile else None
        )
        relationship_profanity = (
            relationship_profile.owner_profanity if relationship_profile else None
        )
        relationship_directness = (
            relationship_profile.owner_directness if relationship_profile else None
        )
        profanity = relationship_profanity or owner_profile.profanity
        if relationship_profile and relationship_profile.avoid_profanity:
            profanity = "low"
        elif (
            user_profile
            and user_profile.profanity_tolerance == "high"
            and adaptation_strength >= 0.40
        ):
            profanity = _combine_choice(
                owner_profile.profanity, "medium", adaptation_strength
            )
        humor = relationship_humor or owner_profile.humor
        if relationship_profile and not relationship_profile.banter_allowed:
            humor = "low" if humor == "high" else humor
        elif tone_source == "playful" and adaptation_strength >= 0.30:
            humor = "medium" if owner_profile.humor == "low" else owner_profile.humor
        formality = relationship_formality or owner_profile.formality
        if formal_context:
            formality = (
                "high" if owner_profile.formality != "high" else owner_profile.formality
            )
        elif (
            user_profile
            and user_profile.formality == "high"
            and adaptation_strength >= 0.35
        ):
            formality = (
                "medium"
                if owner_profile.formality == "low"
                else owner_profile.formality
            )
        return {
            "tone": _combine_choice(
                owner_profile.tone, tone_source, adaptation_strength
            ),
            "verbosity": _blend_verbosity(
                owner_profile.verbosity,
                relationship_profile.preferred_reply_length
                if relationship_profile
                else None,
                user_profile.verbosity if user_profile else None,
                short_replies,
            ),
            "profanity": profanity,
            "humor": humor,
            "formality": formality,
            "punctuation": _combine_choice(
                owner_profile.punctuation,
                user_profile.punctuation_style if user_profile else None,
                adaptation_strength * 0.65,
            ),
            "emoji_usage": _combine_choice(
                owner_profile.emoji_usage,
                user_profile.emoji_usage if user_profile else None,
                adaptation_strength * 0.55,
            ),
            "reply_shape": "fragments" if short_replies else owner_profile.reply_shape,
            "directness": "high"
            if short_replies
            else (relationship_directness or owner_profile.directness),
        }

    async def _save_locked(self) -> None:
        payload = {
            "owner_profile": asdict(self._owner_profile),
            "user_profiles": {
                key: asdict(value) for key, value in self._user_profiles.items()
            },
            "relationship_profiles": {
                key: asdict(value) for key, value in self._relationship_profiles.items()
            },
        }
        atomic_write_json_sync(self._path, payload, indent=2)

    def _deserialize_owner_profile(self, payload: dict[str, Any]) -> OwnerStyleProfile:
        raw_formality_score = payload.get("formality_score")
        if raw_formality_score is None and payload.get("informality_score") is not None:
            raw_formality_score = 1.0 - float(
                payload.get("informality_score", 0.0) or 0.0
            )
        return OwnerStyleProfile(
            tone=str(payload.get("tone", "casual")),
            verbosity=str(payload.get("verbosity", "short")),
            profanity=str(payload.get("profanity", "low")),
            humor=str(payload.get("humor", "medium")),
            formality=str(payload.get("formality", "low")),
            punctuation=str(payload.get("punctuation", "light")),
            emoji_usage=str(payload.get("emoji_usage", "low")),
            reply_shape=str(payload.get("reply_shape", "fragments")),
            directness=str(payload.get("directness", "high")),
            average_message_length=float(
                payload.get(
                    "average_message_length", payload.get("average_length", 0.0)
                )
                or 0.0
            ),
            average_words=float(payload.get("average_words", 0.0) or 0.0),
            punctuation_density=float(payload.get("punctuation_density", 0.0) or 0.0),
            slang_score=float(
                payload.get("slang_score", payload.get("slang_frequency", 0.0)) or 0.0
            ),
            formality_score=float(raw_formality_score or 0.0),
            directness_score=float(payload.get("directness_score", 0.0) or 0.0),
            analyzed_messages=int(payload.get("analyzed_messages", 0) or 0),
            common_topics=list(payload.get("common_topics", [])),
            recent_samples=list(
                payload.get("recent_samples", payload.get("recent_messages", []))
            )[-RECENT_SAMPLE_LIMIT:],
            last_updated=payload.get("last_updated"),
        )

    def _deserialize_user_profile(self, payload: dict[str, Any]) -> UserStyleProfile:
        return UserStyleProfile(
            user_id=int(payload.get("user_id", 0) or 0),
            username=payload.get("username"),
            avg_message_length=float(payload.get("avg_message_length", 0.0) or 0.0),
            tone=str(payload.get("tone", "casual")),
            verbosity=str(payload.get("verbosity", "medium")),
            profanity_tolerance=str(payload.get("profanity_tolerance", "medium")),
            humor_level=str(payload.get("humor_level", "medium")),
            formality=str(payload.get("formality", "low")),
            punctuation_style=str(payload.get("punctuation_style", "light")),
            emoji_usage=str(payload.get("emoji_usage", "low")),
            common_topics=list(payload.get("common_topics", [])),
            last_updated=payload.get("last_updated"),
            sample_size=int(payload.get("sample_size", 0) or 0),
        )

    def _deserialize_relationship_profile(
        self, payload: dict[str, Any]
    ) -> RelationshipProfile:
        return RelationshipProfile(
            user_id=int(payload.get("user_id", 0) or 0),
            familiarity=str(payload.get("familiarity", "medium")),
            trust_level=str(payload.get("trust_level", "medium")),
            banter_allowed=bool(payload.get("banter_allowed", False)),
            preferred_reply_length=str(payload.get("preferred_reply_length", "medium")),
            preferred_reply_tone=str(payload.get("preferred_reply_tone", "casual")),
            avoid_profanity=bool(payload.get("avoid_profanity", False)),
            max_adaptation_strength=float(
                payload.get("max_adaptation_strength", 0.45) or 0.45
            ),
            owner_directness=str(payload.get("owner_directness", "medium")),
            owner_formality=str(payload.get("owner_formality", "low")),
            owner_humor=str(payload.get("owner_humor", "medium")),
            owner_profanity=str(payload.get("owner_profanity", "low")),
            common_topics=list(payload.get("common_topics", [])),
            recent_samples=list(payload.get("recent_samples", [])),
            updated_at=payload.get("updated_at"),
            sample_size=int(payload.get("sample_size", 0) or 0),
        )
