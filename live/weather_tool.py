from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

import httpx

from config.settings import AppConfig


WEATHER_CODE_LABELS = {
    "ru": {
        0: "\u044f\u0441\u043d\u043e",
        1: "\u043f\u0440\u0435\u0438\u043c\u0443\u0449\u0435\u0441\u0442\u0432\u0435\u043d\u043d\u043e \u044f\u0441\u043d\u043e",
        2: "\u043f\u0435\u0440\u0435\u043c\u0435\u043d\u043d\u0430\u044f \u043e\u0431\u043b\u0430\u0447\u043d\u043e\u0441\u0442\u044c",
        3: "\u043f\u0430\u0441\u043c\u0443\u0440\u043d\u043e",
        45: "\u0442\u0443\u043c\u0430\u043d",
        48: "\u0438\u043d\u0435\u0439 \u0438 \u0442\u0443\u043c\u0430\u043d",
        51: "\u0441\u043b\u0430\u0431\u0430\u044f \u043c\u043e\u0440\u043e\u0441\u044c",
        53: "\u043c\u043e\u0440\u043e\u0441\u044c",
        55: "\u0441\u0438\u043b\u044c\u043d\u0430\u044f \u043c\u043e\u0440\u043e\u0441\u044c",
        56: "\u0441\u043b\u0430\u0431\u044b\u0439 \u043b\u0435\u0434\u044f\u043d\u043e\u0439 \u0434\u043e\u0436\u0434\u044c",
        57: "\u043b\u0435\u0434\u044f\u043d\u043e\u0439 \u0434\u043e\u0436\u0434\u044c",
        61: "\u0441\u043b\u0430\u0431\u044b\u0439 \u0434\u043e\u0436\u0434\u044c",
        63: "\u0434\u043e\u0436\u0434\u044c",
        65: "\u0441\u0438\u043b\u044c\u043d\u044b\u0439 \u0434\u043e\u0436\u0434\u044c",
        66: "\u0441\u043b\u0430\u0431\u044b\u0439 \u043b\u0435\u0434\u044f\u043d\u043e\u0439 \u0434\u043e\u0436\u0434\u044c",
        67: "\u0441\u0438\u043b\u044c\u043d\u044b\u0439 \u043b\u0435\u0434\u044f\u043d\u043e\u0439 \u0434\u043e\u0436\u0434\u044c",
        71: "\u0441\u043b\u0430\u0431\u044b\u0439 \u0441\u043d\u0435\u0433",
        73: "\u0441\u043d\u0435\u0433",
        75: "\u0441\u0438\u043b\u044c\u043d\u044b\u0439 \u0441\u043d\u0435\u0433",
        77: "\u0441\u043d\u0435\u0436\u043d\u044b\u0435 \u0437\u0451\u0440\u043d\u0430",
        80: "\u043a\u0440\u0430\u0442\u043a\u0438\u0439 \u0434\u043e\u0436\u0434\u044c",
        81: "\u043b\u0438\u0432\u0435\u043d\u044c",
        82: "\u043e\u0447\u0435\u043d\u044c \u0441\u0438\u043b\u044c\u043d\u044b\u0439 \u043b\u0438\u0432\u0435\u043d\u044c",
        85: "\u0441\u043d\u0435\u0436\u043d\u044b\u0435 \u0437\u0430\u0440\u044f\u0434\u044b",
        86: "\u0441\u0438\u043b\u044c\u043d\u044b\u0435 \u0441\u043d\u0435\u0436\u043d\u044b\u0435 \u0437\u0430\u0440\u044f\u0434\u044b",
        95: "\u0433\u0440\u043e\u0437\u0430",
        96: "\u0433\u0440\u043e\u0437\u0430 \u0441 \u0433\u0440\u0430\u0434\u043e\u043c",
        99: "\u0441\u0438\u043b\u044c\u043d\u0430\u044f \u0433\u0440\u043e\u0437\u0430 \u0441 \u0433\u0440\u0430\u0434\u043e\u043c",
    },
    "en": {
        0: "clear",
        1: "mostly clear",
        2: "partly cloudy",
        3: "overcast",
        45: "fog",
        48: "fog with rime",
        51: "light drizzle",
        53: "drizzle",
        55: "heavy drizzle",
        56: "light freezing drizzle",
        57: "freezing drizzle",
        61: "light rain",
        63: "rain",
        65: "heavy rain",
        66: "light freezing rain",
        67: "heavy freezing rain",
        71: "light snow",
        73: "snow",
        75: "heavy snow",
        77: "snow grains",
        80: "brief rain showers",
        81: "rain showers",
        82: "very heavy rain showers",
        85: "snow showers",
        86: "heavy snow showers",
        95: "thunderstorm",
        96: "thunderstorm with hail",
        99: "severe thunderstorm with hail",
    },
}


