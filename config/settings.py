from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ai.model_pool import (
    DEFAULT_ACTIVE_MODEL,
    DEFAULT_ENABLED_MODELS,
    DEFAULT_JUDGE_MODEL,
    DEFAULT_MODEL_NAMES,
)
from config.prompts import BASE_SYSTEM_PROMPT, MODEL_PROMPT_PATCHES


API_ID = ""
API_HASH = ""
USERBOT_SESSION = "userbot_session"

CONTROL_BOT_TOKEN = ""

GROQ_API_KEY = ""
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v1"
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
DUCKDUCKGO_INSTANT_URL = "https://api.duckduckgo.com/"
DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"
WIKIPEDIA_API_URL = "https://ru.wikipedia.org/w/api.php"
GITHUB_SEARCH_API_URL = "https://api.github.com/search/repositories"
SEARXNG_SEARCH_URL = "http://127.0.0.1:8080/search"
ENABLE_DUCKDUCKGO_SEARCH = True
ENABLE_GOOGLE_SEARCH = True
ENABLE_WIKIPEDIA_SEARCH = True
ENABLE_NEWSPAPER_EXTRACTION = True
ENABLE_GITHUB_SEARCH = True
ENABLE_SEARXNG_SEARCH = True
GOOGLE_SEARCH_PAUSE_SECONDS = 2.0
SEARCH_ARTICLE_EXTRACT_LIMIT = 2
SEARCH_TOP_K = 5
STYLE_MEMORY_ENABLED = True
STYLE_OWNER_PROFILE_ENABLED = True
STYLE_USER_PROFILE_ENABLED = True
STYLE_RELATIONSHIP_PROFILE_ENABLED = True
STYLE_CONTEXT_ANALYSIS_ENABLED = True
STYLE_AUTO_UPDATE_ENABLED = True
STYLE_MAX_ADAPTATION_STRENGTH = 0.45
STYLE_OWNER_WEIGHT = 0.60
STYLE_TARGET_WEIGHT = 0.25
STYLE_CONTEXT_WEIGHT = 0.15
STYLE_DEBUG_LOGGING = False
LIVE_DATA_ENABLED = True
LIVE_DATA_TIMEOUT_SECONDS = 20.0
LIVE_DATA_USER_AGENT = "TelegramAIAssistant/1.0"

OWNER_USER_ID = 0
OWNER_REFERENCE_ALIASES = ["@example_owner", "Project Owner", "Owner"]

COMMAND_TRIGGER_ALIASES = ["Assistant", "assistant", "bot"]
COMMAND_DOT_PREFIX_REQUIRED = True
DEFAULT_COMMAND_MODE_ENABLED = True
DEFAULT_AUTO_REPLY_ENABLED = False
DEFAULT_FALLBACK_ENABLED = True
REJECT_LIVE_DATA_REQUESTS = False
STRICT_OUTGOING_ONLY = True
ALLOW_INCOMING_TRIGGER_COMMANDS = False

PLACEHOLDER_TEXT = "[ Project Assistant: Processing Input... ]"
RESPONSE_SENT_TEXT = "[ Project Assistant: Response sent below ]"
LIVE_DATA_UNAVAILABLE_TEXT = (
    "\u0421\u0435\u0439\u0447\u0430\u0441 \u0443 \u043c\u0435\u043d\u044f \u043d\u0435\u0442 "
    "\u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u043d\u043e\u0433\u043e live-\u0434\u043e\u0441\u0442\u0443\u043f\u0430 "
    "\u043a \u0430\u043a\u0442\u0443\u0430\u043b\u044c\u043d\u044b\u043c \u0434\u0430\u043d\u043d\u044b\u043c, "
    "\u043f\u043e\u044d\u0442\u043e\u043c\u0443 \u044f \u043d\u0435 \u043c\u043e\u0433\u0443 \u043d\u0430\u0434\u0451\u0436\u043d\u043e "
    "\u043e\u0442\u0432\u0435\u0442\u0438\u0442\u044c \u043d\u0430 \u0442\u0430\u043a\u043e\u0439 \u0437\u0430\u043f\u0440\u043e\u0441."
)

