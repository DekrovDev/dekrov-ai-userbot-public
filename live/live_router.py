from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

from config.settings import AppConfig
from live.live_cache import LiveCacheStore
from infra.language_tools import detect_language, tr
from live.rates_tool import RateQuote, RatesTool, RatesToolError
from live.search_tool import SearchHit, SearchTool, SearchToolError
from ai.validator import sanitize_ai_output
from live.weather_tool import WeatherForecast, WeatherTool, WeatherToolError


LOGGER = logging.getLogger("assistant.live")

WEATHER_KEYWORDS = (
    "weather",
    "forecast",
    "temperature",
    "rain",
    "wind",
    "\u043f\u043e\u0433\u043e\u0434",
    "\u043f\u0440\u043e\u0433\u043d\u043e\u0437",
    "\u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442",
    "\u0434\u043e\u0436\u0434",
    "\u0432\u0435\u0442\u0435\u0440",
)
RATES_KEYWORDS = (
    "exchange rate",
    "currency",
    "convert",
    "\u043a\u0443\u0440\u0441 \u0432\u0430\u043b\u044e\u0442",
    "\u043a\u0443\u0440\u0441 \u0434\u043e\u043b\u043b\u0430\u0440",
    "\u043a\u0443\u0440\u0441 \u0435\u0432\u0440\u043e",
    "\u0432\u0430\u043b\u044e\u0442",
    "\u043a\u043e\u043d\u0432\u0435\u0440\u0442",
    "\u0434\u043e\u043b\u043b\u0430\u0440",
    "\u0435\u0432\u0440\u043e",
    "\u0440\u0443\u0431",
    "usd",
    "eur",
    "rub",
    "gbp",
    "cny",
    "jpy",
)
NEWS_KEYWORDS = (
    "news",
    "latest news",
    "latest info",
    "latest information",
    "recent events",
    "headlines",
    "post",
    "posts",
    "article",
    "articles",
    "publication",
    "publications",
    "coverage",
    "info",
    "information",
    "\u043d\u043e\u0432\u043e\u0441\u0442",
    "\u0438\u043d\u0444\u043e",
    "\u0438\u043d\u0444\u0443",
    "\u0438\u043d\u0444\u0430",
    "\u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446",
    "\u043f\u043e\u0441\u0442",
    "\u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446",
    "\u0441\u0442\u0430\u0442\u044c",
    "\u043f\u0438\u0441\u0430\u043b",
    "\u0441\u0432\u0435\u0436\u0438\u0435 \u0441\u043e\u0431\u044b\u0442",
    "\u0447\u0442\u043e \u0441\u043b\u0443\u0447\u0438\u043b\u043e\u0441\u044c",
    "\u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u0441\u043e\u0431\u044b\u0442\u0438\u044f",
)
NEWS_CONTENT_MARKERS = (
    "news",
    "headline",
    "headlines",
    "info",
    "information",
    "post",
    "posts",
    "article",
    "articles",
    "publication",
    "publications",
    "coverage",
    "\u043d\u043e\u0432\u043e\u0441\u0442",
    "\u0438\u043d\u0444\u043e",
    "\u0438\u043d\u0444\u0443",
    "\u0438\u043d\u0444\u0430",
    "\u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446",
    "\u043f\u043e\u0441\u0442",
    "\u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446",
    "\u0441\u0442\u0430\u0442\u044c",
    "\u043f\u0438\u0441\u0430\u043b",
)
TOPIC_MARKERS = (
    " about ",
    " on ",
    " regarding ",
    " about",
    " Ð¿Ñ€Ð¾ ",
    " Ð¾ ",
    " Ð½Ð°ÑÑ‡ÐµÑ‚ ",
)
PRICE_KEYWORDS = (
    "price",
    "current price",
    "how much is",
    "how much does",
    "\u0446\u0435\u043d\u0430",
    "\u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c",
    "\u0441\u043a\u043e\u043b\u044c\u043a\u043e \u0441\u0442\u043e\u0438\u0442",
    "\u0441\u043a\u043e\u043b\u044c\u043a\u043e \u0441\u0435\u0439\u0447\u0430\u0441 \u0441\u0442\u043e\u0438\u0442",
)
TIME_KEYWORDS = (
    "today",
    "tomorrow",
    "now",
    "current",
    "currently",
    "latest",
    "newest",
    "recent",
    "\u0441\u0435\u0433\u043e\u0434\u043d\u044f",
    "\u0437\u0430\u0432\u0442\u0440\u0430",
    "\u0441\u0435\u0439\u0447\u0430\u0441",
    "\u0442\u0435\u043a\u0443\u0449",
    "\u0430\u043a\u0442\u0443\u0430\u043b",
    "\u043f\u043e\u0441\u043b\u0435\u0434\u043d",
    "\u043d\u043e\u0432\u0435\u0439\u0448",
    "\u0441\u0432\u0435\u0436",
)
LOCATION_PREPOSITIONS_RE = re.compile(
    r"^(?:\u0432\u043e?|\u0443|in|for)\s+", re.IGNORECASE
)
LOCATION_TIME_WORDS_RE = re.compile(
    r"\b(?:\u0441\u0435\u0433\u043e\u0434\u043d\u044f|\u0437\u0430\u0432\u0442\u0440\u0430|\u0441\u0435\u0439\u0447\u0430\u0441|\u0442\u0435\u043f\u0435\u0440\u044c|\u0442\u0435\u043a\u0443\u0449\w*|\u0430\u043a\u0442\u0443\u0430\u043b\w*|today|tomorrow|now|currently|current|latest|right now)\b",
    re.IGNORECASE,
)
LOCATION_NOISE_WORDS_RE = re.compile(
    r"\b(?:\u043f\u043e\u0433\u043e\u0434\w*|\u043f\u0440\u043e\u0433\u043d\u043e\u0437\w*|\u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\w*|\u0434\u043e\u0436\u0434\w*|\u0432\u0435\u0442\u0435\u0440\w*|weather|forecast|temperature|rain|wind|what(?:'s| is)?|how(?:'s| is)?|tell me|show me|\u043a\u0430\u043a\w*|\u043a\u0430\u043a\u0430\w*|\u0447\u0442\u043e|\u0431\u0443\u0434\u0435\u0442|\u0441\u043a\u0430\u0436\u0438|\u043f\u043e\u0434\u0441\u043a\u0430\u0436\u0438|\u043f\u043e\u043a\u0430\u0436\u0438|the)\b",
    re.IGNORECASE,
)
LOCATION_TOKEN_RE = re.compile(r"[A-Za-z\u0400-\u04FF'-]+", re.UNICODE)
LOCATION_TRAILING_NOISE_RE = re.compile(
    r"(?i)\b(?:please|pls|\u043f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430|\u0441\u043f\u0430\u0441\u0438\u0431\u043e)\b.*$"
)
LOCATION_STOPWORDS = {
    "in",
    "for",
    "weather",
    "forecast",
    "temperature",
    "rain",
    "wind",
    "today",
    "tomorrow",
    "now",
    "current",
    "currently",
    "latest",
    "what",
    "whats",
    "how",
    "tell",
    "me",
    "show",
    "the",
    "Ð¿Ð¾Ð³Ð¾Ð´Ð°",
    "Ð¿Ñ€Ð¾Ð³Ð½Ð¾Ð·",
    "Ñ‚ÐµÐ¼Ð¿ÐµÑ€Ð°Ñ‚ÑƒÑ€Ð°",
    "Ð´Ð¾Ð¶Ð´ÑŒ",
    "Ð²ÐµÑ‚ÐµÑ€",
    "ÑÐµÐ³Ð¾Ð´Ð½Ñ",
    "Ð·Ð°Ð²Ñ‚Ñ€Ð°",
    "ÑÐµÐ¹Ñ‡Ð°Ñ",
    "Ñ‚ÐµÐ¿ÐµÑ€ÑŒ",
    "Ñ‚ÐµÐºÑƒÑ‰Ð°Ñ",
    "Ñ‚ÐµÐºÑƒÑ‰Ð¸Ð¹",
    "Ð°ÐºÑ‚ÑƒÐ°Ð»ÑŒÐ½Ð°Ñ",
    "Ð°ÐºÑ‚ÑƒÐ°Ð»ÑŒÐ½Ñ‹Ð¹",
    "Ð²",
    "Ð²Ð¾",
    "ÐºÐ°Ðº",
    "ÐºÐ°ÐºÐ°Ñ",
    "ÐºÐ°ÐºÐ¾Ð¹",
    "ÐºÐ°ÐºÐ¾Ðµ",
    "Ñ‡Ñ‚Ð¾",
    "Ð±ÑƒÐ´ÐµÑ‚",
    "ÑÐºÐ°Ð¶Ð¸",
    "Ð¿Ð¾Ð´ÑÐºÐ°Ð¶Ð¸",
    "Ð¿Ð¾ÐºÐ°Ð¶Ð¸",
}
AMOUNT_RE = re.compile(r"(?P<amount>\d+(?:[.,]\d+)?)")
CURRENCY_TOKEN_RE = re.compile(r"[A-Za-z\u0400-\u04FF$â‚¬Â¥]+")