class WeatherToolError(RuntimeError):
    pass


# Ukrainian/Russian case ending patterns for city name normalization
# Each tuple: (ending_to_strip, replacement, description)
_UK_CASE_ENDINGS = [
    ("Ñ–Ð²Ñ†ÑÑ…", "Ñ–Ð²Ñ†Ñ–", "loc -Ñ–Ð²Ñ†ÑÑ… â†’ nom -Ñ–Ð²Ñ†Ñ–"),
    ("Ñ–Ð²ÐºÐ°Ñ…", "Ñ–Ð²ÐºÐ°", "loc -Ñ–Ð²ÐºÐ°Ñ… â†’ nom -Ñ–Ð²ÐºÐ°"),
    ("Ñ†ÑÐ¼Ð¸", "Ñ†Ñ–", "instr -Ñ†ÑÐ¼Ð¸ â†’ nom -Ñ†Ñ–"),
    ("Ñ†ÑÑ…", "Ñ†Ñ–", "loc -Ñ†ÑÑ… â†’ nom -Ñ†Ñ–"),
    ("Ñ†ÑÐ¼", "Ñ†Ñ–", "dat -Ñ†ÑÐ¼ â†’ nom -Ñ†Ñ–"),
    ("ÐºÐ°Ð¼Ð¸", "ÐºÐ°", "instr -ÐºÐ°Ð¼Ð¸ â†’ nom -ÐºÐ°"),
    ("ÐºÐ°Ñ…", "ÐºÐ°", "loc -ÐºÐ°Ñ… â†’ nom -ÐºÐ°"),
    ("ÐºÐ°Ð¼Ð¸", "ÐºÐ°", "instr -ÐºÐ°Ð¼Ð¸ â†’ nom -ÐºÐ°"),
    ("ÐºÐ°Ð¼Ð¸", "Ð¾Ðº", "instr -ÐºÐ°Ð¼Ð¸ â†’ nom -Ð¾Ðº"),
    ("ÐºÐ°Ð¼Ð¸", "ÐºÐ°", "instr -ÐºÐ°Ð¼Ð¸ â†’ nom -ÐºÐ°"),
    ("ÑÐ¼Ð¸", "Ñ", "instr -ÑÐ¼Ð¸ â†’ nom -Ñ"),
    ("ÑÑ…", "Ñ–", "loc -ÑÑ… â†’ nom -Ñ–"),
    ("Ð°Ñ…", "Ð°", "loc -Ð°Ñ… â†’ nom -Ð°"),
    ("Ñ–ÑÐ¼", "Ñ–Ñ", "dat -Ñ–ÑÐ¼ â†’ nom -Ñ–Ñ"),
    ("Ð°Ð¼Ð¸", "Ð°", "instr -Ð°Ð¼Ð¸ â†’ nom -Ð°"),
    ("Ð°Ð¼Ð¸", "Ð¸", "instr -Ð°Ð¼Ð¸ â†’ nom -Ð¸"),
    ("Ð¾Ð¼Ñƒ", "Ð°", "dat -Ð¾Ð¼Ñƒ â†’ nom -Ð°"),
    ("Ð¾Ð¼Ñƒ", "Ñ–Ð¹", "dat -Ð¾Ð¼Ñƒ â†’ nom -Ñ–Ð¹"),
    ("Ð¾Ð²Ð¾", "Ñ–Ð²", "dat -Ð¾Ð²Ð¾ â†’ nom -Ñ–Ð²"),
    ("ÐµÐ²Ñ–", "Ñ–Ð²", "dat -ÐµÐ²Ñ– â†’ nom -Ñ–Ð²"),
    ("Ñ–Ð¹", "Ñ–Ñ", "loc -Ñ–Ð¹ â†’ nom -Ñ–Ñ"),
    ("Ñ–Ð¼", "Ð°", "loc -Ñ–Ð¼ â†’ nom -Ð°"),
]