DEFAULT_REPLY_PROBABILITY = 0.35
DEFAULT_REPLY_COOLDOWN_SECONDS = 120
DEFAULT_REPLY_MIN_DELAY_SECONDS = 6
DEFAULT_REPLY_MAX_DELAY_SECONDS = 16
DEFAULT_REPLY_HOURLY_LIMIT = 15
DEFAULT_REPLY_MIN_MESSAGE_LENGTH = 8
DEFAULT_ALLOW_BOT_REPLIES = False
DEFAULT_DUPLICATE_WINDOW_SECONDS = 120

DEFAULT_CONTEXT_WINDOW_SIZE = 30
DEFAULT_CONTEXT_SCAN_LIMIT = 120
DEFAULT_CONVERSATION_WINDOW = 5
DEFAULT_SUMMARY_ENABLED = True
DEFAULT_CROSS_CHAT_ALLOWED = True
DEFAULT_SUMMARY_MESSAGE_LIMIT = 30
MIN_MEANINGFUL_MESSAGE_LENGTH = 3
MAX_CONSECUTIVE_AI_REPLIES = 2
USER_REPLY_COOLDOWN_SECONDS = 420
DEFAULT_RESPONSE_STYLE_MODE = "NORMAL"
LIVE_CACHE_WEATHER_TTL_SECONDS = 600
LIVE_CACHE_RATES_TTL_SECONDS = 300
LIVE_CACHE_NEWS_TTL_SECONDS = 600
LIVE_CACHE_SEARCH_TTL_SECONDS = 180

VISITOR_MODE_ENABLED = False
VISITOR_PRIMARY_MODEL = "qwen/qwen3-32b"
VISITOR_MAX_CONTEXT_MESSAGES = 12
VISITOR_MAX_OUTPUT_TOKENS = 700
VISITOR_TEMPERATURE = 0.4
VISITOR_ALLOW_GENERAL_CHAT = False
VISITOR_OFFTOPIC_STRICTNESS = "high"
VISITOR_SESSION_TIMEOUT_MINUTES = 30
VISITOR_JUDGE_ENABLED = True
VISITOR_JUDGE_MODEL = "openai/gpt-oss-safeguard-20b"
VISITOR_JUDGE_REPEAT_THRESHOLD = 2
VISITOR_JUDGE_REPEAT_WINDOW_SECONDS = 259200
VISITOR_JUDGE_ALERT_COOLDOWN_SECONDS = 43200


