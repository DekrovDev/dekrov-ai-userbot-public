from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True, slots=True)
class ModelInfo:
    name: str
    stage: str
    role: str
    order: int
    enabled_by_default: bool = True


MODEL_CATALOG: tuple[ModelInfo, ...] = (
    ModelInfo("llama-3.1-8b-instant", "production", "primary", 10, True),
    ModelInfo("openai/gpt-oss-20b", "production", "secondary", 20, True),
    ModelInfo("llama-3.3-70b-versatile", "production", "fallback", 30, True),
    ModelInfo("meta-llama/llama-4-scout-17b-16e-instruct", "preview", "fallback", 40, True),
    ModelInfo("qwen/qwen3-32b", "preview", "fallback", 50, True),
    ModelInfo("moonshotai/kimi-k2-instruct-0905", "preview", "fallback", 60, True),
    ModelInfo("openai/gpt-oss-120b", "production", "fallback", 70, True),
    ModelInfo("groq/compound", "optional", "optional", 80, False),
    ModelInfo("groq/compound-mini", "optional", "optional", 90, False),
)

MODEL_BY_NAME = {item.name: item for item in MODEL_CATALOG}
DEFAULT_MODEL_NAMES = [item.name for item in MODEL_CATALOG]
DEFAULT_ENABLED_MODELS = {item.name: item.enabled_by_default for item in MODEL_CATALOG}
DEFAULT_ACTIVE_MODEL = "llama-3.1-8b-instant"
DEFAULT_JUDGE_MODEL = "openai/gpt-oss-20b"
FALLBACK_JUDGE_MODEL = "qwen/qwen3-32b"


def production_models() -> list[str]:
    return [item.name for item in MODEL_CATALOG if item.stage == "production"]


def preview_models() -> list[str]:
    return [item.name for item in MODEL_CATALOG if item.stage == "preview"]


def optional_models() -> list[str]:
    return [item.name for item in MODEL_CATALOG if item.stage == "optional"]


def model_stage_label(stage: str) -> str:
    if stage == "production":
        return "прод"
    if stage == "preview":
        return "превью"
    return "опц"


def model_role_rank(model_name: str) -> int:
    info = MODEL_BY_NAME.get(model_name)
    return info.order if info is not None else 9999


def default_enabled_for(model_name: str) -> bool:
    return DEFAULT_ENABLED_MODELS.get(model_name, True)


def limit_is_blocking(limits, now: datetime | None = None) -> bool:
    until = blocked_until(limits, now=now)
    return until is not None and until > (now or datetime.now(timezone.utc))


def blocked_until(limits, now: datetime | None = None) -> datetime | None:
    if limits is None or not getattr(limits, "retry_after", None) or not getattr(limits, "last_updated", None):
        return None

    retry_after = _parse_positive_int(limits.retry_after)
    last_updated = _parse_iso(limits.last_updated)
    if retry_after is None or last_updated is None:
        return None
    return last_updated + timedelta(seconds=retry_after)


def limit_health_score(limits) -> tuple[int, int, int]:
    if limits is None:
        return (-1, -1, -1)

    remaining_requests = _parse_positive_int(getattr(limits, "remaining_requests", None))
    remaining_tokens = _parse_positive_int(getattr(limits, "remaining_tokens", None))
    known_values = int(remaining_requests is not None) + int(remaining_tokens is not None)
    return (
        known_values,
        remaining_requests if remaining_requests is not None else -1,
        remaining_tokens if remaining_tokens is not None else -1,
    )


def sort_models_by_preference(model_names: list[str], model_limits: dict[str, object]) -> list[str]:
    now = datetime.now(timezone.utc)

    def sort_key(model_name: str) -> tuple[int, int, int, int, int, str]:
        limits = model_limits.get(model_name)
        blocking = 1 if limit_is_blocking(limits, now=now) else 0
        known_values, remaining_requests, remaining_tokens = limit_health_score(limits)
        return (
            blocking,
            model_role_rank(model_name),
            -known_values,
            -remaining_requests,
            -remaining_tokens,
            model_name,
        )

    return sorted(model_names, key=sort_key)


def preferred_generator_order(
    *,
    available_models: list[str],
    enabled_models: dict[str, bool],
    active_model: str,
    model_limits: dict[str, object],
) -> list[str]:
    enabled_available = [name for name in available_models if enabled_models.get(name, True)]
    if not enabled_available:
        enabled_available = list(available_models)

    sorted_models = sort_models_by_preference(enabled_available, model_limits)
    now = datetime.now(timezone.utc)
    non_blocked = [name for name in sorted_models if not limit_is_blocking(model_limits.get(name), now=now)]
    blocked = [name for name in sorted_models if limit_is_blocking(model_limits.get(name), now=now)]
    ordered = non_blocked or blocked

    if active_model in ordered and not limit_is_blocking(model_limits.get(active_model), now=now):
        ordered = [active_model] + [name for name in ordered if name != active_model]

    return ordered


def preferred_task_order(task_type: str, model_names: list[str]) -> list[str]:
    normalized_task = str(task_type or "").strip().casefold()
    if not model_names:
        return []
    if normalized_task != "command_understanding":
        return list(model_names)

    preferred_names = [
        "openai/gpt-oss-120b",
        "moonshotai/kimi-k2-instruct-0905",
        "qwen/qwen3-32b",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "openai/gpt-oss-20b",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "groq/compound",
        "groq/compound-mini",
    ]
    seen: set[str] = set()
    ordered: list[str] = []
    for name in preferred_names:
        if name in model_names and name not in seen:
            ordered.append(name)
            seen.add(name)
    for name in model_names:
        if name not in seen:
            ordered.append(name)
            seen.add(name)
    return ordered


def judge_candidates(available_models: list[str], enabled_models: dict[str, bool], current_judge_model: str) -> list[str]:
    candidates: list[str] = []
    for model_name in [current_judge_model, DEFAULT_JUDGE_MODEL, FALLBACK_JUDGE_MODEL]:
        if model_name in available_models and enabled_models.get(model_name, True) and model_name not in candidates:
            candidates.append(model_name)
    return candidates


def _parse_positive_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
