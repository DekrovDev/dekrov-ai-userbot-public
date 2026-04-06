"""Multi-stage location resolver with fuzzy matching, alias cache, and cascading search."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx

from infra.json_atomic import atomic_write_json_sync


# â”€â”€â”€ Noise words to strip from queries â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

NOISE_WORDS = {
    # Ukrainian
    "Ð¿Ð¾Ð³Ð¾Ð´Ð°",
    "Ð¿Ð¾Ð³Ð¾Ð´Ñƒ",
    "Ð¿Ñ€Ð¾Ð³Ð½Ð¾Ð·",
    "Ñ‚ÐµÐ¼Ð¿ÐµÑ€Ð°Ñ‚ÑƒÑ€Ð°",
    "Ñ‚ÐµÐ¼Ð¿ÐµÑ€Ð°Ñ‚ÑƒÑ€",
    "Ð´Ð¾Ñ‰",
    "Ð´Ð¾Ñ‰Ñ–",
    "Ð²Ñ–Ñ‚ÐµÑ€",
    "ÑÐ½Ñ–Ð³",
    "Ñ…Ð¼Ð°Ñ€Ð½Ð¾",
    "ÑÐ¾Ð½ÑÑ‡Ð½Ð¾",
    "ÑÑŒÐ¾Ð³Ð¾Ð´Ð½Ñ–",
    "Ð·Ð°Ð²Ñ‚Ñ€Ð°",
    "Ð¿Ñ–ÑÐ»ÑÐ·Ð°Ð²Ñ‚Ñ€Ð°",
    "Ð·Ð°Ñ€Ð°Ð·",
    "ÑÑŒÐ¾Ð³Ð¾Ð´Ð½Ñ–ÑˆÐ½Ñ–Ð¹",
    "ÑÐºÐ°",
    "ÑÐºÐ¸Ð¹",
    "ÑÐºÑ–",
    "Ñ‰Ð¾",
    "ÑÐºÐ°Ð¶Ð¸",
    "Ð¿Ð¾ÐºÐ°Ð¶Ð¸",
    "Ð¿Ñ–Ð´ÐºÐ°Ð¶Ð¸",
    "Ð¿Ñ€Ð¸Ð²Ñ–Ñ‚",
    "Ð´Ð¾Ð±Ñ€Ð¸Ð¹",
    "Ð´ÐµÐ½ÑŒ",
    "Ð²ÐµÑ‡Ñ–Ñ€",
    "Ñ€Ð°Ð½Ð¾Ðº",
    "Ñƒ",
    "Ð²",
    "Ð½Ð°",
    "Ð¿Ð¾",
    "Ð´Ð¾",
    "Ð·",
    "Ñ–Ð·",
    "Ð´Ð»Ñ",
    "Ð±ÑƒÐ´ÑŒ",
    "Ð»Ð°ÑÐºÐ°",
    "Ð´ÑÐºÑƒÑŽ",
    # Russian
    "Ð¿Ð¾Ð³Ð¾Ð´Ð°",
    "Ð¿Ñ€Ð¾Ð³Ð½Ð¾Ð·",
    "Ñ‚ÐµÐ¼Ð¿ÐµÑ€Ð°Ñ‚ÑƒÑ€Ð°",
    "Ñ‚ÐµÐ¼Ð¿ÐµÑ€Ð°Ñ‚ÑƒÑ€",
    "Ð´Ð¾Ð¶Ð´ÑŒ",
    "Ð´Ð¾Ð¶Ð´Ð¸",
    "Ð²ÐµÑ‚ÐµÑ€",
    "ÑÐ½ÐµÐ³",
    "Ð¾Ð±Ð»Ð°Ñ‡Ð½Ð¾",
    "ÑÑÐ½Ð¾",
    "ÑÐµÐ³Ð¾Ð´Ð½Ñ",
    "Ð·Ð°Ð²Ñ‚Ñ€Ð°",
    "Ð¿Ð¾ÑÐ»ÐµÐ·Ð°Ð²Ñ‚Ñ€Ð°",
    "ÑÐµÐ¹Ñ‡Ð°Ñ",
    "ÑÐµÐ³Ð¾Ð´Ð½ÑÑˆÐ½Ð¸Ð¹",
    "ÐºÐ°ÐºÐ°Ñ",
    "ÐºÐ°ÐºÐ¾Ð¹",
    "ÐºÐ°ÐºÐ¸Ðµ",
    "Ñ‡Ñ‚Ð¾",
    "ÑÐºÐ°Ð¶Ð¸",
    "Ð¿Ð¾ÐºÐ°Ð¶Ð¸",
    "Ð¿Ð¾Ð´ÑÐºÐ°Ð¶Ð¸",
    "Ð¿Ñ€Ð¸Ð²ÐµÑ‚",
    "Ð´Ð¾Ð±Ñ€Ñ‹Ð¹",
    "Ð´ÐµÐ½ÑŒ",
    "Ð²ÐµÑ‡ÐµÑ€",
    "ÑƒÑ‚Ñ€Ð¾",
    "Ð²",
    "Ð²Ð¾",
    "Ð½Ð°",
    "Ð¿Ð¾",
    "Ð´Ð¾",
    "Ñ",
    "Ð¸Ð·",
    "Ð´Ð»Ñ",
    "Ð±ÑƒÐ´ÑŒ",
    "Ð»Ð°ÑÐºÐ°",
    "ÑÐ¿Ð°ÑÐ¸Ð±Ð¾",
    "Ð¿Ð¾Ð¶Ð°Ð»ÑƒÐ¹ÑÑ‚Ð°",
    # English
    "weather",
    "forecast",
    "temperature",
    "rain",
    "wind",
    "snow",
    "sunny",
    "cloudy",
    "today",
    "tomorrow",
    "now",
    "currently",
    "what",
    "how",
    "is",
    "the",
    "in",
    "at",
    "tell",
    "show",
    "please",
    "hi",
    "hello",
    "hey",
}


# â”€â”€â”€ Slavic case endings for variant generation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_CASE_RULES: list[tuple[str, str]] = [
    # Ukrainian - most specific first
    ("\u0456\u0432\u0446\u044f\u0445", "\u0456\u0432\u0446\u0456"),  # Ñ–Ð²Ñ†ÑÑ… â†’ Ñ–Ð²Ñ†Ñ–
    ("\u0456\u0432\u043a\u0430\u0445", "\u0456\u0432\u043a\u0430"),  # Ñ–Ð²ÐºÐ°Ñ… â†’ Ñ–Ð²ÐºÐ°
    ("\u0446\u044f\u043c\u0438", "\u0446\u0456"),  # Ñ†ÑÐ¼Ð¸ â†’ Ñ†Ñ–
    ("\u0446\u044f\u0445", "\u0446\u0456"),  # Ñ†ÑÑ… â†’ Ñ†Ñ–
    ("\u0446\u044f\u043c", "\u0446\u0456"),  # Ñ†ÑÐ¼ â†’ Ñ†Ñ–
    ("\u043a\u0430\u043c\u0438", "\u043a\u0430"),  # ÐºÐ°Ð¼Ð¸ â†’ ÐºÐ°
    ("\u043a\u0430\u0445", "\u043a\u0430"),  # ÐºÐ°Ñ… â†’ ÐºÐ°
    ("\u044f\u043c\u0438", "\u044f"),  # ÑÐ¼Ð¸ â†’ Ñ
    ("\u044f\u0445", "\u0456"),  # ÑÑ… â†’ Ñ– (generic)
    ("\u0430\u0445", "\u0430"),  # Ð°Ñ… â†’ Ð° (generic)
    ("\u0456\u044f\u043c", "\u0456\u044f"),  # Ñ–ÑÐ¼ â†’ Ñ–Ñ
    ("\u0430\u043c\u0438", "\u0430"),  # Ð°Ð¼Ð¸ â†’ Ð°
    ("\u043e\u043c\u0443", "\u0430"),  # Ð¾Ð¼Ñƒ â†’ Ð°
    ("\u0456\u0439", "\u0456\u044f"),  # Ñ–Ð¹ â†’ Ñ–Ñ
    ("\u0456\u0432", "\u0456"),  # Ñ–Ð² â†’ Ñ– (very generic, last resort)
    # Russian
    ("\u0446\u0430\u043c\u0438", "\u0446\u044b"),  # Ñ†Ð°Ð¼Ð¸ â†’ Ñ†Ñ‹
    ("\u0446\u0430\u043c", "\u0446\u044b"),  # Ñ†Ð°Ð¼ â†’ Ñ†Ñ‹
    ("\u0446\u0430\u0445", "\u0446\u044b"),  # Ñ†Ð°Ñ… â†’ Ñ†Ñ‹
    ("\u043a\u0430\u043c\u0438", "\u043a\u0430"),  # ÐºÐ°Ð¼Ð¸ â†’ ÐºÐ°
    ("\u043a\u0430\u0445", "\u043a\u0430"),  # ÐºÐ°Ñ… â†’ ÐºÐ°
    ("\u044f\u043c\u0438", "\u044f"),  # ÑÐ¼Ð¸ â†’ Ñ
    ("\u044f\u0445", "\u044f"),  # ÑÑ… â†’ Ñ
    ("\u0430\u0445", "\u0430"),  # Ð°Ñ… â†’ Ð°
    ("\u0430\u043c\u0438", "\u0430"),  # Ð°Ð¼Ð¸ â†’ Ð°
    ("\u043e\u043c\u0443", "\u0430"),  # Ð¾Ð¼Ñƒ â†’ Ð°
    ("\u043e\u0432\u043e", "\u043e\u0432"),  # Ð¾Ð²Ð¾ â†’ Ð¾Ð²
    ("\u0435\u0432\u0435", "\u0435\u0432"),  # ÐµÐ²Ñ â†’ ÐµÐ²
    ("\u043e\u043c", "\u0430"),  # Ð¾Ð¼ â†’ Ð°
    ("\u043e\u0439", "\u0430"),  # Ð¾Ð¹ â†’ Ð°
    ("\u0435\u0439", "\u044f"),  # ÐµÐ¹ â†’ Ñ
    ("\u0438\u0438", "\u0438\u044f"),  # Ð¸Ð¸ â†’ Ð¸Ñ
]


def _is_cyrillic(text: str) -> bool:
    return any("\u0400" <= c <= "\u04ff" for c in text)


def _normalize_text(text: str) -> str:
    """Lowercase, trim, collapse spaces."""
    return " ".join((text or "").split()).strip().casefold()


# â”€â”€â”€ Gazetteer entry â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@dataclass
class GazetteerEntry:
    name: str
    country: str
    admin1: str
    lat: float
    lon: float
    population: int = 0
    alt_names: list[str] = field(default_factory=list)


# â”€â”€â”€ Resolved location â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@dataclass
class ResolvedLocation:
    name: str
    lat: float
    lon: float
    country: str = ""
    admin1: str = ""
    timezone: str = "auto"
    confidence: float = 0.0
    source: str = ""  # "openmeteo", "nominatim", "gazetteer", "alias_cache"


# â”€â”€â”€ Main resolver â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class LocationResolver:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        open_meteo_url: str = "https://geocoding-api.open-meteo.com/v1/search",
        cache_dir: Path | None = None,
    ) -> None:
        self._http = http_client
        self._open_meteo_url = open_meteo_url
        self._cache_dir = cache_dir or Path(".")
        self._alias_cache: dict[str, dict[str, Any]] = {}
        self._gazetteer: list[GazetteerEntry] = []
        self._gazetteer_loaded = False
        self._load_alias_cache()

    # â”€â”€ Public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def resolve(self, raw_query: str, language: str = "ru") -> ResolvedLocation:
        """Resolve a natural-language location query into coordinates."""
        # Step 1: Normalize and extract location phrase
        location = self._extract_location_phrase(raw_query)
        if not location:
            raise LocationResolverError("location_not_found")

        # Step 2: Check alias cache (exact + normalized)
        cached = self._check_alias_cache(location)
        if cached is not None:
            return cached

        # Step 3: Generate candidates
        candidates = self._generate_candidates(location)

        # Step 4: Cascading search through external APIs
        result = await self._search_external(candidates, language)
        if result is not None:
            self._save_alias(location, result)
            return result

        # Step 5: Fuzzy search local gazetteer
        await self._ensure_gazetteer_loaded()
        result = self._fuzzy_search_gazetteer(location, candidates)
        if result is not None:
            # Re-verify with API using canonical name
            verified = await self._search_external([result.name], language)
            if verified is not None:
                self._save_alias(location, verified)
                return verified
            # Return gazetteer result even without API verification
            result.source = "gazetteer"
            self._save_alias(location, result)
            return result

        # Step 6: Return suggestions if available
        suggestions = self._get_suggestions(location, candidates)
        if suggestions:
            raise LocationResolverError("ambiguous", suggestions=suggestions)

        raise LocationResolverError("location_not_found")

    # â”€â”€ Step 1: Extract location phrase â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _extract_location_phrase(self, raw: str) -> str | None:
        """Extract the location name from a natural language query."""
        text = raw.strip()
        if not text:
            return None

        # Try regex patterns first (most reliable)
        patterns = [
            # "Ð¿Ð¾Ð³Ð¾Ð´Ð° Ð² <location>" / "weather in <location>"
            r"(?:\u043f\u043e\u0433\u043e\u0434\w*|\u043f\u0440\u043e\u0433\u043d\u043e\u0437\w*|\u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\w*|weather|forecast|temperature)\s+(?:\u0432\u043e?|\u0443|in|for)\s+(.+?)(?:\s+(?:\u0441\u044c\u043e\u0433\u043e\u0434\u043d\u0456|\u0437\u0430\u0432\u0442\u0440\u0430|\u0441\u0435\u0433\u043e\u0434\u043d\u044f|today|tomorrow|now))?$",
            # "<location> weather"
            r"^(.+?)\s+(?:\u043f\u043e\u0433\u043e\u0434\w*|\u043f\u0440\u043e\u0433\u043d\u043e\u0437\w*|weather|forecast)$",
            # "Ð² <location>" (general preposition)
            r"(?:\u0432\u043e?|\u0443|in|for)\s+(.+?)(?:\s+(?:\u0441\u044c\u043e\u0433\u043e\u0434\u043d\u0456|\u0437\u0430\u0432\u0442\u0440\u0430|\u0441\u0435\u0433\u043e\u0434\u043d\u044f|today|tomorrow|now))?$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip(" ,.-")
                if candidate:
                    return self._clean_candidate(candidate)

        # Fallback: strip noise words and take remaining tokens
        tokens = text.split()
        cleaned = [t for t in tokens if t.casefold() not in NOISE_WORDS]
        result = " ".join(cleaned).strip(" ,.-")
        if result and len(result) >= 2:
            return self._clean_candidate(result)

        return None

    def _clean_candidate(self, text: str) -> str | None:
        """Clean extracted candidate text."""
        # Remove punctuation, emojis, extra spaces
        cleaned = re.sub(r"[^\w\s\u0400-\u04FF\u00C0-\u024F\u1E00-\u1EFF'-]", " ", text)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.-")
        if not cleaned or len(cleaned) < 2:
            return None
        return cleaned

    # â”€â”€ Step 2: Alias cache â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    _CACHE_TTL_SECONDS = 30 * 86400  # 30 days

    def _check_alias_cache(self, location: str) -> ResolvedLocation | None:
        """Check if we've seen this location before."""
        import time

        key = _normalize_text(location)
        # Exact match
        if key in self._alias_cache:
            entry = self._alias_cache[key]
            # Check TTL
            saved_at = entry.get("_saved_at", 0)
            if saved_at and (time.time() - saved_at) > self._CACHE_TTL_SECONDS:
                del self._alias_cache[key]
                return None
            return ResolvedLocation(
                name=entry["canonical_name"],
                lat=entry["lat"],
                lon=entry["lon"],
                country=entry.get("country", ""),
                admin1=entry.get("admin1", ""),
                timezone=entry.get("timezone", "auto"),
                confidence=0.95,
                source="alias_cache",
            )
        # Try without country suffix
        for suffix in (
            ", \u0443\u043a\u0440\u0430\u0457\u043d\u0430",
            ", \u0443\u043a\u0440\u0430\u0438\u043d\u0430",
            ", ukraine",
        ):
            if key.endswith(suffix):
                base = key[: -len(suffix)].strip()
                if base in self._alias_cache:
                    entry = self._alias_cache[base]
                    saved_at = entry.get("_saved_at", 0)
                    if saved_at and (time.time() - saved_at) > self._CACHE_TTL_SECONDS:
                        del self._alias_cache[base]
                        return None
                    return ResolvedLocation(
                        name=entry["canonical_name"],
                        lat=entry["lat"],
                        lon=entry["lon"],
                        country=entry.get("country", ""),
                        admin1=entry.get("admin1", ""),
                        timezone=entry.get("timezone", "auto"),
                        confidence=0.90,
                        source="alias_cache",
                    )
        return None

    def _save_alias(self, original_query: str, location: ResolvedLocation) -> None:
        """Save a successful resolution to the alias cache. Only caches API-verified results."""
        import time

        # Only cache results from external APIs, not gazetteer-only guesses
        if location.source not in ("openmeteo", "nominatim"):
            return
        if location.confidence < 0.7:
            return
        key = _normalize_text(original_query)
        self._alias_cache[key] = {
            "canonical_name": location.name,
            "lat": location.lat,
            "lon": location.lon,
            "country": location.country,
            "admin1": location.admin1,
            "timezone": location.timezone,
            "_saved_at": time.time(),
            "_source": location.source,
        }
        # Also save canonical name as alias
        canonical_key = _normalize_text(location.name)
        if canonical_key != key:
            self._alias_cache[canonical_key] = self._alias_cache[key]
        self._save_alias_cache()

    def _load_alias_cache(self) -> None:
        path = self._cache_dir / "location_aliases.json"
        if path.exists():
            try:
                self._alias_cache = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                self._alias_cache = {}

    def _save_alias_cache(self) -> None:
        path = self._cache_dir / "location_aliases.json"
        try:
            atomic_write_json_sync(path, self._alias_cache, indent=1)
        except Exception:
            pass

    # â”€â”€ Step 3: Generate candidates â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _generate_candidates(self, location: str) -> list[str]:
        """Generate multiple search candidates from a location name."""
        seen: set[str] = set()
        candidates: list[str] = []

        def _add(v: str):
            v = v.strip()
            key = v.casefold()
            if key and key not in seen and len(v) >= 2:
                seen.add(key)
                candidates.append(v)

        # Original
        _add(location)

        # Apply case ending transformations
        lower = location.casefold()
        for ending, replacement in _CASE_RULES:
            if lower.endswith(ending) and len(lower) > len(ending) + 2:
                _add(location[: -len(ending)] + replacement)

        # For Cyrillic: add country variants and cross-language variants
        if _is_cyrillic(location):
            for country in (
                "\u0423\u043a\u0440\u0430\u0457\u043d\u0430",
                "\u0423\u043a\u0440\u0430\u0438\u043d\u0430",
            ):
                for v in list(candidates[:4]):  # only top variants
                    if country.casefold() not in v.casefold():
                        _add(f"{v}, {country}")

            # Ukrainian â†” Russian letter swaps (common mistakes)
            swaps = (
                ("\u0456", "\u0438"),  # Ñ– â†” Ð¸
                ("\u0457", "\u0438"),  # Ñ— â†” Ð¸
                ("\u0454", "\u0435"),  # Ñ” â†” Ðµ
                ("\u0491", "\u0433"),  # Ò‘ â†” Ð³
                ("\u0449", "\u0448\u0447"),  # Ñ‰ â†” ÑˆÑ‡
            )
            for orig_candidates in list(candidates):
                for from_ch, to_ch in swaps:
                    if from_ch in orig_candidates.casefold():
                        _add(orig_candidates.replace(from_ch, to_ch))
                    if to_ch in orig_candidates.casefold():
                        _add(orig_candidates.replace(to_ch, from_ch))

        # For non-Cyrillic: try transliteration variants
        if not _is_cyrillic(location) and len(location) > 3:
            _add(location.capitalize())

        return candidates

    # â”€â”€ Step 4: External API search â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _search_external(
        self, candidates: list[str], language: str
    ) -> ResolvedLocation | None:
        """Try Open-Meteo and Nominatim with each candidate."""
        lang_param = "ru" if language in ("ru", "uk") else "en"

        for candidate in candidates:
            # Try Open-Meteo
            try:
                resp = await self._http.get(
                    self._open_meteo_url,
                    params={
                        "name": candidate,
                        "count": 5,
                        "language": lang_param,
                        "format": "json",
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    results = resp.json().get("results") or []
                    if results:
                        best = max(results, key=lambda r: r.get("population", 0))
                        return ResolvedLocation(
                            name=best.get("name", candidate),
                            lat=float(best["latitude"]),
                            lon=float(best["longitude"]),
                            country=best.get("country", ""),
                            admin1=best.get("admin1", ""),
                            timezone=best.get("timezone", "auto"),
                            confidence=0.9,
                            source="openmeteo",
                        )
            except Exception:
                pass

            # Try Nominatim
            try:
                resp = await self._http.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        "q": candidate,
                        "format": "json",
                        "limit": 5,
                        "accept-language": lang_param,
                    },
                    headers={"User-Agent": "Project Assistant/1.0"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    results = resp.json() or []
                    if results:
                        best = results[0]
                        display = best.get("display_name", "")
                        parts = [p.strip() for p in display.split(",")]
                        return ResolvedLocation(
                            name=parts[0] if parts else candidate,
                            lat=float(best["lat"]),
                            lon=float(best["lon"]),
                            country=parts[-1].strip() if parts else "",
                            admin1=parts[-2].strip() if len(parts) > 1 else "",
                            timezone="auto",
                            confidence=0.85,
                            source="nominatim",
                        )
            except Exception:
                pass

        return None

    # â”€â”€ Step 5: Local gazetteer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _ensure_gazetteer_loaded(self) -> None:
        if self._gazetteer_loaded:
            return
        self._gazetteer_loaded = True
        gazetteer_path = self._cache_dir / "gazetteer.json"
        if gazetteer_path.exists():
            try:
                data = json.loads(gazetteer_path.read_text(encoding="utf-8"))
                for item in data:
                    self._gazetteer.append(
                        GazetteerEntry(
                            name=item["name"],
                            country=item.get("country", ""),
                            admin1=item.get("admin1", ""),
                            lat=float(item.get("lat", 0)),
                            lon=float(item.get("lon", 0)),
                            population=int(item.get("population", 0)),
                            alt_names=item.get("alt_names", []),
                        )
                    )
            except Exception:
                pass

    def _fuzzy_search_gazetteer(
        self, query: str, candidates: list[str]
    ) -> ResolvedLocation | None:
        """Fuzzy match against local gazetteer with typo tolerance."""
        if not self._gazetteer:
            return None

        query_norm = _normalize_text(query)
        best_match: GazetteerEntry | None = None
        best_score = 0.0

        search_terms = [_normalize_text(c) for c in candidates]
        search_terms.append(query_norm)

        for entry in self._gazetteer:
            entry_names = [_normalize_text(entry.name)] + [
                _normalize_text(a) for a in entry.alt_names
            ]

            for entry_name in entry_names:
                for search_term in search_terms:
                    if not entry_name or not search_term:
                        continue

                    # Exact match
                    if search_term == entry_name:
                        score = 1.0
                    # Standard fuzzy match
                    else:
                        score = SequenceMatcher(None, search_term, entry_name).ratio()

                    # Typo tolerance: try swapping adjacent chars
                    if score < 0.85:
                        typo_score = self._typo_similarity(search_term, entry_name)
                        score = max(score, typo_score)

                    # Prefix match (short query like "Ð´Ð°Ð²Ð¸Ð´" for "Ð´Ð°Ð²Ð¸Ð´Ñ–Ð²Ñ†Ñ–")
                    if len(search_term) >= 4 and entry_name.startswith(search_term):
                        score = max(
                            score, 0.75 + (len(search_term) / len(entry_name)) * 0.2
                        )

                    # Bonus for population
                    pop_bonus = min(entry.population / 1_000_000, 0.1)
                    total = score + pop_bonus
                    if total > best_score and score > 0.5:
                        best_score = total
                        best_match = entry

        if best_match and best_score > 0.5:
            return ResolvedLocation(
                name=best_match.name,
                lat=best_match.lat,
                lon=best_match.lon,
                country=best_match.country,
                admin1=best_match.admin1,
                confidence=min(best_score, 0.95),
                source="gazetteer",
            )
        return None

    def _typo_similarity(self, a: str, b: str) -> float:
        """Compare strings with typo tolerance (adjacent swaps, missing/extra chars)."""
        if len(a) < 3 or len(b) < 3:
            return 0.0

        best = 0.0

        # Try swapping adjacent characters (common typo)
        for i in range(len(a) - 1):
            swapped = a[:i] + a[i + 1] + a[i] + a[i + 2 :]
            score = SequenceMatcher(None, swapped, b).ratio()
            best = max(best, score)

        # Try removing one character (extra letter typo)
        for i in range(len(a)):
            removed = a[:i] + a[i + 1 :]
            score = SequenceMatcher(None, removed, b).ratio()
            best = max(best, score)

        # Try inserting one character (missing letter typo)
        for i in range(len(a) + 1):
            for c in "Ð°Ð±Ð²Ð³Ò‘Ð´ÐµÑ”Ð¶Ð·Ð¸Ñ–Ñ—Ð¹ÐºÐ»Ð¼Ð½Ð¾Ð¿Ñ€ÑÑ‚ÑƒÑ„Ñ…Ñ†Ñ‡ÑˆÑ‰ÑŒÑŽÑ":
                inserted = a[:i] + c + a[i:]
                score = SequenceMatcher(None, inserted, b).ratio()
                best = max(best, score)
                if best > 0.85:
                    return best

        return best

    # â”€â”€ Step 6: Suggestions fallback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _get_suggestions(self, query: str, candidates: list[str]) -> list[str]:
        """Get top suggestions when exact match fails."""
        if not self._gazetteer:
            return []

        query_norm = _normalize_text(query)
        scored: list[tuple[float, str]] = []

        search_terms = [_normalize_text(c) for c in candidates]
        search_terms.append(query_norm)

        for entry in self._gazetteer:
            entry_names = [_normalize_text(entry.name)] + [
                _normalize_text(a) for a in entry.alt_names
            ]
            for entry_name in entry_names:
                for search_term in search_terms:
                    if entry_name and search_term:
                        score = SequenceMatcher(None, search_term, entry_name).ratio()
                        if score > 0.5:
                            label = f"{entry.name}"
                            if entry.admin1:
                                label += f", {entry.admin1}"
                            if entry.country:
                                label += f", {entry.country}"
                            scored.append((score, label))

        scored.sort(key=lambda x: -x[0])
        seen: set[str] = set()
        suggestions: list[str] = []
        for _, label in scored:
            if label not in seen and len(suggestions) < 5:
                seen.add(label)
                suggestions.append(label)
        return suggestions


class LocationResolverError(Exception):
    def __init__(self, message: str, suggestions: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.suggestions = suggestions or []