CURRENCY_ALIASES = {
    "usd": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "buck": "USD",
    "bucks": "USD",
    "\u0431\u0430\u043a\u0441": "USD",
    "\u0431\u0430\u043a\u0441\u0430": "USD",
    "\u0431\u0430\u043a\u0441\u0443": "USD",
    "\u0431\u0430\u043a\u0441\u043e\u0432": "USD",
    "\u0434\u043e\u043b\u043b\u0430\u0440": "USD",
    "\u0434\u043e\u043b\u043b\u0430\u0440\u0430": "USD",
    "\u0434\u043e\u043b\u043b\u0430\u0440\u0435": "USD",
    "\u0434\u043e\u043b\u043b\u0430\u0440\u043e\u0432": "USD",
    "$": "USD",
    "eur": "EUR",
    "euro": "EUR",
    "\u0435\u0432\u0440\u043e": "EUR",
    "\u20ac": "EUR",
    "rub": "RUB",
    "ruble": "RUB",
    "rubles": "RUB",
    "\u0440\u0443\u0431": "RUB",
    "\u0440\u0443\u0431\u043b": "RUB",
    "\u0440\u0443\u0431\u043b\u044c": "RUB",
    "\u0440\u0443\u0431\u043b\u044f": "RUB",
    "\u0440\u0443\u0431\u043b\u044e": "RUB",
    "\u0440\u0443\u0431\u043b\u0435\u0439": "RUB",
    "gbp": "GBP",
    "pound": "GBP",
    "\u0444\u0443\u043d\u0442": "GBP",
    "cny": "CNY",
    "\u044e\u0430\u043d\u044c": "CNY",
    "\u044e\u0430\u043d\u044f": "CNY",
    "jpy": "JPY",
    "\u0438\u0435\u043d": "JPY",
    "\u0438\u0435\u043d\u0430": "JPY",
    "chf": "CHF",
    "franc": "CHF",
    "\u0444\u0440\u0430\u043d\u043a": "CHF",
    "try": "TRY",
    "\u043b\u0438\u0440\u0430": "TRY",
    "aed": "AED",
    "dirham": "AED",
    "\u0434\u0438\u0440\u0445\u0430\u043c": "AED",
    "pln": "PLN",
    "\u0437\u043b\u043e\u0442\u044b\u0439": "PLN",
    "kzt": "KZT",
    "\u0442\u0435\u043d\u0433\u0435": "KZT",
}
SEARCH_QUERY_NOISE_PATTERNS = (
    re.compile(
        r"(?iu)\b(?:\u043d\u0430\u0439\u0434\u0438|\u043f\u043e\u0438\u0449\u0438|\u0438\u0449\u0438|\u0437\u0430\u0433\u0443\u0433\u043b\u0438|\u0433\u0443\u0433\u043b\u0438|search|find|look up)\b"
    ),
    re.compile(
        r"(?iu)\b(?:\u0432\u0020\u0433\u0443\u0433\u043b\u0435|\u0432\u0020\u0438\u043d\u0442\u0435\u0440\u043d\u0435\u0442\u0435|\u0432\u0020\u0441\u043e\u0446\u0441\u0435\u0442\u044f\u0445|\u0441\u043e\u0446\u0441\u0435\u0442\u0438|\u0441\u043e\u0446\u0020\u0441\u0435\u0442\u0438|google|internet|online|web|social media|social networks|socials)\b"
    ),
    re.compile(
        r"(?iu)\b(?:\u0432\u0441\u044e|\u0432\u0441\u044f|\u0432\u0441\u0451|\u043c\u0430\u043a\u0441\u0438\u043c\u0430\u043b\u044c\u043d\u043e\u0435|\u043c\u0430\u043a\u0441\u0438\u043c\u0443\u043c|\u043a\u0430\u043a\u0020\u043c\u043e\u0436\u043d\u043e\u0020\u0431\u043e\u043b\u044c\u0448\u0435|\u043a\u0430\u043a\u0020\u043c\u043e\u0436\u043d\u043e\u0020\u0431\u043e\u043b\u044c\u0448\u0435\u0020\u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u0438|all|maximum|maximal|maximum amount of|as much as possible)\b"
    ),
    re.compile(
        r"(?iu)\b(?:\u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u044f|\u0438\u043d\u0444\u043e|information|info|details)\b"
    ),
)
SEARCH_QUERY_ABOUT_RE = re.compile(
    r"(?iu)\b(?:\u043f\u0440\u043e|\u043e\u0431|\u043e|\u043d\u0430\u0441\u0447\u0435\u0442|about|regarding|on)\s+(.+)$"
)


