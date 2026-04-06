"""Rate limiter Ð´Ð»Ñ Ð²Ð½ÐµÑˆÐ½Ð¸Ñ… API.

ÐŸÐ¾Ð´Ð´ÐµÑ€Ð¶Ð¸Ð²Ð°ÐµÑ‚:
- Ð›Ð¸Ð¼Ð¸Ñ‚ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ¾Ð² Ð² Ð¼Ð¸Ð½ÑƒÑ‚Ñƒ/Ñ‡Ð°Ñ
- Per-key Ð»Ð¸Ð¼Ð¸Ñ‚Ñ‹ (different limits for different APIs)
- Ð­ÐºÑÐ¿Ð¾Ð½ÐµÐ½Ñ†Ð¸Ð°Ð»ÑŒÐ½Ñ‹Ð¹ backoff Ð¿Ñ€Ð¸ retry
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger("assistant.rate_limiter")


@dataclass
class RateLimitConfig:
    """ÐšÐ¾Ð½Ñ„Ð¸Ð³ÑƒÑ€Ð°Ñ†Ð¸Ñ Ð»Ð¸Ð¼Ð¸Ñ‚Ð° Ð´Ð»Ñ Ð¾Ð´Ð½Ð¾Ð³Ð¾ API."""

    calls_per_minute: int | None = None
    calls_per_hour: int | None = None
    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential_base: float = 2.0


@dataclass
class CallRecord:
    """Ð—Ð°Ð¿Ð¸ÑÑŒ Ð¾ Ð²Ñ‹Ð·Ð¾Ð²Ðµ API."""

    timestamp: float
    success: bool = True


class RateLimiter:
    """Rate limiter Ñ Ð¿Ð¾Ð´Ð´ÐµÑ€Ð¶ÐºÐ¾Ð¹ per-key Ð»Ð¸Ð¼Ð¸Ñ‚Ð¾Ð² Ð¸ retry.

    ÐŸÑ€Ð¸Ð¼ÐµÑ€ Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ð½Ð¸Ñ:
        limiter = RateLimiter()
        limiter.configure("open-meteo", calls_per_minute=10)
        limiter.configure("github", calls_per_hour=100)

        async with limiter.rate_limit("open-meteo"):
            response = await client.get(url)

        # Ð¡ retry + backoff
        response = await limiter.execute_with_retry(
            "github",
            lambda: client.get(url),
        )
    """

    def __init__(self) -> None:
        self._configs: dict[str, RateLimitConfig] = {}
        self._calls: dict[str, list[CallRecord]] = defaultdict(list)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def configure(self, key: str, config: RateLimitConfig) -> None:
        """ÐÐ°ÑÑ‚Ñ€Ð¾Ð¸Ñ‚ÑŒ Ð»Ð¸Ð¼Ð¸Ñ‚Ñ‹ Ð´Ð»Ñ API key."""
        self._configs[key] = config
        LOGGER.info("rate_limit_configured key=%s config=%s", key, config)

    def _cleanup_old_calls(self, key: str, window_seconds: int) -> None:
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ ÑÑ‚Ð°Ñ€Ñ‹Ðµ Ð²Ñ‹Ð·Ð¾Ð²Ñ‹ Ð·Ð° Ð¿Ñ€ÐµÐ´ÐµÐ»Ð°Ð¼Ð¸ Ð¾ÐºÐ½Ð°."""
        now = time.time()
        cutoff = now - window_seconds
        self._calls[key] = [
            record for record in self._calls[key] if record.timestamp > cutoff
        ]

    def _get_calls_in_window(self, key: str, window_seconds: int) -> int:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾ Ð²Ñ‹Ð·Ð¾Ð²Ð¾Ð² Ð·Ð° Ð¾ÐºÐ½Ð¾."""
        self._cleanup_old_calls(key, window_seconds)
        return len(self._calls[key])

    async def _wait_if_needed(self, key: str) -> None:
        """ÐŸÐ¾Ð´Ð¾Ð¶Ð´Ð°Ñ‚ÑŒ ÐµÑÐ»Ð¸ Ð»Ð¸Ð¼Ð¸Ñ‚ Ð¿Ñ€ÐµÐ²Ñ‹ÑˆÐµÐ½."""
        config = self._configs.get(key)
        if not config:
            return

        now = time.time()
        delay = 0.0

        # ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð»Ð¸Ð¼Ð¸Ñ‚Ð° Ð² Ð¼Ð¸Ð½ÑƒÑ‚Ñƒ
        if config.calls_per_minute:
            calls_last_minute = self._get_calls_in_window(key, 60)
            if calls_last_minute >= config.calls_per_minute:
                # ÐÐ°Ð¹Ñ‚Ð¸ ÑÐ°Ð¼Ñ‹Ð¹ ÑÑ‚Ð°Ñ€Ñ‹Ð¹ Ð²Ñ‹Ð·Ð¾Ð² Ð² Ð¼Ð¸Ð½ÑƒÑ‚Ð½Ð¾Ð¼ Ð¾ÐºÐ½Ðµ
                oldest = min(
                    (r.timestamp for r in self._calls[key]),
                    default=now,
                )
                delay = max(delay, 60.0 - (now - oldest))

        # ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð»Ð¸Ð¼Ð¸Ñ‚Ð° Ð² Ñ‡Ð°Ñ
        if config.calls_per_hour:
            calls_last_hour = self._get_calls_in_window(key, 3600)
            if calls_last_hour >= config.calls_per_hour:
                oldest = min(
                    (r.timestamp for r in self._calls[key]),
                    default=now,
                )
                delay = max(delay, 3600.0 - (now - oldest))

        if delay > 0.1:
            LOGGER.debug("rate_limit_wait key=%s delay=%.2fs", key, delay)
            await asyncio.sleep(delay)

    async def acquire(self, key: str) -> None:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ñ€Ð°Ð·Ñ€ÐµÑˆÐµÐ½Ð¸Ðµ Ð½Ð° Ð²Ñ‹Ð·Ð¾Ð² API."""
        async with self._locks[key]:
            await self._wait_if_needed(key)

    async def record_call(self, key: str, success: bool = True) -> None:
        """Ð—Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ Ð²Ñ‹Ð·Ð¾Ð² API."""
        async with self._locks[key]:
            self._calls[key].append(CallRecord(timestamp=time.time(), success=success))

    async def __aenter__(self) -> None:
        """Context manager entry."""
        pass

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - Ð·Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚."""
        pass

    async def execute_with_retry(
        self,
        key: str,
        func: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Ð’Ñ‹Ð¿Ð¾Ð»Ð½Ð¸Ñ‚ÑŒ Ñ„ÑƒÐ½ÐºÑ†Ð¸ÑŽ Ñ retry Ð¸ exponential backoff.

        Args:
            key: API key Ð´Ð»Ñ Ð»Ð¸Ð¼Ð¸Ñ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ
            func: ÐÑÐ¸Ð½Ñ…Ñ€Ð¾Ð½Ð½Ð°Ñ Ñ„ÑƒÐ½ÐºÑ†Ð¸Ñ Ð´Ð»Ñ Ð²Ñ‹Ð·Ð¾Ð²Ð°
            *args: ÐŸÐ¾Ð·Ð¸Ñ†Ð¸Ð¾Ð½Ð½Ñ‹Ðµ Ð°Ñ€Ð³ÑƒÐ¼ÐµÐ½Ñ‚Ñ‹ Ð´Ð»Ñ Ñ„ÑƒÐ½ÐºÑ†Ð¸Ð¸
            **kwargs: Keyword Ð°Ñ€Ð³ÑƒÐ¼ÐµÐ½Ñ‚Ñ‹ Ð´Ð»Ñ Ñ„ÑƒÐ½ÐºÑ†Ð¸Ð¸

        Returns:
            Ð ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚ Ð²Ñ‹Ð¿Ð¾Ð»Ð½ÐµÐ½Ð¸Ñ Ñ„ÑƒÐ½ÐºÑ†Ð¸Ð¸

        Raises:
            ÐŸÐ¾ÑÐ»ÐµÐ´Ð½ÐµÐµ Ð¸ÑÐºÐ»ÑŽÑ‡ÐµÐ½Ð¸Ðµ ÐµÑÐ»Ð¸ Ð²ÑÐµ retry Ð¸ÑÑ‡ÐµÑ€Ð¿Ð°Ð½Ñ‹
        """
        config = self._configs.get(key, RateLimitConfig())
        last_exception: Exception | None = None

        for attempt in range(config.max_retries + 1):
            try:
                # Ð–Ð´Ð°Ñ‚ÑŒ ÐµÑÐ»Ð¸ Ð½ÑƒÐ¶Ð½Ð¾
                await self.acquire(key)

                # Ð’Ñ‹Ð¿Ð¾Ð»Ð½Ð¸Ñ‚ÑŒ Ð²Ñ‹Ð·Ð¾Ð²
                if inspect.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                    if inspect.isawaitable(result):
                        result = await result

                # Ð—Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ ÑƒÑÐ¿ÐµÑˆÐ½Ñ‹Ð¹ Ð²Ñ‹Ð·Ð¾Ð²
                await self.record_call(key, success=True)
                return result

            except Exception as e:
                last_exception = e
                await self.record_call(key, success=False)

                # ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ retry limit
                if attempt >= config.max_retries:
                    break

                # ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ rate limit error (429)
                is_rate_limit = getattr(e, "status_code", None) == 429

                if not is_rate_limit and attempt < config.max_retries:
                    # Ð”Ð»Ñ Ð´Ñ€ÑƒÐ³Ð¸Ñ… Ð¾ÑˆÐ¸Ð±Ð¾Ðº Ñ‚Ð¾Ð¶Ðµ retry
                    pass

                # Ð’Ñ‹Ñ‡Ð¸ÑÐ»Ð¸Ñ‚ÑŒ delay Ñ exponential backoff
                delay = min(
                    config.base_delay_seconds * (config.exponential_base**attempt),
                    config.max_delay_seconds,
                )

                LOGGER.warning(
                    "api_call_retry key=%s attempt=%d/%d delay=%.2fs error=%s",
                    key,
                    attempt + 1,
                    config.max_retries + 1,
                    delay,
                    str(e),
                )

                await asyncio.sleep(delay)

        if last_exception:
            raise last_exception
        raise RuntimeError("Unexpected state: no result and no exception")