_RU_CASE_ENDINGS = [
    ("Ñ†Ð°Ð¼Ð¸", "Ñ†Ñ‹", "instr -Ñ†Ð°Ð¼Ð¸ â†’ nom -Ñ†Ñ‹"),
    ("Ñ†Ð°Ð¼", "Ñ†Ñ‹", "dat -Ñ†Ð°Ð¼ â†’ nom -Ñ†Ñ‹"),
    ("Ñ†Ð°Ñ…", "Ñ†Ñ‹", "loc -Ñ†Ð°Ñ… â†’ nom -Ñ†Ñ‹"),
    ("ÐºÐ°Ð¼Ð¸", "ÐºÐ°", "instr -ÐºÐ°Ð¼Ð¸ â†’ nom -ÐºÐ°"),
    ("ÐºÐ°Ñ…", "ÐºÐ°", "loc -ÐºÐ°Ñ… â†’ nom -ÐºÐ°"),
    ("ÐºÐ°Ð¼Ð¸", "ÐºÐ°", "instr -ÐºÐ°Ð¼Ð¸ â†’ nom -ÐºÐ°"),
    ("ÑÐ¼Ð¸", "Ñ", "instr -ÑÐ¼Ð¸ â†’ nom -Ñ"),
    ("ÑÑ…", "Ñ", "loc -ÑÑ… â†’ nom -Ñ"),
    ("Ð°Ñ…", "Ð°", "loc -Ð°Ñ… â†’ nom -Ð°"),
    ("Ð°Ð¼Ð¸", "Ð°", "instr -Ð°Ð¼Ð¸ â†’ nom -Ð°"),
    ("Ð¾Ð¼Ñƒ", "Ð°", "dat -Ð¾Ð¼Ñƒ â†’ nom -Ð°"),
    ("Ð¾Ð¼Ñƒ", "Ð¸Ð¹", "dat -Ð¾Ð¼Ñƒ â†’ nom -Ð¸Ð¹"),
    ("Ð¾Ð²Ð¾", "Ð¾Ð²", "dat -Ð¾Ð²Ð¾ â†’ nom -Ð¾Ð²"),
    ("ÐµÐ²Ðµ", "ÐµÐ²", "dat -ÐµÐ²Ðµ â†’ nom -ÐµÐ²"),
    ("Ð¾Ð¼", "Ð°", "loc -Ð¾Ð¼ â†’ nom -Ð°"),
    ("Ð¾Ð¹", "Ð°", "loc -Ð¾Ð¹ â†’ nom -Ð°"),
    ("ÐµÐ¹", "Ñ", "loc -ÐµÐ¹ â†’ nom -Ñ"),
    ("Ð¸Ð¸", "Ð¸Ñ", "loc -Ð¸Ð¸ â†’ nom -Ð¸Ñ"),
]


def _is_cyrillic(text: str) -> bool:
    return any("\u0400" <= c <= "\u04ff" for c in text)