@dataclass(slots=True)
class AppConfig:
    api_id: int
    api_hash: str
    userbot_session: str
    control_bot_token: str
    chat_bot_token: str
    groq_api_key: str
    groq_base_url: str
    open_meteo_geocoding_url: str
    open_meteo_forecast_url: str
    frankfurter_base_url: str
    google_news_rss_url: str
    duckduckgo_instant_url: str
    duckduckgo_html_url: str
    wikipedia_api_url: str
    github_search_api_url: str
    searxng_search_url: str
    github_token: str
    enable_duckduckgo_search: bool
    enable_google_search: bool
    enable_wikipedia_search: bool
    enable_newspaper_extraction: bool
    enable_github_search: bool
    enable_searxng_search: bool
    google_search_pause_seconds: float
    search_article_extract_limit: int
    search_top_k: int
    style_memory_enabled: bool
    style_owner_profile_enabled: bool
    style_user_profile_enabled: bool
    style_relationship_profile_enabled: bool
    style_context_analysis_enabled: bool
    style_auto_update_enabled: bool
    style_max_adaptation_strength: float
    style_owner_weight: float
    style_target_weight: float
    style_context_weight: float
    style_debug_logging: bool
    live_data_enabled: bool
    live_data_timeout_seconds: float
    live_data_user_agent: str
    owner_user_id: int
    owner_reference_aliases: list[str]
    base_dir: Path
    state_path: Path
    style_profile_path: Path
    chat_topics_path: Path
    chat_config_path: Path
    user_profiles_path: Path
    shared_memory_path: Path
    owner_directives_path: Path
    entity_memory_path: Path
    owner_knowledge_path: Path
    model_stats_path: Path
    live_cache_path: Path
    scheduler_path: Path
    monitor_path: Path
    control_bot_session: str
    default_models: list[str]
    default_active_model: str
    default_judge_model: str
    default_enabled_models: dict[str, bool]
    default_trigger_aliases: list[str]
    default_dot_prefix_required: bool
    default_command_mode_enabled: bool
    default_auto_reply_enabled: bool
    default_fallback_enabled: bool
    reject_live_data_requests: bool
    strict_outgoing_only: bool
    allow_incoming_trigger_commands: bool
    placeholder_text: str
    response_sent_text: str
    usage_hint: str
    live_data_unavailable_text: str
    base_system_prompt: str
    system_prompt: str
    model_prompt_patches: dict[str, str]
    openai_timeout_seconds: float
    max_output_tokens: int
    auto_reply_max_output_tokens: int
    default_reply_probability: float
    default_reply_cooldown_seconds: int
    default_reply_min_delay_seconds: int
    default_reply_max_delay_seconds: int
    default_reply_hourly_limit: int
    default_reply_min_message_length: int
    default_allow_bot_replies: bool
    duplicate_window_seconds: int
    default_context_window_size: int
    default_context_scan_limit: int
    default_conversation_window: int
    default_summary_enabled: bool
    default_cross_chat_allowed: bool
    default_summary_message_limit: int
    min_meaningful_message_length: int
    max_consecutive_ai_replies: int
    user_reply_cooldown_seconds: int
    default_response_style_mode: str
    live_cache_weather_ttl_seconds: int
    live_cache_rates_ttl_seconds: int
    live_cache_news_ttl_seconds: int
    live_cache_search_ttl_seconds: int
    visitor_mode_enabled: bool
    visitor_primary_model: str
    visitor_max_context_messages: int
    visitor_max_output_tokens: int
    visitor_temperature: float
    visitor_allow_general_chat: bool
    visitor_offtopic_strictness: str
    visitor_session_timeout_minutes: int
    visitor_judge_enabled: bool
    visitor_judge_model: str
    visitor_judge_repeat_threshold: int
    visitor_judge_repeat_window_seconds: int
    visitor_judge_alert_cooldown_seconds: int


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if value.startswith(('"', "'")) and value.endswith(('"', "'")) and len(value) >= 2:
            value = value[1:-1]

        os.environ.setdefault(key, value)


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return list(default)

    items = [item.strip().lstrip(".") for item in value.split(",")]
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item:
            continue
        lowered = item.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(item)
    return normalized or list(default)


def _env_required(name: str, default: str = "") -> str:
    value = os.getenv(name, default).strip()
    if not value:
        raise ValueError(f"Missing required configuration value: {name}")
    return value


def _build_usage_hint(trigger_aliases: list[str], dot_prefix_required: bool) -> str:
    primary = trigger_aliases[0] if trigger_aliases else "ProjectOwner"
    prefix = "." if dot_prefix_required else ""
    return f".\u0434 <\u0432\u0430\u0448 \u0437\u0430\u043f\u0440\u043e\u0441> | .\u043a <\u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435> | {prefix}{primary} <legacy dialogue>"