# Ð“Ð»Ð¾Ð±Ð°Ð»ÑŒÐ½Ñ‹Ð¹ instance Ð´Ð»Ñ ÑƒÐ´Ð¾Ð±ÑÑ‚Ð²Ð°
_global_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð³Ð»Ð¾Ð±Ð°Ð»ÑŒÐ½Ñ‹Ð¹ rate limiter."""
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = RateLimiter()
    return _global_limiter


def configure_default_limits(limiter: RateLimiter) -> None:
    """ÐÐ°ÑÑ‚Ñ€Ð¾Ð¸Ñ‚ÑŒ Ð»Ð¸Ð¼Ð¸Ñ‚Ñ‹ Ð¿Ð¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ Ð´Ð»Ñ Ð¿Ð¾Ð¿ÑƒÐ»ÑÑ€Ð½Ñ‹Ñ… API."""

    # Open-Meteo (weather) - 10 calls/min
    limiter.configure(
        "open-meteo",
        RateLimitConfig(
            calls_per_minute=10,
            max_retries=3,
        ),
    )

    # GitHub API - 100 calls/hour (unauthenticated)
    limiter.configure(
        "github",
        RateLimitConfig(
            calls_per_hour=100,
            max_retries=3,
            base_delay_seconds=2.0,
        ),
    )

    # DuckDuckGo - ÐºÐ¾Ð½ÑÐµÑ€Ð²Ð°Ñ‚Ð¸Ð²Ð½Ð¾
    limiter.configure(
        "duckduckgo",
        RateLimitConfig(
            calls_per_minute=5,
            max_retries=2,
        ),
    )

    # Google Search - Ð¾Ñ‡ÐµÐ½ÑŒ ÐºÐ¾Ð½ÑÐµÑ€Ð²Ð°Ñ‚Ð¸Ð²Ð½Ð¾
    limiter.configure(
        "google",
        RateLimitConfig(
            calls_per_minute=2,
            max_retries=2,
            base_delay_seconds=5.0,
        ),
    )

    # Wikipedia API
    limiter.configure(
        "wikipedia",
        RateLimitConfig(
            calls_per_minute=10,
            max_retries=3,
        ),
    )

    # Generic fallback
    limiter.configure(
        "default",
        RateLimitConfig(
            calls_per_minute=30,
            max_retries=3,
        ),
    )

