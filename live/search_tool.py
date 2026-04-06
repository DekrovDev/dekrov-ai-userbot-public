from __future__ import annotations

import asyncio
import html
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import quote_plus, urlparse

import httpx

from config.settings import AppConfig

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - optional dependency
    BeautifulSoup = None

try:
    from duckduckgo_search import DDGS
except Exception:  # pragma: no cover - optional dependency
    DDGS = None

try:
    from googlesearch import search as google_search
except Exception:  # pragma: no cover - optional dependency
    google_search = None

try:
    from newspaper import Article
except Exception:  # pragma: no cover - optional dependency
    Article = None

try:
    import trafilatura
except Exception:  # pragma: no cover - optional dependency
    trafilatura = None

try:
    from readability import Document
except Exception:  # pragma: no cover - optional dependency
    Document = None


LOGGER = logging.getLogger("assistant.search")

TAG_RE = re.compile(r"<[^>]+>")
TITLE_RE = re.compile(r"<title[^>]*>(?P<title>.*?)</title>", re.IGNORECASE | re.DOTALL)
RESULT_LINK_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
RESULT_SNIPPET_RE = re.compile(
    r'<a[^>]+class="result__snippet"[^>]*>(?P<snippet>.*?)</a>|<div[^>]+class="result__snippet"[^>]*>(?P<snippet_div>.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
WORD_RE = re.compile(
    r"[A-Za-z\u0400-\u04FF0-9][A-Za-z\u0400-\u04FF0-9_./:+-]*", re.UNICODE
)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
NOISE_PATTERNS = (
    re.compile(
        r"(?iu)\b(?:Ð½Ð°Ð¹Ð´Ð¸|Ð¿Ð¾Ð¸Ñ‰Ð¸|Ð¸Ñ‰Ð¸|Ð·Ð°Ð³ÑƒÐ³Ð»Ð¸|Ð¿Ð¾ÑÐ¼Ð¾Ñ‚Ñ€Ð¸|show|find|search|look up|look for|check)\b"
    ),
    re.compile(
        r"(?iu)\b(?:Ð²\s+Ð¸Ð½Ñ‚ÐµÑ€Ð½ÐµÑ‚Ðµ|Ð²\s+Ð³ÑƒÐ³Ð»Ðµ|Ð¾Ð½Ð»Ð°Ð¹Ð½|online|internet|web|google)\b"
    ),
    re.compile(r"(?iu)\b(?:Ð¸Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸Ñ|Ð¸Ð½Ñ„Ð¾|info|information|please|pls|Ð¿Ð¾Ð¶Ð°Ð»ÑƒÐ¹ÑÑ‚Ð°)\b"),
)
ABOUT_PATTERNS = (
    re.compile(r"(?iu)\b(?:Ð¿Ñ€Ð¾|Ð¾Ð±|Ð¾|about|regarding|on)\s+(.+)$"),
    re.compile(
        r"(?iu)\b(?:ÐºÑ‚Ð¾\s+Ñ‚Ð°ÐºÐ¾Ð¹|Ñ‡Ñ‚Ð¾\s+Ñ‚Ð°ÐºÐ¾Ðµ|who\s+is|what\s+is|how\s+old\s+is)\s+(.+)$"
    ),
)
TECH_QUERY_HINTS = (
    "github",
    "repo",
    "repository",
    "library",
    "package",
    "sdk",
    "api",
    "python",
    "javascript",
    "typescript",
    "java",
    "golang",
    "rust",
    "npm",
    "pip",
    "pypi",
    "open source",
    "framework",
    "tooling",
    "issue",
    "issues",
)
ENCYCLOPEDIA_HINTS = (
    "ÐºÑ‚Ð¾",
    "Ñ‡Ñ‚Ð¾ Ñ‚Ð°ÐºÐ¾Ðµ",
    "ÑÐºÐ¾Ð»ÑŒÐºÐ¾ Ð»ÐµÑ‚",
    "Ð±Ð¸Ð¾Ð³Ñ€Ð°Ñ„Ð¸Ñ",
    "Ñ€Ð¾Ð´Ð¸Ð»ÑÑ",
    "ÑƒÐ¼ÐµÑ€",
    "Ð²Ð¾Ð·Ñ€Ð°ÑÑ‚",
    "when was",
    "how old",
    "who is",
    "what is",
    "born",
    "biography",
    "age",
)
NEWS_HINTS = (
    "Ð½Ð¾Ð²Ð¾ÑÑ‚Ð¸",
    "news",
    "latest",
    "recent",
    "ÑÐµÐ³Ð¾Ð´Ð½Ñ",
    "Ð²Ñ‡ÐµÑ€Ð°",
    "headline",
    "headlines",
)
TRUSTED_DOMAIN_SCORES = {
    "wikipedia.org": 1.8,
    "github.com": 1.7,
    "docs.python.org": 1.5,
    "developer.mozilla.org": 1.5,
    "openai.com": 1.4,
    "bbc.com": 1.3,
    "reuters.com": 1.3,
    "apnews.com": 1.3,
}
BLOCKED_DOMAINS = {
    "pinterest.com",
}


class SearchToolError(RuntimeError):
    pass


@dataclass(slots=True)
class SearchHit:
    title: str
    url: str | None
    snippet: str
    source: str | None = None
    published_at: str | None = None
    provider: str | None = None
    article_text: str | None = None
    domain: str | None = None
    score: float = 0.0
    query_variant: str | None = None


@dataclass(slots=True)
class QueryPlan:
    query_type: str
    language_hint: str
    variants: list[str]


class SearchTool:
    def __init__(
        self,
        client: httpx.AsyncClient,
        config: AppConfig,
        limiter=None,  # RateLimiter | None
    ) -> None:
        self._client = client
        self._config = config
        self._limiter = limiter

    async def _rate_limited_get(
        self, key: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        """Ð’Ñ‹Ð¿Ð¾Ð»Ð½Ð¸Ñ‚ÑŒ GET Ð·Ð°Ð¿Ñ€Ð¾Ñ Ñ rate limiting."""
        if self._limiter:
            return await self._limiter.execute_with_retry(
                key,
                lambda: self._client.get(url, **kwargs),
            )
        return await self._client.get(url, **kwargs)

    async def search_news(
        self, query: str, *, limit: int = 3, language: str = "en"
    ) -> list[SearchHit]:
        news_locale = "ru" if language == "ru" else "en"
        news_country = "RU" if language == "ru" else "US"
        url = (
            f"{self._config.google_news_rss_url}"
            f"?q={quote_plus(query)}&hl={news_locale}&gl={news_country}&ceid={news_country}:{news_locale}"
        )
        response = await self._rate_limited_get(
            "google",
            url,
            timeout=self._config.live_data_timeout_seconds,
            headers={"User-Agent": self._config.live_data_user_agent},
        )
        response.raise_for_status()

        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            raise SearchToolError("news_parse_failed") from exc

        hits: list[SearchHit] = []
        for item in root.findall(".//item"):
            title = self._clean_text(item.findtext("title"))
            link = self._clean_text(item.findtext("link"))
            source = self._clean_text(item.findtext("source"))
            published_at = self._clean_text(item.findtext("pubDate"))
            if not title:
                continue
            hits.append(
                SearchHit(
                    title=title,
                    url=link or None,
                    snippet="",
                    source=source or "Google News",
                    published_at=published_at or None,
                    provider="google_news_rss",
                    domain=self._extract_domain(link),
                )
            )
            if len(hits) >= limit:
                break
        return hits

    async def search_web(self, query: str, *, limit: int = 3) -> list[SearchHit]:
        normalized_query = " ".join((query or "").split()).strip()
        if not normalized_query:
            return []

        plan = self._build_query_plan(normalized_query)
        raw_hits: list[SearchHit] = []
        per_provider_limit = max(limit + 2, 4)

        for variant in plan.variants:
            raw_hits.extend(
                await self._search_variant(plan, variant, limit=per_provider_limit)
            )

        normalized_hits = self._normalize_hits(raw_hits, normalized_query)
        deduped_hits = self._dedupe_hits(normalized_hits)
        scored_hits = self._score_hits(deduped_hits, normalized_query, plan.query_type)
        top_hits = scored_hits[: max(limit, self._config.search_top_k)]
        await self._enrich_article_texts(top_hits, plan.query_type)
        rescored_hits = self._score_hits(top_hits, normalized_query, plan.query_type)
        return rescored_hits[:limit]

    def _build_query_plan(self, query: str) -> QueryPlan:
        normalized = " ".join((query or "").split()).strip()
        lowered = normalized.casefold()
        language_hint = "ru" if re.search(r"[\u0400-\u04FF]", normalized) else "en"
        if any(marker in lowered for marker in TECH_QUERY_HINTS):
            query_type = "tech"
        elif any(marker in lowered for marker in NEWS_HINTS):
            query_type = "news"
        elif any(marker in lowered for marker in ENCYCLOPEDIA_HINTS):
            query_type = "encyclopedia"
        else:
            query_type = "general"
        variants = self._build_query_variants(
            normalized, query_type=query_type, language_hint=language_hint
        )
        return QueryPlan(
            query_type=query_type, language_hint=language_hint, variants=variants
        )

    def _build_query_variants(
        self, query: str, *, query_type: str, language_hint: str
    ) -> list[str]:
        normalized = " ".join((query or "").split()).strip()
        variants: list[str] = []
        seen: set[str] = set()

        def add(value: str) -> None:
            cleaned = " ".join((value or "").split()).strip(" .,!?:;")
            if len(cleaned) < 2:
                return
            lowered = cleaned.casefold()
            if lowered in seen:
                return
            seen.add(lowered)
            variants.append(cleaned)

        add(normalized)

        simplified = normalized
        for pattern in NOISE_PATTERNS:
            simplified = pattern.sub(" ", simplified)
        simplified = " ".join(simplified.split()).strip(" .,!?:;")
        add(simplified)

        for pattern in ABOUT_PATTERNS:
            match = pattern.search(normalized)
            if match:
                add(match.group(1))
            match = pattern.search(simplified)
            if match:
                add(match.group(1))

        if query_type == "encyclopedia":
            core = variants[-1] if variants else normalized
            add(f"{core} wikipedia")
        if query_type == "tech":
            core = variants[-1] if variants else normalized
            add(f"{core} github")
        if language_hint == "ru":
            latin_tokens = [
                token
                for token in WORD_RE.findall(normalized)
                if re.search(r"[A-Za-z]", token)
            ]
            if latin_tokens:
                add(" ".join(latin_tokens))

        return variants[:4]

    async def _search_variant(
        self, plan: QueryPlan, variant: str, *, limit: int
    ) -> list[SearchHit]:
        hits: list[SearchHit] = []
        if self._config.enable_searxng_search:
            hits.extend(await self._try_provider(self._search_searxng, variant, limit))
        if self._config.enable_duckduckgo_search:
            hits.extend(
                await self._try_provider(
                    self._search_duckduckgo_library, variant, limit
                )
            )
            hits.extend(
                await self._try_provider(
                    self._search_duckduckgo_instant, variant, limit
                )
            )
            hits.extend(
                await self._try_provider(self._search_duckduckgo_html, variant, limit)
            )
        if self._config.enable_google_search:
            hits.extend(
                await self._try_provider(self._search_google_library, variant, limit)
            )
        if self._config.enable_wikipedia_search and plan.query_type in {
            "encyclopedia",
            "general",
        }:
            hits.extend(
                await self._try_provider(self._search_wikipedia, variant, limit)
            )
        if self._config.enable_github_search and plan.query_type == "tech":
            hits.extend(await self._try_provider(self._search_github, variant, limit))

        for hit in hits:
            if not hit.query_variant:
                hit.query_variant = variant
        return hits

    async def _try_provider(self, provider, query: str, limit: int) -> list[SearchHit]:
        try:
            return await provider(query, limit=limit)
        except (httpx.HTTPError, SearchToolError):
            LOGGER.exception(
                "search_provider_failed provider=%s query=%s", provider.__name__, query
            )
        except Exception:
            LOGGER.exception(
                "search_provider_unexpected_error provider=%s query=%s",
                provider.__name__,
                query,
            )
        return []

    async def _search_searxng(self, query: str, *, limit: int) -> list[SearchHit]:
        response = await self._rate_limited_get(
            "searxng",
            self._config.searxng_search_url,
            params={"q": query, "format": "json", "language": "all", "safesearch": 0},
            timeout=self._config.live_data_timeout_seconds,
            headers={"User-Agent": self._config.live_data_user_agent},
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") or []
        hits: list[SearchHit] = []
        for row in results[:limit]:
            title = self._clean_text(row.get("title"))
            url = self._clean_text(row.get("url"))
            snippet = self._clean_text(row.get("content"))
            engines = row.get("engines") or []
            published_at = self._clean_text(
                row.get("publishedDate") or row.get("published_date")
            )
            if not title and not url:
                continue
            hits.append(
                SearchHit(
                    title=title or url or query,
                    url=url or None,
                    snippet=snippet,
                    source="SearXNG",
                    published_at=published_at or None,
                    provider="searxng",
                    domain=self._extract_domain(url),
                )
            )
            if engines and not hits[-1].source:
                hits[-1].source = ", ".join(str(engine) for engine in engines)
        return hits

    async def _search_duckduckgo_library(
        self, query: str, *, limit: int
    ) -> list[SearchHit]:
        if DDGS is None:
            return []

        def _run() -> list[dict]:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=limit))

        rows = await asyncio.to_thread(_run)
        hits: list[SearchHit] = []
        for row in rows[:limit]:
            title = self._clean_text(row.get("title"))
            url = self._clean_text(row.get("href") or row.get("url"))
            snippet = self._clean_text(row.get("body") or row.get("snippet"))
            if not title and not url:
                continue
            hits.append(
                SearchHit(
                    title=title or url or query,
                    url=url or None,
                    snippet=snippet,
                    source="DuckDuckGo",
                    provider="duckduckgo_search",
                    domain=self._extract_domain(url),
                )
            )
        return hits

    async def _search_duckduckgo_instant(
        self, query: str, *, limit: int
    ) -> list[SearchHit]:
        response = await self._rate_limited_get(
            "duckduckgo",
            self._config.duckduckgo_instant_url,
            params={
                "q": query,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1,
                "no_redirect": 1,
            },
            timeout=self._config.live_data_timeout_seconds,
            headers={"User-Agent": self._config.live_data_user_agent},
        )
        response.raise_for_status()
        payload = response.json()

        hits: list[SearchHit] = []
        answer = self._clean_text(payload.get("Answer"))
        abstract = self._clean_text(payload.get("AbstractText"))
        abstract_url = self._clean_text(payload.get("AbstractURL"))
        heading = self._clean_text(payload.get("Heading")) or query

        if answer:
            hits.append(
                SearchHit(
                    title=heading,
                    url=abstract_url or None,
                    snippet=answer,
                    source="DuckDuckGo Instant",
                    provider="duckduckgo_instant",
                    domain=self._extract_domain(abstract_url),
                )
            )
        if abstract and abstract != answer:
            hits.append(
                SearchHit(
                    title=heading,
                    url=abstract_url or None,
                    snippet=abstract,
                    source="DuckDuckGo Instant",
                    provider="duckduckgo_instant",
                    domain=self._extract_domain(abstract_url),
                )
            )

        for related in payload.get("RelatedTopics") or []:
            if isinstance(related, dict) and "Text" in related:
                text = self._clean_text(related.get("Text"))
                if text:
                    url = self._clean_text(related.get("FirstURL"))
                    hits.append(
                        SearchHit(
                            title=heading,
                            url=url or None,
                            snippet=text,
                            source="DuckDuckGo Instant",
                            provider="duckduckgo_instant",
                            domain=self._extract_domain(url),
                        )
                    )
            if len(hits) >= limit:
                break
        return hits[:limit]

    async def _search_duckduckgo_html(
        self, query: str, *, limit: int
    ) -> list[SearchHit]:
        response = await self._rate_limited_get(
            "duckduckgo",
            self._config.duckduckgo_html_url,
            params={"q": query},
            timeout=self._config.live_data_timeout_seconds,
            headers={"User-Agent": self._config.live_data_user_agent},
        )
        response.raise_for_status()

        html_text = response.text
        links = list(RESULT_LINK_RE.finditer(html_text))
        snippets = list(RESULT_SNIPPET_RE.finditer(html_text))

        hits: list[SearchHit] = []
        for index, match in enumerate(links[:limit]):
            title = self._clean_html(match.group("title"))
            href = html.unescape(match.group("href"))
            snippet_match = snippets[index] if index < len(snippets) else None
            snippet = ""
            if snippet_match is not None:
                snippet = self._clean_html(
                    snippet_match.group("snippet")
                    or snippet_match.group("snippet_div")
                    or ""
                )
            if not title and not href:
                continue
            hits.append(
                SearchHit(
                    title=title or href or query,
                    url=href or None,
                    snippet=snippet,
                    source="DuckDuckGo HTML",
                    provider="duckduckgo_html",
                    domain=self._extract_domain(href),
                )
            )
        return hits

    async def _search_google_library(
        self, query: str, *, limit: int
    ) -> list[SearchHit]:
        if google_search is None:
            return []

        def _run() -> list[str]:
            results = google_search(
                query,
                num_results=limit,
                sleep_interval=max(0.0, self._config.google_search_pause_seconds),
            )
            return list(results)

        urls = await asyncio.to_thread(_run)
        hits: list[SearchHit] = []
        for url in urls[:limit]:
            cleaned_url = self._clean_text(url)
            if not cleaned_url:
                continue
            title = await self._fetch_page_title(cleaned_url)
            hits.append(
                SearchHit(
                    title=title or cleaned_url,
                    url=cleaned_url,
                    snippet="",
                    source="Google Search",
                    provider="google_search",
                    domain=self._extract_domain(cleaned_url),
                )
            )
        return hits

    async def _search_wikipedia(self, query: str, *, limit: int) -> list[SearchHit]:
        response = await self._rate_limited_get(
            "wikipedia",
            self._config.wikipedia_api_url,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "utf8": 1,
                "format": "json",
                "srlimit": limit,
            },
            timeout=self._config.live_data_timeout_seconds,
            headers={"User-Agent": self._config.live_data_user_agent},
        )
        response.raise_for_status()
        payload = response.json()
        results = ((payload.get("query") or {}).get("search") or [])[:limit]
        hits: list[SearchHit] = []
        for row in results:
            title = self._clean_text(row.get("title"))
            snippet = self._clean_html(row.get("snippet") or "")
            if not title:
                continue
            url_title = quote_plus(title.replace(" ", "_"))
            hits.append(
                SearchHit(
                    title=title,
                    url=f"https://ru.wikipedia.org/wiki/{url_title}",
                    snippet=snippet,
                    source="Wikipedia",
                    provider="wikipedia_api",
                    domain="wikipedia.org",
                )
            )
        return hits

    async def _search_github(self, query: str, *, limit: int) -> list[SearchHit]:
        headers = {"User-Agent": self._config.live_data_user_agent}
        if self._config.github_token:
            headers["Authorization"] = f"Bearer {self._config.github_token}"
        response = await self._rate_limited_get(
            "github",
            self._config.github_search_api_url,
            params={
                "q": query,
                "sort": "updated",
                "order": "desc",
                "per_page": max(1, min(10, limit)),
            },
            timeout=self._config.live_data_timeout_seconds,
            headers=headers,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items") or []
        hits: list[SearchHit] = []
        for item in items[:limit]:
            full_name = self._clean_text(item.get("full_name"))
            html_url = self._clean_text(item.get("html_url"))
            description = self._clean_text(item.get("description"))
            updated_at = self._clean_text(item.get("updated_at"))
            if not full_name and not html_url:
                continue
            hits.append(
                SearchHit(
                    title=full_name or html_url or query,
                    url=html_url or None,
                    snippet=description,
                    source="GitHub",
                    published_at=updated_at or None,
                    provider="github_api",
                    domain="github.com",
                )
            )
        return hits

    def _normalize_hits(self, hits: list[SearchHit], query: str) -> list[SearchHit]:
        normalized: list[SearchHit] = []
        for hit in hits:
            title = self._clean_text(hit.title)
            url = self._clean_text(hit.url)
            snippet = self._clean_text(hit.snippet)
            domain = hit.domain or self._extract_domain(url)
            if not title and not url:
                continue
            if domain in BLOCKED_DOMAINS:
                continue
            normalized.append(
                SearchHit(
                    title=title or url or query,
                    url=url or None,
                    snippet=snippet,
                    source=self._clean_text(hit.source),
                    published_at=self._clean_text(hit.published_at) or None,
                    provider=hit.provider,
                    article_text=hit.article_text,
                    domain=domain,
                    query_variant=hit.query_variant,
                    score=hit.score,
                )
            )
        return normalized

    def _dedupe_hits(self, hits: list[SearchHit]) -> list[SearchHit]:
        deduped: list[SearchHit] = []
        seen: set[str] = set()
        for hit in hits:
            key = ""
            if hit.url:
                key = hit.url.strip().casefold().rstrip("/")
            if not key:
                key = f"{(hit.domain or '').casefold()}::{(hit.title or '').casefold()}"
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(hit)
        return deduped

    def _score_hits(
        self, hits: list[SearchHit], query: str, query_type: str
    ) -> list[SearchHit]:
        query_tokens = {
            token.casefold() for token in WORD_RE.findall(query) if len(token) > 2
        }
        now_year = time.gmtime().tm_year
        scored: list[SearchHit] = []
        for hit in hits:
            haystack = " ".join(
                part
                for part in [
                    hit.title,
                    hit.snippet,
                    hit.article_text or "",
                    hit.domain or "",
                ]
                if part
            ).casefold()
            overlap = sum(1 for token in query_tokens if token in haystack)
            score = float(overlap)
            if hit.title:
                title_lower = hit.title.casefold()
                if any(token in title_lower for token in query_tokens):
                    score += 1.2
            if hit.provider == "searxng":
                score += 0.8
            if hit.provider == "google_search":
                score += 0.6
            if hit.provider == "duckduckgo_search":
                score += 0.5
            if hit.provider == "wikipedia_api" and query_type == "encyclopedia":
                score += 1.5
            if hit.provider == "github_api" and query_type == "tech":
                score += 1.6
            if hit.domain:
                for domain, bonus in TRUSTED_DOMAIN_SCORES.items():
                    if hit.domain.endswith(domain):
                        score += bonus
                        break
            year_matches = YEAR_RE.findall(
                " ".join(part for part in [hit.title, hit.snippet] if part)
            )
            if year_matches:
                score += 0.2
            if hit.published_at:
                published = hit.published_at
                if str(now_year) in published:
                    score += 0.8
                elif str(now_year - 1) in published:
                    score += 0.3
            if hit.article_text:
                score += 0.9
            hit.score = score
            scored.append(hit)
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored

    async def _enrich_article_texts(
        self, hits: list[SearchHit], query_type: str
    ) -> None:
        extract_limit = max(0, self._config.search_article_extract_limit)
        if extract_limit <= 0:
            return
        candidates = [
            hit for hit in hits if hit.url and hit.provider not in {"github_api"}
        ]
        for hit in candidates[:extract_limit]:
            article_excerpt = await self._extract_article_excerpt(hit.url)
            if not article_excerpt:
                continue
            hit.article_text = article_excerpt
            if not hit.snippet or len(hit.snippet) < 40:
                hit.snippet = article_excerpt
            if hit.provider == "wikipedia_api" and query_type == "encyclopedia":
                hit.score += 0.5

    async def _extract_article_excerpt(self, url: str | None) -> str:
        if not url:
            return ""
        html_text = await self._download_page_html(url)
        if not html_text:
            return ""
        for extractor in (
            self._extract_with_trafilatura,
            self._extract_with_readability,
            self._extract_with_newspaper,
            self._extract_with_bs4,
        ):
            text = await extractor(url, html_text)
            if text:
                return text
        return ""

    async def _download_page_html(self, url: str) -> str:
        try:
            response = await self._client.get(
                url,
                timeout=self._config.live_data_timeout_seconds,
                headers={"User-Agent": self._config.live_data_user_agent},
            )
            response.raise_for_status()
            return response.text or ""
        except Exception:
            LOGGER.debug("search_page_download_failed url=%s", url, exc_info=True)
            return ""

    async def _extract_with_trafilatura(self, url: str, html_text: str) -> str:
        del url
        if trafilatura is None:
            return ""

        def _run() -> str:
            extracted = (
                trafilatura.extract(
                    html_text, include_comments=False, include_tables=False
                )
                or ""
            )
            return self._truncate_text(extracted)

        try:
            return await asyncio.to_thread(_run)
        except Exception:
            LOGGER.debug("trafilatura_extraction_failed", exc_info=True)
            return ""

    async def _extract_with_readability(self, url: str, html_text: str) -> str:
        del url
        if Document is None or BeautifulSoup is None:
            return ""

        def _run() -> str:
            doc = Document(html_text)
            summary_html = doc.summary(html_partial=True)
            soup = BeautifulSoup(summary_html, "html.parser")
            text = " ".join(soup.get_text(" ", strip=True).split())
            return self._truncate_text(text)

        try:
            return await asyncio.to_thread(_run)
        except Exception:
            LOGGER.debug("readability_extraction_failed", exc_info=True)
            return ""

    async def _extract_with_newspaper(self, url: str, html_text: str) -> str:
        del html_text
        if not self._config.enable_newspaper_extraction or Article is None:
            return ""

        def _run() -> str:
            article = Article(url)
            article.download()
            article.parse()
            text = " ".join((article.text or "").split()).strip()
            return self._truncate_text(text)

        try:
            return await asyncio.to_thread(_run)
        except Exception:
            LOGGER.debug("newspaper_extraction_failed url=%s", url, exc_info=True)
            return ""

    async def _extract_with_bs4(self, url: str, html_text: str) -> str:
        del url
        if BeautifulSoup is None:
            return self._truncate_text(self._clean_html(html_text))

        def _run() -> str:
            soup = BeautifulSoup(html_text, "html.parser")
            for tag_name in (
                "script",
                "style",
                "noscript",
                "header",
                "footer",
                "nav",
                "aside",
            ):
                for tag in soup.find_all(tag_name):
                    tag.decompose()
            text = " ".join(soup.get_text(" ", strip=True).split())
            return self._truncate_text(text)

        try:
            return await asyncio.to_thread(_run)
        except Exception:
            LOGGER.debug("bs4_extraction_failed", exc_info=True)
            return ""

    async def _fetch_page_title(self, url: str) -> str:
        html_text = await self._download_page_html(url)
        if not html_text:
            return ""
        match = TITLE_RE.search(html_text)
        if not match:
            return ""
        return self._clean_html(match.group("title"))

    def _extract_domain(self, url: str | None) -> str | None:
        if not url:
            return None
        try:
            parsed = urlparse(url)
        except Exception:
            return None
        hostname = (parsed.netloc or "").casefold().strip()
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return hostname or None

    def _truncate_text(self, text: str, limit: int = 900) -> str:
        cleaned = " ".join((text or "").split()).strip()
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[:limit].rsplit(" ", 1)[0].rstrip(" .,;:") + "..."

    def _clean_html(self, raw_text: str) -> str:
        text = TAG_RE.sub(" ", raw_text or "")
        return self._clean_text(text)

    def _clean_text(self, raw_text: object) -> str:
        if raw_text is None:
            return ""
        text = html.unescape(str(raw_text))
        text = re.sub(r"\s{2,}", " ", text)
        return text.strip()