@dataclass(slots=True)
class LiveIntent:
    kind: str
    raw_query: str
    location: str | None = None
    day_offset: int = 0
    amount: float = 1.0
    base_currency: str | None = None
    quote_currency: str | None = None


class LiveDataRouter:
    def __init__(self, config: AppConfig, cache_store: LiveCacheStore) -> None:
        self._config = config
        self._cache_store = cache_store
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=config.live_data_timeout_seconds,
            headers={"User-Agent": config.live_data_user_agent},
        )

        # Rate limiter
        from infra.rate_limiter import RateLimiter, configure_default_limits

        self._limiter = RateLimiter()
        configure_default_limits(self._limiter)

        from live.location_resolver import LocationResolver

        location_resolver = LocationResolver(
            self._client,
            config.open_meteo_geocoding_url,
            cache_dir=config.base_dir / "data",
        )
        self._weather_tool = WeatherTool(
            self._client,
            config,
            location_resolver=location_resolver,
            limiter=self._limiter,
        )
        self._rates_tool = RatesTool(self._client, config, limiter=self._limiter)
        self._search_tool = SearchTool(self._client, config, limiter=self._limiter)

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_page(self, url: str, *, max_chars: int = 4000) -> str | None:
        """Fetch a URL and return cleaned text content. Returns None on failure."""
        if not self._config.live_data_enabled:
            return None
        try:
            resp = await self._client.get(url, timeout=10)
            resp.raise_for_status()
            raw = resp.text or ""
            # Strip HTML tags
            import re

            text = re.sub(
                r"<style[^>]*>.*?</style>", " ", raw, flags=re.DOTALL | re.IGNORECASE
            )
            text = re.sub(
                r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE
            )
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"&[a-z#0-9]+;", " ", text)
            text = re.sub(r"\s{3,}", "\n\n", text)
            text = text.strip()
            return text[:max_chars] if text else None
        except Exception:
            LOGGER.debug("fetch_page_failed url=%s", url, exc_info=True)
            return None

    async def route(
        self, query: str, *, response_style_mode: str = "NORMAL"
    ) -> str | None:
        if not self._config.live_data_enabled:
            LOGGER.debug("live_router_disabled")
            return None

        intent = self.detect_intent(query)
        if intent is None:
            LOGGER.debug("live_router_no_intent query=%s", query[:80])
            return None
        language = detect_language(query)
        variant = str(response_style_mode or "NORMAL").strip().upper()

        cached = await self._cache_store.get(
            kind=intent.kind,
            query=intent.raw_query,
            language=language,
            variant=variant,
        )
        if cached is not None:
            LOGGER.info("live_router_cache_hit kind=%s", intent.kind)
            return cached

        LOGGER.info(
            "live_router_detected kind=%s location=%s",
            intent.kind,
            getattr(intent, "location", None),
        )

        try:
            if intent.kind == "weather":
                if not intent.location:
                    return sanitize_ai_output(
                        self._weather_location_failure_message(language),
                        user_query=query,
                        expected_language=language,
                    )
                forecast = await self._weather_tool.fetch_forecast(
                    intent.location,
                    day_offset=intent.day_offset,
                    language=language,
                )
                result = sanitize_ai_output(
                    self._format_weather(forecast, language),
                    user_query=query,
                    expected_language=language,
                )
                await self._cache_store.set(
                    kind=intent.kind,
                    query=intent.raw_query,
                    language=language,
                    value=result,
                    ttl_seconds=self._config.live_cache_weather_ttl_seconds,
                    variant=variant,
                )
                return result

            if intent.kind == "rates":
                if intent.base_currency is None or intent.quote_currency is None:
                    return sanitize_ai_output(
                        tr("rates_parse_failed", language),
                        user_query=query,
                        expected_language=language,
                    )
                quote = await self._rates_tool.fetch_quote(
                    amount=intent.amount,
                    base_currency=intent.base_currency,
                    quote_currency=intent.quote_currency,
                )
                result = sanitize_ai_output(
                    self._format_rate(quote, language),
                    user_query=query,
                    expected_language=language,
                )
                await self._cache_store.set(
                    kind=intent.kind,
                    query=intent.raw_query,
                    language=language,
                    value=result,
                    ttl_seconds=self._config.live_cache_rates_ttl_seconds,
                    variant=variant,
                )
                return result

            if intent.kind == "news":
                hits = await self._search_tool.search_news(
                    intent.raw_query,
                    limit=self._result_limit(variant),
                    language=language,
                )
                if not hits:
                    return sanitize_ai_output(
                        tr("news_not_found", language),
                        user_query=query,
                        expected_language=language,
                    )
                result = sanitize_ai_output(
                    self._format_news(hits, language),
                    user_query=query,
                    expected_language=language,
                )
                await self._cache_store.set(
                    kind=intent.kind,
                    query=intent.raw_query,
                    language=language,
                    value=result,
                    ttl_seconds=self._config.live_cache_news_ttl_seconds,
                    variant=variant,
                )
                return result

            if intent.kind == "search":
                hits = await self._search_tool.search_web(
                    intent.raw_query, limit=self._result_limit(variant)
                )
                if not hits:
                    hits = await self._search_tool.search_news(
                        intent.raw_query,
                        limit=self._result_limit(variant),
                        language=language,
                    )
                if not hits:
                    return sanitize_ai_output(
                        tr("search_not_found", language),
                        user_query=query,
                        expected_language=language,
                    )
                result = sanitize_ai_output(
                    self._format_search(hits, language),
                    user_query=query,
                    expected_language=language,
                )
                await self._cache_store.set(
                    kind=intent.kind,
                    query=intent.raw_query,
                    language=language,
                    value=result,
                    ttl_seconds=self._config.live_cache_search_ttl_seconds,
                    variant=variant,
                )
                return result
        except (
            httpx.HTTPError,
            WeatherToolError,
            RatesToolError,
            SearchToolError,
        ) as exc:
            LOGGER.exception("live_router_request_failed kind=%s", intent.kind)
            if (
                intent.kind == "weather"
                and isinstance(exc, WeatherToolError)
                and str(exc) == "location_not_found"
            ):
                return sanitize_ai_output(
                    self._weather_location_failure_message(language),
                    user_query=query,
                    expected_language=language,
                )
            if intent.kind == "rates" and isinstance(exc, RatesToolError):
                return sanitize_ai_output(
                    self._rates_failure_message(language, str(exc)),
                    user_query=query,
                    expected_language=language,
                )
            return sanitize_ai_output(
                tr("live_data_failed", language),
                user_query=query,
                expected_language=language,
            )
        except Exception as exc:
            from live.location_resolver import LocationResolverError

            LOGGER.exception("live_router_unexpected_error kind=%s", intent.kind)
            if intent.kind == "weather" and isinstance(exc, LocationResolverError):
                if exc.suggestions:
                    suggestions_text = ", ".join(exc.suggestions[:3])
                    msg = self._weather_location_failure_message(language)
                    if language in ("ru", "uk"):
                        return sanitize_ai_output(
                            f"{msg} \u0412\u043e\u0437\u043c\u043e\u0436\u043d\u043e, \u0432\u044b \u0438\u043c\u0435\u043b\u0438 \u0432 \u0432\u0438\u0434\u0443: {suggestions_text}",
                            user_query=query,
                            expected_language=language,
                        )
                    return sanitize_ai_output(
                        f"{msg} Maybe you meant: {suggestions_text}",
                        user_query=query,
                        expected_language=language,
                    )
                return sanitize_ai_output(
                    self._weather_location_failure_message(language),
                    user_query=query,
                    expected_language=language,
                )
            return None

        return sanitize_ai_output(
            tr("live_data_failed", language),
            user_query=query,
            expected_language=language,
        )

    async def search_web_query(
        self, query: str, *, response_style_mode: str = "NORMAL"
    ) -> str:
        normalized_query = " ".join((query or "").split()).strip()
        language = detect_language(normalized_query)
        variant = str(response_style_mode or "NORMAL").strip().upper()
        query_candidates = self._build_search_query_candidates(normalized_query)

        for candidate_query in query_candidates:
            cached = await self._cache_store.get(
                kind="search",
                query=candidate_query,
                language=language,
                variant=variant,
            )
            if cached is not None:
                LOGGER.info("live_router_cache_hit kind=search_explicit")
                return cached

            try:
                hits = await self._search_tool.search_web(
                    candidate_query, limit=self._result_limit(variant)
                )
                if not hits and self._should_use_news_fallback_for_explicit_search(
                    candidate_query
                ):
                    hits = await self._search_tool.search_news(
                        candidate_query,
                        limit=self._result_limit(variant),
                        language=language,
                    )
            except (httpx.HTTPError, SearchToolError):
                LOGGER.exception(
                    "live_router_explicit_search_failed query=%s", candidate_query
                )
                continue

            if not hits:
                continue

            result = sanitize_ai_output(
                self._format_search(hits, language),
                user_query=candidate_query,
                expected_language=language,
            )
            await self._cache_store.set(
                kind="search",
                query=candidate_query,
                language=language,
                value=result,
                ttl_seconds=self._config.live_cache_search_ttl_seconds,
                variant=variant,
            )
            return result

        if not query_candidates:
            return sanitize_ai_output(
                tr("search_not_found", language),
                user_query=normalized_query,
                expected_language=language,
            )
        return sanitize_ai_output(
            tr("search_not_found", language),
            user_query=query_candidates[-1],
            expected_language=language,
        )

    async def build_web_grounding_block(
        self, query: str, *, response_style_mode: str = "NORMAL"
    ) -> str | None:
        normalized_query = " ".join((query or "").split()).strip()
        if not normalized_query:
            return None
        language = detect_language(normalized_query)
        variant = str(response_style_mode or "NORMAL").strip().upper()
        limit = max(3, self._result_limit(variant) + 1)

        for candidate_query in self._build_search_query_candidates(normalized_query):
            try:
                hits = await self._search_tool.search_web(candidate_query, limit=limit)
                if not hits and self._should_use_news_fallback_for_explicit_search(
                    candidate_query
                ):
                    hits = await self._search_tool.search_news(
                        candidate_query, limit=limit, language=language
                    )
            except (httpx.HTTPError, SearchToolError):
                LOGGER.exception(
                    "live_router_grounding_failed query=%s", candidate_query
                )
                continue
            if not hits:
                continue
            block = self._format_search_grounding_block(candidate_query, hits)
            if block:
                return block
        return None

    def _result_limit(self, response_style_mode: str) -> int:
        mode = str(response_style_mode or "NORMAL").strip().upper()
        if mode == "SHORT":
            return 2
        if mode == "DETAILED":
            return 4
        return 3

    def _build_search_query_candidates(self, query: str) -> list[str]:
        normalized = " ".join((query or "").split()).strip()
        if not normalized:
            return []
        candidates: list[str] = []
        seen: set[str] = set()

        def add(value: str) -> None:
            cleaned = " ".join((value or "").split()).strip(" .,!?:;")
            if len(cleaned) < 2:
                return
            lowered = cleaned.casefold()
            if lowered in seen:
                return
            seen.add(lowered)
            candidates.append(cleaned)

        add(normalized)

        simplified = normalized
        for pattern in SEARCH_QUERY_NOISE_PATTERNS:
            simplified = pattern.sub(" ", simplified)
        simplified = " ".join(simplified.split()).strip(" .,!?:;")
        if simplified:
            add(simplified)

        about_match = SEARCH_QUERY_ABOUT_RE.search(normalized)
        if about_match:
            add(about_match.group(1))

        if simplified:
            about_match = SEARCH_QUERY_ABOUT_RE.search(simplified)
            if about_match:
                add(about_match.group(1))

        return candidates

    def _should_use_news_fallback_for_explicit_search(self, query: str) -> bool:
        lowered = (query or "").casefold()
        explicit_news_markers = (
            "news",
            "latest news",
            "headline",
            "headlines",
            "Ð½Ð¾Ð²Ð¾ÑÑ‚",
            "ÑÐ²ÐµÐ¶Ð¸Ðµ Ð½Ð¾Ð²Ð¾ÑÑ‚Ð¸",
            "Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ðµ Ð½Ð¾Ð²Ð¾ÑÑ‚Ð¸",
            "Ñ‡Ñ‚Ð¾ ÑÐ»ÑƒÑ‡Ð¸Ð»Ð¾ÑÑŒ",
            "latest headlines",
        )
        return any(marker in lowered for marker in explicit_news_markers)

    def _format_search_grounding_block(self, query: str, hits: list[SearchHit]) -> str:
        lines = [
            "Web search results fetched before answering:",
            f"Query: {query}",
            "Use these results for factual grounding. Prefer them over memory when they are relevant. If they conflict or look insufficient, say so briefly.",
        ]
        for index, hit in enumerate(hits[:5], start=1):
            title = (hit.title or "").strip() or f"Result {index}"
            snippet = (hit.snippet or "").strip()
            source_parts = [
                part for part in [hit.source, hit.url, hit.published_at] if part
            ]
            source_line = (
                f" Source: {' | '.join(source_parts)}." if source_parts else ""
            )
            if snippet:
                lines.append(f"{index}. {title}. {snippet}.{source_line}")
            else:
                lines.append(f"{index}. {title}.{source_line}")
        return "\n".join(lines).strip()

    def detect_intent(self, query: str) -> LiveIntent | None:
        normalized = " ".join((query or "").split())
        lowered = normalized.casefold()

        if self._is_weather_query(lowered):
            location = self._extract_location(normalized)
            day_offset = (
                1
                if any(
                    token in lowered
                    for token in ("tomorrow", "\u0437\u0430\u0432\u0442\u0440\u0430")
                )
                else 0
            )
            return LiveIntent(
                kind="weather",
                raw_query=normalized,
                location=location,
                day_offset=day_offset,
            )

        if self._is_rates_query(lowered):
            amount, base_currency, quote_currency = self._extract_currency_request(
                normalized
            )
            return LiveIntent(
                kind="rates",
                raw_query=normalized,
                amount=amount,
                base_currency=base_currency,
                quote_currency=quote_currency,
            )

        if self._is_news_query(lowered):
            return LiveIntent(kind="news", raw_query=normalized)

        if self._is_price_or_current_search_query(lowered):
            return LiveIntent(kind="search", raw_query=normalized)

        return None

    def _is_weather_query(self, lowered_query: str) -> bool:
        return any(keyword in lowered_query for keyword in WEATHER_KEYWORDS)

    def _is_rates_query(self, lowered_query: str) -> bool:
        if any(keyword in lowered_query for keyword in RATES_KEYWORDS):
            return True
        codes = self._extract_currency_codes(lowered_query)
        return len(codes) >= 2

    def _is_news_query(self, lowered_query: str) -> bool:
        if any(keyword in lowered_query for keyword in NEWS_KEYWORDS):
            return True
        if any(token in lowered_query for token in TIME_KEYWORDS) and any(
            token in lowered_query
            for token in (
                "info",
                "information",
                "about",
                "\u0438\u043d\u0444\u043e",
                "\u0438\u043d\u0444\u0443",
                "\u0438\u043d\u0444\u0430",
                "\u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446",
                "\u043f\u0440\u043e ",
                "\u043e\u0431 ",
            )
        ):
            return True
        has_time_context = any(token in lowered_query for token in TIME_KEYWORDS)
        has_news_content = any(
            marker in lowered_query for marker in NEWS_CONTENT_MARKERS
        )
        if has_time_context and has_news_content:
            return True
        return has_time_context and any(
            marker in lowered_query for marker in TOPIC_MARKERS
        )

    def _is_price_or_current_search_query(self, lowered_query: str) -> bool:
        if any(keyword in lowered_query for keyword in PRICE_KEYWORDS):
            return True
        if any(
            token in lowered_query
            for token in ("\u0441\u0435\u0439\u0447\u0430\u0441", "now", "current")
        ) and any(
            marker in lowered_query
            for marker in (
                "\u0441\u0442\u043e\u0438\u0442",
                "\u0446\u0435\u043d",
                "\u0441\u0442\u043e\u0438\u043c",
                "price",
                "cost",
            )
        ):
            return True
        return any(token in lowered_query for token in TIME_KEYWORDS) and any(
            keyword in lowered_query
            for keyword in (
                "price",
                "\u0446\u0435\u043d",
                "\u0441\u0442\u043e\u0438\u043c",
                "\u0441\u043e\u0431\u044b\u0442",
                "\u043d\u043e\u0432\u043e\u0441\u0442",
            )
        )

    def _extract_location(self, query: str) -> str | None:
        patterns = (
            r"(?:\u043f\u043e\u0433\u043e\u0434[^\n]{0,120}?|\u043f\u0440\u043e\u0433\u043d\u043e\u0437[^\n]{0,120}?|weather[^\n]{0,120}?|forecast[^\n]{0,120}?)(?:\u0432\u043e?|in|for)\s+(.+?)(?:$|[?.!,])",
            r"(?:\u0432\u043e?|in|for)\s+(.+?)(?:$|[?.!,])",
            r"^(?:weather|forecast|\u043f\u043e\u0433\u043e\u0434\w*|\u043f\u0440\u043e\u0433\u043d\u043e\u0437\w*)\s+(.+)$",
            r"^(.+?)\s+(?:weather|forecast|\u043f\u043e\u0433\u043e\u0434\w*|\u043f\u0440\u043e\u0433\u043d\u043e\u0437\w*)$",
        )
        for pattern in patterns:
            match = re.search(pattern, query, flags=re.IGNORECASE)
            if not match:
                continue
            candidate = self._clean_location_candidate(match.group(1))
            if candidate:
                return candidate
        return self._fallback_location_candidate(query)

    def _clean_location_candidate(self, candidate: str) -> str | None:
        cleaned = " ".join((candidate or "").split()).strip(" ,.-")
        if not cleaned:
            return None
        cleaned = LOCATION_PREPOSITIONS_RE.sub("", cleaned)
        cleaned = LOCATION_TRAILING_NOISE_RE.sub("", cleaned)
        cleaned = LOCATION_TIME_WORDS_RE.sub(" ", cleaned)
        cleaned = LOCATION_NOISE_WORDS_RE.sub(" ", cleaned)
        cleaned = re.sub(r"[\"'`()\[\]]", " ", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.-")
        if not cleaned:
            return None
        return cleaned

    def _fallback_location_candidate(self, query: str) -> str | None:
        tokens = [
            token
            for token in LOCATION_TOKEN_RE.findall(query or "")
            if token.casefold() not in LOCATION_STOPWORDS
        ]
        if not tokens:
            return None
        candidate = " ".join(tokens)
        candidate = self._clean_location_candidate(candidate)
        if not candidate:
            return None
        if len(candidate) < 2:
            return None
        return candidate

    def _weather_location_failure_message(self, language: str) -> str:
        if language == "ru":
            return "ÐÐµ Ð¿Ð¾Ð»ÑƒÑ‡Ð¸Ð»Ð¾ÑÑŒ Ð¾Ð¿Ñ€ÐµÐ´ÐµÐ»Ð¸Ñ‚ÑŒ Ð»Ð¾ÐºÐ°Ñ†Ð¸ÑŽ Ð´Ð»Ñ Ð¿Ñ€Ð¾Ð³Ð½Ð¾Ð·Ð°."
        if language == "uk":
            return "ÐÐµ Ð²Ð´Ð°Ð»Ð¾ÑÑ Ð²Ð¸Ð·Ð½Ð°Ñ‡Ð¸Ñ‚Ð¸ Ð»Ð¾ÐºÐ°Ñ†Ñ–ÑŽ Ð´Ð»Ñ Ð¿Ñ€Ð¾Ð³Ð½Ð¾Ð·Ñƒ."
        if language == "it":
            return "Non sono riuscito a capire la localita per il meteo."
        if language == "es":
            return "No pude determinar la ubicacion para el pronostico."
        if language == "fr":
            return "Je n'ai pas reussi a determiner le lieu pour la meteo."
        if language == "de":
            return (
                "Ich konnte den Ort fuer die Wettervorhersage nicht eindeutig erkennen."
            )
        return "I couldn't determine the location for the forecast."

    def _rates_failure_message(self, language: str, error_code: str) -> str:
        if error_code.startswith("unsupported_base:"):
            code = error_code.split(":", 1)[1] or "?"
            if language == "ru":
                return f"\u0412 Frankfurter \u0441\u0435\u0439\u0447\u0430\u0441 \u043d\u0435\u0442 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0438 \u0431\u0430\u0437\u043e\u0432\u043e\u0439 \u0432\u0430\u043b\u044e\u0442\u044b {code}."
            return f"Frankfurter does not currently support {code} as a base currency."
        if error_code.startswith("unsupported_quote:"):
            code = error_code.split(":", 1)[1] or "?"
            if language == "ru":
                return f"\u0412 Frankfurter \u0441\u0435\u0439\u0447\u0430\u0441 \u043d\u0435\u0442 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0438 \u0432\u0430\u043b\u044e\u0442\u044b {code}."
            return f"Frankfurter does not currently support the currency {code}."
        if error_code == "currencies_unavailable":
            if language == "ru":
                return "\u041d\u0435 \u043f\u043e\u043b\u0443\u0447\u0438\u043b\u043e\u0441\u044c \u0443\u0442\u043e\u0447\u043d\u0438\u0442\u044c \u0441\u043f\u0438\u0441\u043e\u043a \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0445 \u0432\u0430\u043b\u044e\u0442 \u0443 Frankfurter."
            return "I couldn't fetch the list of supported currencies from Frankfurter."
        if error_code == "rate_not_found":
            if language == "ru":
                return "\u041d\u0435 \u043f\u043e\u043b\u0443\u0447\u0438\u043b\u043e\u0441\u044c \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u043a\u0443\u0440\u0441 \u0434\u043b\u044f \u044d\u0442\u043e\u0439 \u043f\u0430\u0440\u044b \u0432\u0430\u043b\u044e\u0442."
            return "I couldn't fetch a rate for that currency pair."
        return tr("live_data_failed", language)

    def _extract_currency_request(
        self, query: str
    ) -> tuple[float, str | None, str | None]:
        lowered = query.casefold()
        amount_match = AMOUNT_RE.search(lowered)
        amount = 1.0
        if amount_match:
            amount = float(amount_match.group("amount").replace(",", "."))

        base_currency, quote_currency = self._extract_directional_currency_pair(lowered)
        if base_currency is None or quote_currency is None:
            codes = self._extract_currency_codes(lowered)
            base_currency = base_currency or (codes[0] if codes else None)
            quote_currency = quote_currency or (codes[1] if len(codes) >= 2 else None)

        if base_currency and quote_currency is None:
            quote_currency = "EUR" if base_currency != "EUR" else "USD"

        return amount, base_currency, quote_currency

    def _extract_currency_codes(self, text: str) -> list[str]:
        codes: list[str] = []
        seen: set[str] = set()
        for token in CURRENCY_TOKEN_RE.findall(text):
            normalized = CURRENCY_ALIASES.get(token.casefold())
            if normalized is None:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            codes.append(normalized)
        return codes

    def _extract_directional_currency_pair(
        self, text: str
    ) -> tuple[str | None, str | None]:
        matches: list[tuple[int, int, str]] = []
        seen_positions: set[tuple[int, int, str]] = set()
        for token_match in CURRENCY_TOKEN_RE.finditer(text or ""):
            normalized = CURRENCY_ALIASES.get(token_match.group(0).casefold())
            if normalized is None:
                continue
            candidate = (token_match.start(), token_match.end(), normalized)
            if candidate in seen_positions:
                continue
            seen_positions.add(candidate)
            matches.append(candidate)
        if len(matches) < 2:
            return None, None

        for index in range(len(matches) - 1):
            first = matches[index]
            second = matches[index + 1]
            between = text[first[1] : second[0]]
            if re.search(r"(?iu)\b(?:Ðº|to|against|vs)\b", between):
                return first[2], second[2]
            if re.search(r"(?iu)\b(?:Ð²|in)\s+(?:Ð¾Ð´Ð½Ð¾Ð¼|one|1)\b", between):
                return second[2], first[2]
            if re.search(r"(?iu)\b(?:Ð·Ð°|for)\b", between):
                return second[2], first[2]
        return None, None

    def _format_weather(self, forecast: WeatherForecast, language: str) -> str:
        location = forecast.location.label
        min_temp = self._format_temperature(forecast.temperature_min)
        max_temp = self._format_temperature(forecast.temperature_max)
        wind = self._format_wind(forecast.wind_speed)
        precipitation = self._format_percent(forecast.precipitation_probability)

        if forecast.day_offset == 0:
            current_temp = self._format_temperature(forecast.temperature_current)
            parts = [
                tr(
                    "weather_now",
                    language,
                    location=location,
                    condition=forecast.condition,
                )
            ]
            if current_temp:
                parts.append(f"{current_temp}")
            if min_temp or max_temp:
                temp_range = " / ".join(part for part in [min_temp, max_temp] if part)
                if temp_range:
                    parts.append(tr("weather_for_day", language, temp_range=temp_range))
            if precipitation:
                parts.append(
                    tr("weather_precip_chance", language, precipitation=precipitation)
                )
            if wind:
                parts.append(tr("weather_wind", language, wind=wind))
            return ", ".join(parts) + "."

        parts = [
            tr(
                "weather_tomorrow",
                language,
                location=location,
                condition=forecast.condition,
            )
        ]
        if min_temp or max_temp:
            temp_range = " / ".join(part for part in [min_temp, max_temp] if part)
            if temp_range:
                parts.append(f"{temp_range}")
        if precipitation:
            parts.append(
                tr("weather_precip_up_to", language, precipitation=precipitation)
            )
        if wind:
            parts.append(tr("weather_wind_up_to", language, wind=wind))
        return ", ".join(parts) + "."

    def _format_rate(self, quote: RateQuote, language: str) -> str:
        amount_text = self._format_number(quote.amount)
        converted = self._format_number(quote.converted_amount)
        rate = self._format_number(quote.rate)
        if quote.amount == 1:
            if language == "ru":
                return f"\u0421\u0435\u0439\u0447\u0430\u0441 1 {quote.base_currency} = {rate} {quote.quote_currency}."
            if language == "it":
                return (
                    f"Adesso 1 {quote.base_currency} = {rate} {quote.quote_currency}."
                )
            if language == "es":
                return f"Ahora 1 {quote.base_currency} = {rate} {quote.quote_currency}."
            if language == "fr":
                return f"En ce moment 1 {quote.base_currency} = {rate} {quote.quote_currency}."
            if language == "de":
                return f"Gerade gilt 1 {quote.base_currency} = {rate} {quote.quote_currency}."
            return f"Right now 1 {quote.base_currency} = {rate} {quote.quote_currency}."
        if language == "ru":
            return f"\u0421\u0435\u0439\u0447\u0430\u0441 {amount_text} {quote.base_currency} = {converted} {quote.quote_currency} \u043f\u043e \u043a\u0443\u0440\u0441\u0443 {rate}."
        if language == "it":
            return f"Adesso {amount_text} {quote.base_currency} = {converted} {quote.quote_currency} al tasso di {rate}."
        if language == "es":
            return f"Ahora {amount_text} {quote.base_currency} = {converted} {quote.quote_currency} al tipo de cambio de {rate}."
        if language == "fr":
            return f"En ce moment {amount_text} {quote.base_currency} = {converted} {quote.quote_currency} au taux de {rate}."
        if language == "de":
            return f"Gerade sind {amount_text} {quote.base_currency} = {converted} {quote.quote_currency} zum Kurs von {rate}."
        return f"Right now {amount_text} {quote.base_currency} = {converted} {quote.quote_currency} at a rate of {rate}."

    def _format_news(self, hits: list[SearchHit], language: str) -> str:
        items: list[str] = []
        for index, hit in enumerate(hits[:3], start=1):
            source = f" ({hit.source})" if hit.source else ""
            items.append(f"{index}) {hit.title}{source}")
        return tr("news_brief", language, items=" ".join(items))

    def _format_search(self, hits: list[SearchHit], language: str) -> str:
        items: list[str] = []
        for index, hit in enumerate(hits[:3], start=1):
            source_bits = [
                part for part in [hit.source or hit.provider, hit.published_at] if part
            ]
            source = f" ({' | '.join(source_bits)})" if source_bits else ""
            detail = hit.article_text or hit.snippet
            snippet = f": {detail}" if detail else ""
            items.append(f"{index}) {hit.title}{source}{snippet}")
        return tr("search_found", language, items=" ".join(items))

    def _format_temperature(self, value: float | None) -> str:
        if value is None:
            return ""
        sign = "+" if value > 0 else ""
        return f"{sign}{round(value):d}\u00b0C"

    def _format_wind(self, value: float | None) -> str:
        if value is None:
            return ""
        return f"{round(value):d} \u043a\u043c/\u0447"

    def _format_percent(self, value: int | None) -> str:
        if value is None:
            return ""
        return f"{value}%"

    def _format_number(self, value: float) -> str:
        if abs(value - round(value)) < 0.0001:
            return str(int(round(value)))
        return f"{value:.2f}".replace(".", ",")