def _generate_location_variants(location: str) -> list[str]:
    """Generate multiple search variants for a Slavic city name."""
    if not location:
        return []

    variants = []
    seen = set()

    def _add(v: str):
        v = v.strip()
        key = v.casefold()
        if key and key not in seen:
            seen.add(key)
            variants.append(v)

    # Original
    _add(location)

    if not _is_cyrillic(location):
        return variants

    # Try all case endings (Ukrainian + Russian)
    all_endings = _UK_CASE_ENDINGS + _RU_CASE_ENDINGS
    lower = location.casefold()
    for ending, replacement, _ in all_endings:
        if lower.endswith(ending) and len(lower) > len(ending) + 2:
            _add(location[: -len(ending)] + replacement)

    # Try adding country hints for Cyrillic names
    countries = ["Ð£ÐºÑ€Ð°Ñ—Ð½Ð°", "Ð£ÐºÑ€Ð°Ð¸Ð½Ð°"]
    for v in list(variants):
        for country in countries:
            if country.casefold() not in v.casefold():
                _add(f"{v}, {country}")

    return variants


@dataclass(frozen=True, slots=True)
class LocationAlias:
    canonical_name: str
    preferred_country_codes: tuple[str, ...] = ()


LOCATION_ALIASES = {
    "rome": LocationAlias("Rome", ("IT",)),
    "roma": LocationAlias("Rome", ("IT",)),
    "Ñ€Ð¸Ð¼": LocationAlias("Rome", ("IT",)),
    "Ñ€Ð¸Ð¼Ðµ": LocationAlias("Rome", ("IT",)),
    "Ñ€Ð¸Ð¼Ð°": LocationAlias("Rome", ("IT",)),
    "Ñ€Ð¸Ð¼Ñƒ": LocationAlias("Rome", ("IT",)),
}

COUNTRY_NAME_ALIASES = {
    "italy": "IT",
    "italia": "IT",
    "Ð¸Ñ‚Ð°Ð»Ð¸Ñ": "IT",
    "Ð¸Ñ‚Ð°Ð»Ð¸Ð¸": "IT",
    "it": "IT",
    "romania": "RO",
    "Ñ€ÑƒÐ¼Ñ‹Ð½Ð¸Ñ": "RO",
    "Ñ€ÑƒÐ¼Ñ‹Ð½Ð¸Ð¸": "RO",
    "Ñ€Ð¾Ð¼Ð°Ð½Ð¸Ñ": "RO",
    "ro": "RO",
    "france": "FR",
    "Ñ„Ñ€Ð°Ð½Ñ†Ð¸Ñ": "FR",
    "fr": "FR",
    "germany": "DE",
    "Ð³ÐµÑ€Ð¼Ð°Ð½Ð¸Ñ": "DE",
    "de": "DE",
    "spain": "ES",
    "Ð¸ÑÐ¿Ð°Ð½Ð¸Ñ": "ES",
    "es": "ES",
    "united states": "US",
    "usa": "US",
    "us": "US",
    "ÑÑˆÐ°": "US",
    "america": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "great britain": "GB",
    "britain": "GB",
    "england": "GB",
    "Ð²ÐµÐ»Ð¸ÐºÐ¾Ð±Ñ€Ð¸Ñ‚Ð°Ð½Ð¸Ñ": "GB",
    "Ð°Ð½Ð³Ð»Ð¸Ñ": "GB",
    "gb": "GB",
}


def normalize_location_name(value: str) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold().replace("Ñ‘", "Ðµ")
    text = re.sub(r"[^a-zÐ°-Ñ0-9\s,-]", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" ,.-")


