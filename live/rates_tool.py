from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from config.settings import AppConfig


class RatesToolError(RuntimeError):
    pass


@dataclass(slots=True)
class RateQuote:
    amount: float
    base_currency: str
    quote_currency: str
    rate: float
    converted_amount: float
    quoted_at: str | None


class RatesTool:
    def __init__(
        self,
        client: httpx.AsyncClient,
        config: AppConfig,
        limiter=None,
    ) -> None:
        self._client = client
        self._config = config
        self._currencies_cache: dict[str, str] | None = None
        self._currencies_cache_expires_at = 0.0
        self._limiter = limiter

    async def _rate_limited_get(
        self, key: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        """Выполнить GET запрос с rate limiting."""
        if self._limiter:
            return await self._limiter.execute_with_retry(
                key,
                lambda: self._client.get(url, **kwargs),
            )
        return await self._client.get(url, **kwargs)

    async def fetch_quote(
        self, *, amount: float, base_currency: str, quote_currency: str
    ) -> RateQuote:
        base_currency = (base_currency or "").strip().upper()
        quote_currency = (quote_currency or "").strip().upper()
        if base_currency == quote_currency:
            return RateQuote(
                amount=amount,
                base_currency=base_currency,
                quote_currency=quote_currency,
                rate=1.0,
                converted_amount=amount,
                quoted_at=None,
            )

        supported = await self.fetch_supported_currencies()
        if base_currency not in supported:
            raise RatesToolError(f"unsupported_base:{base_currency}")
        if quote_currency not in supported:
            raise RatesToolError(f"unsupported_quote:{quote_currency}")

        try:
            response = await self._rate_limited_get(
                "frankfurter",
                f"{self._config.frankfurter_base_url}/latest",
                params={"base": base_currency, "symbols": quote_currency},
                timeout=self._config.live_data_timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise RatesToolError("rate_not_found") from exc
            raise

        payload = response.json()
        rates = payload.get("rates") or {}
        rate = rates.get(quote_currency)
        if rate is None:
            raise RatesToolError("rate_not_found")

        rate_value = float(rate)
        return RateQuote(
            amount=amount,
            base_currency=base_currency,
            quote_currency=quote_currency,
            rate=rate_value,
            converted_amount=amount * rate_value,
            quoted_at=payload.get("date"),
        )

    async def fetch_supported_currencies(
        self, *, force_refresh: bool = False
    ) -> dict[str, str]:
        now = time.monotonic()
        if (
            not force_refresh
            and self._currencies_cache is not None
            and now < self._currencies_cache_expires_at
        ):
            return dict(self._currencies_cache)

        response = await self._rate_limited_get(
            "frankfurter",
            f"{self._config.frankfurter_base_url}/currencies",
            timeout=self._config.live_data_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not payload:
            raise RatesToolError("currencies_unavailable")

        normalized = {
            str(code).strip().upper(): str(name).strip()
            for code, name in payload.items()
            if str(code).strip()
        }
        if not normalized:
            raise RatesToolError("currencies_unavailable")

        self._currencies_cache = normalized
        self._currencies_cache_expires_at = now + 12 * 60 * 60
        return dict(normalized)