def load_config() -> AppConfig:
    base_dir = Path(__file__).resolve().parent.parent
    _load_env_file(base_dir / ".env")
    trigger_aliases = _env_list("COMMAND_TRIGGER_ALIASES", COMMAND_TRIGGER_ALIASES)
    dot_prefix_required = _env_flag("COMMAND_DOT_PREFIX_REQUIRED", COMMAND_DOT_PREFIX_REQUIRED)

    return AppConfig(
        api_id=int(_env_required("API_ID", API_ID)),
        api_hash=_env_required("API_HASH", API_HASH),
        userbot_session=os.getenv("USERBOT_SESSION", USERBOT_SESSION),
        control_bot_token=_env_required("CONTROL_BOT_TOKEN", CONTROL_BOT_TOKEN),
        chat_bot_token=os.getenv("CHAT_BOT_TOKEN", ""),
        groq_api_key=_env_required("GROQ_API_KEY", GROQ_API_KEY),
        groq_base_url=os.getenv("GROQ_BASE_URL", GROQ_BASE_URL),
        open_meteo_geocoding_url=os.getenv("OPEN_METEO_GEOCODING_URL", OPEN_METEO_GEOCODING_URL),
        open_meteo_forecast_url=os.getenv("OPEN_METEO_FORECAST_URL", OPEN_METEO_FORECAST_URL),
        frankfurter_base_url=os.getenv("FRANKFURTER_BASE_URL", FRANKFURTER_BASE_URL),
        google_news_rss_url=os.getenv("GOOGLE_NEWS_RSS_URL", GOOGLE_NEWS_RSS_URL),
        duckduckgo_instant_url=os.getenv("DUCKDUCKGO_INSTANT_URL", DUCKDUCKGO_INSTANT_URL),
        duckduckgo_html_url=os.getenv("DUCKDUCKGO_HTML_URL", DUCKDUCKGO_HTML_URL),
        wikipedia_api_url=os.getenv("WIKIPEDIA_API_URL", WIKIPEDIA_API_URL),
        github_search_api_url=os.getenv("GITHUB_SEARCH_API_URL", GITHUB_SEARCH_API_URL),
        searxng_search_url=os.getenv("SEARXNG_SEARCH_URL", SEARXNG_SEARCH_URL),
        github_token=os.getenv("GITHUB_TOKEN", "").strip(),
        enable_duckduckgo_search=_env_flag("ENABLE_DUCKDUCKGO_SEARCH", ENABLE_DUCKDUCKGO_SEARCH),
        enable_google_search=_env_flag("ENABLE_GOOGLE_SEARCH", ENABLE_GOOGLE_SEARCH),
        enable_wikipedia_search=_env_flag("ENABLE_WIKIPEDIA_SEARCH", ENABLE_WIKIPEDIA_SEARCH),
        enable_newspaper_extraction=_env_flag("ENABLE_NEWSPAPER_EXTRACTION", ENABLE_NEWSPAPER_EXTRACTION),
        enable_github_search=_env_flag("ENABLE_GITHUB_SEARCH", ENABLE_GITHUB_SEARCH),
        enable_searxng_search=_env_flag("ENABLE_SEARXNG_SEARCH", ENABLE_SEARXNG_SEARCH),
        google_search_pause_seconds=_env_float("GOOGLE_SEARCH_PAUSE_SECONDS", GOOGLE_SEARCH_PAUSE_SECONDS),
        search_article_extract_limit=_env_int("SEARCH_ARTICLE_EXTRACT_LIMIT", SEARCH_ARTICLE_EXTRACT_LIMIT),
        search_top_k=_env_int("SEARCH_TOP_K", SEARCH_TOP_K),
        style_memory_enabled=_env_flag("STYLE_MEMORY_ENABLED", STYLE_MEMORY_ENABLED),
        style_owner_profile_enabled=_env_flag("STYLE_OWNER_PROFILE_ENABLED", STYLE_OWNER_PROFILE_ENABLED),
        style_user_profile_enabled=_env_flag("STYLE_USER_PROFILE_ENABLED", STYLE_USER_PROFILE_ENABLED),
        style_relationship_profile_enabled=_env_flag(
            "STYLE_RELATIONSHIP_PROFILE_ENABLED",
            STYLE_RELATIONSHIP_PROFILE_ENABLED,
        ),
        style_context_analysis_enabled=_env_flag(
            "STYLE_CONTEXT_ANALYSIS_ENABLED",
            STYLE_CONTEXT_ANALYSIS_ENABLED,
        ),
        style_auto_update_enabled=_env_flag("STYLE_AUTO_UPDATE_ENABLED", STYLE_AUTO_UPDATE_ENABLED),
        style_max_adaptation_strength=_env_float(
            "STYLE_MAX_ADAPTATION_STRENGTH",
            STYLE_MAX_ADAPTATION_STRENGTH,
        ),
        style_owner_weight=_env_float("STYLE_OWNER_WEIGHT", STYLE_OWNER_WEIGHT),
        style_target_weight=_env_float("STYLE_TARGET_WEIGHT", STYLE_TARGET_WEIGHT),
        style_context_weight=_env_float("STYLE_CONTEXT_WEIGHT", STYLE_CONTEXT_WEIGHT),
        style_debug_logging=_env_flag("STYLE_DEBUG_LOGGING", STYLE_DEBUG_LOGGING),
        live_data_enabled=_env_flag("LIVE_DATA_ENABLED", LIVE_DATA_ENABLED),
        live_data_timeout_seconds=_env_float("LIVE_DATA_TIMEOUT_SECONDS", LIVE_DATA_TIMEOUT_SECONDS),
        live_data_user_agent=os.getenv("LIVE_DATA_USER_AGENT", LIVE_DATA_USER_AGENT),
        owner_user_id=int(os.getenv("OWNER_USER_ID", str(OWNER_USER_ID))),
        owner_reference_aliases=_env_list("OWNER_REFERENCE_ALIASES", OWNER_REFERENCE_ALIASES),
        base_dir=base_dir,
        state_path=base_dir / "data" / "state.json",
        style_profile_path=base_dir / "data" / "style_profile.json",
        chat_topics_path=base_dir / "data" / "chat_topics.json",
        chat_config_path=base_dir / "data" / "chat_config.json",
        user_profiles_path=base_dir / "data" / "user_profiles.json",
        shared_memory_path=base_dir / "data" / "shared_memory.json",
        owner_directives_path=base_dir / "data" / "owner_directives.json",
        entity_memory_path=base_dir / "data" / "entity_memory.json",
        owner_knowledge_path=base_dir / "data" / "owner_knowledge.md",
        model_stats_path=base_dir / "data" / "model_stats.json",
        live_cache_path=base_dir / "data" / "live_cache.json",
        scheduler_path=base_dir / "data" / "scheduler.json",
        monitor_path=base_dir / "data" / "monitor.json",
        control_bot_session="control_bot_session",
        default_models=list(DEFAULT_MODEL_NAMES),
        default_active_model=DEFAULT_ACTIVE_MODEL,
        default_judge_model=DEFAULT_JUDGE_MODEL,
        default_enabled_models=dict(DEFAULT_ENABLED_MODELS),
        default_trigger_aliases=trigger_aliases,
        default_dot_prefix_required=dot_prefix_required,
        default_command_mode_enabled=_env_flag("DEFAULT_COMMAND_MODE_ENABLED", DEFAULT_COMMAND_MODE_ENABLED),
        default_auto_reply_enabled=_env_flag("DEFAULT_AUTO_REPLY_ENABLED", DEFAULT_AUTO_REPLY_ENABLED),
        default_fallback_enabled=_env_flag("DEFAULT_FALLBACK_ENABLED", DEFAULT_FALLBACK_ENABLED),
        reject_live_data_requests=_env_flag("REJECT_LIVE_DATA_REQUESTS", REJECT_LIVE_DATA_REQUESTS),
        strict_outgoing_only=_env_flag("STRICT_OUTGOING_ONLY", STRICT_OUTGOING_ONLY),
        allow_incoming_trigger_commands=_env_flag(
            "ALLOW_INCOMING_TRIGGER_COMMANDS",
            ALLOW_INCOMING_TRIGGER_COMMANDS,
        ),
        placeholder_text=PLACEHOLDER_TEXT,
        response_sent_text=RESPONSE_SENT_TEXT,
        usage_hint=_build_usage_hint(trigger_aliases, dot_prefix_required),
        live_data_unavailable_text=LIVE_DATA_UNAVAILABLE_TEXT,
        base_system_prompt=BASE_SYSTEM_PROMPT,
        system_prompt=BASE_SYSTEM_PROMPT,
        model_prompt_patches=dict(MODEL_PROMPT_PATCHES),
        openai_timeout_seconds=30.0,
        max_output_tokens=500,
        auto_reply_max_output_tokens=260,
        default_reply_probability=DEFAULT_REPLY_PROBABILITY,
        default_reply_cooldown_seconds=DEFAULT_REPLY_COOLDOWN_SECONDS,
        default_reply_min_delay_seconds=DEFAULT_REPLY_MIN_DELAY_SECONDS,
        default_reply_max_delay_seconds=DEFAULT_REPLY_MAX_DELAY_SECONDS,
        default_reply_hourly_limit=DEFAULT_REPLY_HOURLY_LIMIT,
        default_reply_min_message_length=DEFAULT_REPLY_MIN_MESSAGE_LENGTH,
        default_allow_bot_replies=DEFAULT_ALLOW_BOT_REPLIES,
        duplicate_window_seconds=DEFAULT_DUPLICATE_WINDOW_SECONDS,
        default_context_window_size=_env_int("DEFAULT_CONTEXT_WINDOW_SIZE", DEFAULT_CONTEXT_WINDOW_SIZE),
        default_context_scan_limit=_env_int("DEFAULT_CONTEXT_SCAN_LIMIT", DEFAULT_CONTEXT_SCAN_LIMIT),
        default_conversation_window=_env_int("DEFAULT_CONVERSATION_WINDOW", DEFAULT_CONVERSATION_WINDOW),
        default_summary_enabled=_env_flag("DEFAULT_SUMMARY_ENABLED", DEFAULT_SUMMARY_ENABLED),
        default_cross_chat_allowed=_env_flag("DEFAULT_CROSS_CHAT_ALLOWED", DEFAULT_CROSS_CHAT_ALLOWED),
        default_summary_message_limit=_env_int("DEFAULT_SUMMARY_MESSAGE_LIMIT", DEFAULT_SUMMARY_MESSAGE_LIMIT),
        min_meaningful_message_length=_env_int("MIN_MEANINGFUL_MESSAGE_LENGTH", MIN_MEANINGFUL_MESSAGE_LENGTH),
        max_consecutive_ai_replies=_env_int("MAX_CONSECUTIVE_AI_REPLIES", MAX_CONSECUTIVE_AI_REPLIES),
        user_reply_cooldown_seconds=_env_int("USER_REPLY_COOLDOWN_SECONDS", USER_REPLY_COOLDOWN_SECONDS),
        default_response_style_mode=os.getenv("DEFAULT_RESPONSE_STYLE_MODE", DEFAULT_RESPONSE_STYLE_MODE).strip().upper() or DEFAULT_RESPONSE_STYLE_MODE,
        live_cache_weather_ttl_seconds=_env_int("LIVE_CACHE_WEATHER_TTL_SECONDS", LIVE_CACHE_WEATHER_TTL_SECONDS),
        live_cache_rates_ttl_seconds=_env_int("LIVE_CACHE_RATES_TTL_SECONDS", LIVE_CACHE_RATES_TTL_SECONDS),
        live_cache_news_ttl_seconds=_env_int("LIVE_CACHE_NEWS_TTL_SECONDS", LIVE_CACHE_NEWS_TTL_SECONDS),
        live_cache_search_ttl_seconds=_env_int("LIVE_CACHE_SEARCH_TTL_SECONDS", LIVE_CACHE_SEARCH_TTL_SECONDS),
        visitor_mode_enabled=_env_flag("VISITOR_MODE_ENABLED", VISITOR_MODE_ENABLED),
        visitor_primary_model=os.getenv("VISITOR_PRIMARY_MODEL", VISITOR_PRIMARY_MODEL),
        visitor_max_context_messages=_env_int("VISITOR_MAX_CONTEXT_MESSAGES", VISITOR_MAX_CONTEXT_MESSAGES),
        visitor_max_output_tokens=_env_int("VISITOR_MAX_OUTPUT_TOKENS", VISITOR_MAX_OUTPUT_TOKENS),
        visitor_temperature=_env_float("VISITOR_TEMPERATURE", VISITOR_TEMPERATURE),
        visitor_allow_general_chat=_env_flag("VISITOR_ALLOW_GENERAL_CHAT", VISITOR_ALLOW_GENERAL_CHAT),
        visitor_offtopic_strictness=os.getenv("VISITOR_OFFTOPIC_STRICTNESS", VISITOR_OFFTOPIC_STRICTNESS).strip().lower() or VISITOR_OFFTOPIC_STRICTNESS,
        visitor_session_timeout_minutes=_env_int("VISITOR_SESSION_TIMEOUT_MINUTES", VISITOR_SESSION_TIMEOUT_MINUTES),
        visitor_judge_enabled=_env_flag("VISITOR_JUDGE_ENABLED", VISITOR_JUDGE_ENABLED),
        visitor_judge_model=os.getenv("VISITOR_JUDGE_MODEL", VISITOR_JUDGE_MODEL).strip() or VISITOR_JUDGE_MODEL,
        visitor_judge_repeat_threshold=_env_int("VISITOR_JUDGE_REPEAT_THRESHOLD", VISITOR_JUDGE_REPEAT_THRESHOLD),
        visitor_judge_repeat_window_seconds=_env_int("VISITOR_JUDGE_REPEAT_WINDOW_SECONDS", VISITOR_JUDGE_REPEAT_WINDOW_SECONDS),
        visitor_judge_alert_cooldown_seconds=_env_int("VISITOR_JUDGE_ALERT_COOLDOWN_SECONDS", VISITOR_JUDGE_ALERT_COOLDOWN_SECONDS),
    )