def rank_geocoding_candidate(
    candidate: dict,
    *,
    raw_query: str,
    target_name: str,
    alias: LocationAlias | None,
    country_hints: set[str],
) -> int:
    score = 0
    raw_query_norm = normalize_location_name(raw_query)
    target_norm = normalize_location_name(target_name)
    name_norm = normalize_location_name(str(candidate.get("name") or ""))
    country_norm = normalize_location_name(str(candidate.get("country") or ""))
    admin_norm = normalize_location_name(str(candidate.get("admin1") or ""))
    timezone_norm = normalize_location_name(str(candidate.get("timezone") or ""))
    candidate_country_codes = _candidate_country_codes(candidate)

    if target_norm and name_norm == target_norm:
        score += 140
    elif target_norm and (
        name_norm.startswith(target_norm) or target_norm in name_norm
    ):
        score += 80

    if raw_query_norm and name_norm == raw_query_norm:
        score += 75
    elif raw_query_norm and raw_query_norm in name_norm:
        score += 35

    if country_hints:
        if candidate_country_codes.intersection(country_hints):
            score += 95
        else:
            score -= 25

    if alias and alias.preferred_country_codes:
        preferred = set(alias.preferred_country_codes)
        if candidate_country_codes.intersection(preferred):
            score += 85
        else:
            score -= 20

    feature_code = str(candidate.get("feature_code") or "").upper()
    if feature_code == "PPLC":
        score += 45
    elif feature_code.startswith("PPLA"):
        score += 32
    elif feature_code == "PPL":
        score += 18

    population = _as_int(candidate.get("population"))
    if population is not None and population > 0:
        score += min(42, int(math.log10(population + 1) * 7))

    if target_norm and target_norm == admin_norm:
        score += 12
    if target_norm and target_norm in timezone_norm:
        score += 20
    if country_norm and target_norm and country_norm == target_norm:
        score -= 40

    return score


def _candidate_country_codes(candidate: dict) -> set[str]:
    country_codes: set[str] = set()
    country_code = str(candidate.get("country_code") or "").strip().upper()
    if country_code:
        country_codes.add(country_code)
    country_name = normalize_location_name(str(candidate.get("country") or ""))
    if country_name:
        alias_code = COUNTRY_NAME_ALIASES.get(country_name)
        if alias_code:
            country_codes.add(alias_code)
    return country_codes


def _extract_country_hints(query: str) -> set[str]:
    normalized = normalize_location_name(query)
    if not normalized:
        return set()
    padded = f" {normalized} "
    hints: set[str] = set()
    for phrase, code in COUNTRY_NAME_ALIASES.items():
        if f" {phrase} " in padded:
            hints.add(code)
    return hints


def _as_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class ResolvedLocation:
    query: str
    name: str
    latitude: float
    longitude: float
    timezone: str
    country: str | None
    admin1: str | None

    @property
    def label(self) -> str:
        parts = [self.name]
        if self.admin1 and self.admin1 != self.name:
            parts.append(self.admin1)
        if self.country:
            parts.append(self.country)
        return ", ".join(part for part in parts if part)


@dataclass(slots=True)
class WeatherForecast:
    location: ResolvedLocation
    day_offset: int
    forecast_date: str
    condition: str
    temperature_current: float | None
    temperature_min: float | None
    temperature_max: float | None
    precipitation_probability: int | None
    wind_speed: float | None


class WeatherTool:
    def __init__(
        self,
        client: httpx.AsyncClient,
        config: AppConfig,
        *,
        location_resolver=None,
        limiter=None,
    ) -> None:
        self._client = client
        self._config = config
        self._location_resolver = location_resolver
        self._limiter = limiter

    async def _rate_limited_get(
        self, key: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        """Ð’Ñ‹Ð¿Ð¾Ð»Ð½Ð¸Ñ‚ÑŒ GET Ð·Ð°Ð¿Ñ€Ð¾Ñ Ñ rate limiting."""
        if self._limiter:
            from infra.rate_limiter import get_rate_limiter

            limiter = self._limiter
            return await limiter.execute_with_retry(
                key,
                lambda: self._client.get(url, **kwargs),
            )
        return await self._client.get(url, **kwargs)

    async def fetch_forecast(
        self, location_query: str, *, day_offset: int, language: str = "en"
    ) -> WeatherForecast:
        location = await self._resolve_location(location_query, language=language)
        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "timezone": "auto",
            "current": "temperature_2m,wind_speed_10m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max",
            "forecast_days": max(3, day_offset + 2),
        }
        response = await self._rate_limited_get(
            "open-meteo",
            self._config.open_meteo_forecast_url,
            params=params,
            timeout=self._config.live_data_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()

        daily = payload.get("daily") or {}
        dates = list(daily.get("time") or [])
        if not dates or day_offset >= len(dates):
            raise WeatherToolError("forecast_not_available")

        current = payload.get("current") or {}
        weather_codes = list(daily.get("weather_code") or [])
        min_temps = list(daily.get("temperature_2m_min") or [])
        max_temps = list(daily.get("temperature_2m_max") or [])
        precip = list(daily.get("precipitation_probability_max") or [])
        max_wind = list(daily.get("wind_speed_10m_max") or [])

        daily_code = (
            weather_codes[day_offset] if day_offset < len(weather_codes) else None
        )
        current_code = current.get("weather_code")
        code = daily_code if daily_code is not None else current_code

        return WeatherForecast(
            location=location,
            day_offset=day_offset,
            forecast_date=dates[day_offset],
            condition=self._weather_label(code, language),
            temperature_current=self._as_float(current.get("temperature_2m")),
            temperature_min=self._pick_float(min_temps, day_offset),
            temperature_max=self._pick_float(max_temps, day_offset),
            precipitation_probability=self._pick_int(precip, day_offset),
            wind_speed=self._pick_float(max_wind, day_offset)
            if day_offset > 0
            else self._as_float(current.get("wind_speed_10m")),
        )

    async def _resolve_location(
        self, location_query: str, *, language: str = "en"
    ) -> ResolvedLocation:
        # Use LocationResolver if available
        if self._location_resolver is not None:
            from live.location_resolver import LocationResolverError

            try:
                resolved = await self._location_resolver.resolve(
                    location_query, language=language
                )
                return ResolvedLocation(
                    query=location_query,
                    name=resolved.name,
                    latitude=resolved.lat,
                    longitude=resolved.lon,
                    timezone=resolved.timezone,
                    country=resolved.country or None,
                    admin1=resolved.admin1 or None,
                )
            except LocationResolverError:
                raise WeatherToolError("location_not_found")

        # Fallback to old logic
        return await self._resolve_location_legacy(location_query, language=language)

    async def _resolve_location_legacy(
        self, location_query: str, *, language: str = "en"
    ) -> ResolvedLocation:
        prepared_query, target_name, alias, country_hints = (
            self._prepare_location_query(location_query)
        )

        # Generate multiple query variants for better geocoding
        query_variants = _generate_location_variants(prepared_query)

        results = []
        for variant in query_variants:
            response = await self._client.get(
                self._config.open_meteo_geocoding_url,
                params={
                    "name": variant,
                    "count": 5,
                    "language": "ru" if language in ("ru", "uk") else "en",
                    "format": "json",
                },
                timeout=self._config.live_data_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results") or []
            if results:
                break

        # Fallback to Nominatim if Open-Meteo found nothing
        if not results:
            for variant in query_variants:
                for service_url, service_name in [
                    ("https://nominatim.openstreetmap.org/search", "nominatim"),
                    (
                        "https://geocoding-api.open-meteo.com/v1/search",
                        "openmeteo_retry",
                    ),
                ]:
                    try:
                        if service_name == "nominatim":
                            params = {
                                "q": variant,
                                "format": "json",
                                "limit": 5,
                                "accept-language": "ru"
                                if language in ("ru", "uk")
                                else "en",
                            }
                            headers = {"User-Agent": "Project Assistant/1.0"}
                        else:
                            params = {
                                "name": variant,
                                "count": 5,
                                "language": "ru" if language in ("ru", "uk") else "en",
                                "format": "json",
                            }
                            headers = {}

                        nom_resp = await self._client.get(
                            service_url,
                            params=params,
                            headers=headers,
                            timeout=self._config.live_data_timeout_seconds,
                        )
                        if nom_resp.status_code == 200:
                            payload = nom_resp.json()
                            nom_results = (
                                payload.get("results")
                                if service_name == "openmeteo_retry"
                                else (payload or [])
                            )
                            if nom_results:
                                best = nom_results[0]
                                return ResolvedLocation(
                                    query=location_query,
                                    name=str(
                                        best.get("display_name")
                                        if service_name == "nominatim"
                                        else best.get("name") or location_query
                                    ),
                                    latitude=float(
                                        best.get("lat") or best.get("latitude", 0)
                                    ),
                                    longitude=float(
                                        best.get("lon") or best.get("longitude", 0)
                                    ),
                                    timezone=str(best.get("timezone") or "auto"),
                                    country=(
                                        best.get("display_name", "")
                                        .split(",")[-1]
                                        .strip()
                                        if service_name == "nominatim"
                                        else best.get("country")
                                    )
                                    or None,
                                    admin1=best.get("admin1"),
                                )
                    except Exception:
                        continue

        if not results:
            raise WeatherToolError("location_not_found")

        item = max(
            results,
            key=lambda candidate: rank_geocoding_candidate(
                candidate,
                raw_query=location_query,
                target_name=target_name,
                alias=alias,
                country_hints=country_hints,
            ),
        )
        return ResolvedLocation(
            query=location_query,
            name=str(item.get("name") or location_query),
            latitude=float(item["latitude"]),
            longitude=float(item["longitude"]),
            timezone=str(item.get("timezone") or "auto"),
            country=item.get("country"),
            admin1=item.get("admin1"),
        )

    def _prepare_location_query(
        self,
        location_query: str,
    ) -> tuple[str, str, LocationAlias | None, set[str]]:
        cleaned_query = " ".join((location_query or "").split()).strip(" ,.-")
        if not cleaned_query:
            raise WeatherToolError("location_not_found")

        country_hints = _extract_country_hints(cleaned_query)
        city_segment = cleaned_query.split(",", 1)[0].strip(" ,.-") or cleaned_query
        alias = self._lookup_location_alias(city_segment)
        if alias is None:
            alias = self._lookup_location_alias(cleaned_query)

        target_name = alias.canonical_name if alias is not None else city_segment
        return target_name, target_name, alias, country_hints

    def _lookup_location_alias(self, value: str) -> LocationAlias | None:
        normalized = normalize_location_name(value)
        if not normalized:
            return None

        alias = LOCATION_ALIASES.get(normalized)
        if alias is not None:
            return alias

        tokens = normalized.split()
        for size in range(min(3, len(tokens)), 0, -1):
            candidate = " ".join(tokens[:size])
            alias = LOCATION_ALIASES.get(candidate)
            if alias is not None:
                return alias
        return None

    def _pick_float(self, values: list[object], index: int) -> float | None:
        if index >= len(values):
            return None
        return self._as_float(values[index])

    def _pick_int(self, values: list[object], index: int) -> int | None:
        if index >= len(values):
            return None
        value = values[index]
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return None

    def _as_float(self, value: object) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _weather_label(self, code: object, language: str) -> str:
        if code is None:
            return (
                "\u0431\u0435\u0437 \u0442\u043e\u0447\u043d\u043e\u0433\u043e \u043e\u043f\u0438\u0441\u0430\u043d\u0438\u044f"
                if language == "ru"
                else "without a precise description"
            )
        normalized_code = int(code)
        labels = WEATHER_CODE_LABELS["ru" if language == "ru" else "en"]
        return labels.get(
            normalized_code,
            "\u0431\u0435\u0437 \u0442\u043e\u0447\u043d\u043e\u0433\u043e \u043e\u043f\u0438\u0441\u0430\u043d\u0438\u044f"
            if language == "ru"
            else "without a precise description",
        )

