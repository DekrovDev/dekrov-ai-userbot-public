from __future__ import annotations

import html
import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from config.settings import AppConfig

LOGGER = logging.getLogger("assistant.visitor.search")

GITHUB_API = "https://api.github.com"
TAG_RE = re.compile(r"<[^>]+>")
TITLE_RE = re.compile(
    r"<title[^>]*>(?P<title>.*?)</title>", re.IGNORECASE | re.DOTALL
)
URL_RE = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - optional dependency
    BeautifulSoup = None

PORTFOLIO_CACHE_TTL_SECONDS = 900
PORTFOLIO_MAX_PAGES = 5
PORTFOLIO_MAX_DEPTH = 2
PROJECT_LINK_HINTS = (
    "project",
    "projects",
    "work",
    "works",
    "portfolio",
    "case",
    "cases",
    "bot",
    "automation",
    "dashboard",
    "landing",
    "product",
)
PROJECT_CONTENT_HINTS = (
    "project",
    "projects",
    "portfolio",
    "bot",
    "automation",
    "dashboard",
    "landing",
    "system",
    "interface",
    "product",
)
SKIP_FILE_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".rar",
    ".7z",
    ".mp4",
    ".mp3",
)
_PORTFOLIO_CACHE: dict[str, tuple[float, list["PortfolioPage"]]] = {}


@dataclass(slots=True)
class PortfolioPage:
    url: str
    title: str
    snippet: str
    anchor_text: str = ""
    depth: int = 0
    score: float = 0.0

# Technology â†’ owner connection mapping
TECH_CONNECTIONS = {
    "python": "ProjectOwner Ð°ÐºÑ‚Ð¸Ð²Ð½Ð¾ Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÑ‚ Python Ð´Ð»Ñ Ð±Ð¾Ñ‚Ð¾Ð² Ð¸ Ð°Ð²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ð·Ð°Ñ†Ð¸Ð¸.",
    "linux": "ProjectOwner Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÑ‚ Ð½Ð° Linux Ð´Ð»Ñ Ñ€Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ¸ Ð¸ Ð°Ð²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ð·Ð°Ñ†Ð¸Ð¸.",
    "sql": "ProjectOwner Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÑ‚ Ñ Ð±Ð°Ð·Ð°Ð¼Ð¸ Ð´Ð°Ð½Ð½Ñ‹Ñ… Ð² ÑÐ²Ð¾Ð¸Ñ… Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ….",
    "api": "ProjectOwner Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÑ‚ API: Telegram Bot API, Groq API Ð¸ Ð´Ñ€.",
    "telegram": "ProjectOwner ÑÐ¾Ð·Ð´Ð°Ñ‘Ñ‚ Telegram-Ð±Ð¾Ñ‚Ð¾Ð², Ð²ÐºÐ»ÑŽÑ‡Ð°Ñ Project Assistant.",
    "bot": "ProjectOwner ÑÐ¿ÐµÑ†Ð¸Ð°Ð»Ð¸Ð·Ð¸Ñ€ÑƒÐµÑ‚ÑÑ Ð½Ð° ÑÐ¾Ð·Ð´Ð°Ð½Ð¸Ð¸ Telegram-Ð±Ð¾Ñ‚Ð¾Ð².",
    "docker": "ProjectOwner Ð·Ð½Ð°ÐºÐ¾Ð¼ Ñ ÐºÐ¾Ð½Ñ‚ÐµÐ¹Ð½ÐµÑ€Ð¸Ð·Ð°Ñ†Ð¸ÐµÐ¹.",
    "git": "ProjectOwner Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÑ‚ Git Ð´Ð»Ñ Ð²ÑÐµÑ… Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð¾Ð².",
    "github": "GitHub ProjectOwner: github.com/example",
    "bash": "ProjectOwner Ð°ÐºÑ‚Ð¸Ð²Ð½Ð¾ Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÑ‚ Ñ bash Ð¸ Ñ‚ÐµÑ€Ð¼Ð¸Ð½Ð°Ð»Ð¾Ð¼.",
    "javascript": "ProjectOwner Ð·Ð½Ð°ÐºÐ¾Ð¼ Ñ JavaScript, Ð½Ð¾ Ð¾ÑÐ½Ð¾Ð²Ð½Ð¾Ð¹ ÑÐ·Ñ‹Ðº â€” Python.",
    "html": "ProjectOwner Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÑ‚ HTML Ð² Ð²ÐµÐ±-Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ….",
    "css": "ProjectOwner Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÑ‚ CSS Ð² Ð²ÐµÐ±-Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ….",
    "json": "ProjectOwner Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÑ‚ JSON Ð´Ð»Ñ Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ñ Ð´Ð°Ð½Ð½Ñ‹Ñ….",
    "jwt": "ProjectOwner Ð·Ð½Ð°ÐºÐ¾Ð¼ Ñ JWT Ñ‚Ð¾ÐºÐµÐ½Ð°Ð¼Ð¸.",
    "nginx": "ProjectOwner Ð·Ð½Ð°ÐºÐ¾Ð¼ Ñ Nginx.",
    "websocket": "ProjectOwner Ð·Ð½Ð°ÐºÐ¾Ð¼ Ñ WebSocket.",
    "webhook": "ProjectOwner Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÑ‚ Ð²ÐµÐ±Ñ…ÑƒÐºÐ¸ Ð² Telegram-Ð±Ð¾Ñ‚Ð°Ñ….",
    "regex": "ProjectOwner Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÑ‚ Ñ€ÐµÐ³ÑƒÐ»ÑÑ€Ð½Ñ‹Ðµ Ð²Ñ‹Ñ€Ð°Ð¶ÐµÐ½Ð¸Ñ Ð² Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ….",
    "cache": "ProjectOwner Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÑ‚ ÐºÑÑˆÐ¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ Ð² Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ….",
    "database": "ProjectOwner Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÑ‚ Ñ Ð±Ð°Ð·Ð°Ð¼Ð¸ Ð´Ð°Ð½Ð½Ñ‹Ñ… Ð² Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ….",
    "encryption": "ProjectOwner Ð·Ð½Ð°ÐºÐ¾Ð¼ Ñ ÑˆÐ¸Ñ„Ñ€Ð¾Ð²Ð°Ð½Ð¸ÐµÐ¼.",
    "vpn": "ProjectOwner Ð·Ð½Ð°ÐºÐ¾Ð¼ Ñ VPN.",
}


def find_tech_connection(text: str) -> str:
    """Find connection between tech question and owner's work."""
    lowered = text.casefold()
    for keyword, connection in TECH_CONNECTIONS.items():
        if keyword in lowered:
            return connection
    return ""


def clean_search_query(text: str) -> str:
    """Extract search query from visitor text."""
    cleaned = re.sub(
        r"(?i)(github|Ñ€ÐµÐ¿Ð¾Ð·Ð¸Ñ‚Ð¾Ñ€Ð¸|repo|ÐºÐ¾Ð´|code|Ð¿Ñ€Ð¾ÐµÐºÑ‚|Ð½Ð°Ð¹Ð´Ð¸|find|search|"
        r"Ð¿Ð¾ÑÐ¼Ð¾Ñ‚Ñ€Ð¸|Ð¿Ð¾ÐºÐ°Ð¶Ð¸|Ñ‡Ñ‚Ð¾|ÐºÐ°ÐºÐ¸Ðµ|Ñƒ|Ð²|Ð½Ð°|ÐµÑÑ‚ÑŒ|Ð»Ð¸|Ð¼Ð¾Ð¶ÐµÑˆÑŒ|Ð½ÐµÐ³Ð¾|ÐµÐ³Ð¾)\s*",
        " ", text,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned if len(cleaned) >= 2 else ""


def extract_portfolio_url(knowledge_text: str) -> str | None:
    """Extract portfolio URL from owner knowledge."""
    if not knowledge_text:
        return None

    for raw_line in knowledge_text.splitlines():
        line = raw_line.strip()
        lowered = line.casefold()
        if "portfolio:" not in lowered and "example.com" not in lowered:
            continue
        match = URL_RE.search(line)
        if match:
            return _normalize_url(match.group(0))
        if "example.com" in lowered:
            return "https://example.com/"

    match = URL_RE.search(knowledge_text)
    if match and "example.com" in match.group(0).casefold():
        return _normalize_url(match.group(0))

    if "example.com" in knowledge_text.casefold():
        return "https://example.com/"

    return None


def _normalize_url(url: str) -> str:
    """Normalize a public URL for crawling and display."""
    candidate = html.unescape(url.strip())
    candidate = candidate.rstrip(").,;]>\"'")
    if not candidate:
        return ""

    if not candidate.startswith(("http://", "https://")):
        candidate = f"https://{candidate.lstrip('/')}"

    parsed = urlparse(candidate)
    host = (parsed.netloc or parsed.path).strip().lower()
    path = parsed.path if parsed.netloc else ""
    if not host:
        return ""

    normalized = parsed._replace(
        scheme=parsed.scheme or "https",
        netloc=host,
        path=path or "/",
        params="",
        fragment="",
    )
    return normalized.geturl()


def _normalize_host(url: str) -> str:
    host = (urlparse(url).hostname or "").casefold()
    return host[4:] if host.startswith("www.") else host


def _same_domain(base_host: str, candidate_url: str) -> bool:
    candidate_host = _normalize_host(candidate_url)
    return bool(candidate_host) and (
        candidate_host == base_host or candidate_host.endswith(f".{base_host}")
    )


def _should_visit_portfolio_url(url: str, base_host: str) -> bool:
    if not url or not _same_domain(base_host, url):
        return False

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False

    lowered_path = parsed.path.casefold()
    if any(lowered_path.endswith(ext) for ext in SKIP_FILE_EXTENSIONS):
        return False

    if any(part in lowered_path for part in ("/cdn-cgi/", "/feed", "/tag/")):
        return False

    return True


def _clean_text(text: str) -> str:
    cleaned = html.unescape(text or "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _extract_page_title(page_html: str, url: str) -> str:
    if BeautifulSoup is not None:
        soup = BeautifulSoup(page_html, "html.parser")
        if soup.title and soup.title.get_text(" ", strip=True):
            return _clean_text(soup.title.get_text(" ", strip=True))

    match = TITLE_RE.search(page_html)
    if match:
        return _clean_text(match.group("title"))

    path = urlparse(url).path.strip("/")
    if not path:
        return "ProjectOwner Portfolio"
    return path.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ").title()


def _extract_page_text(page_html: str) -> str:
    if BeautifulSoup is not None:
        soup = BeautifulSoup(page_html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        for selector in ("header", "footer", "nav"):
            for node in soup.select(selector):
                node.decompose()
        text = soup.get_text(" ", strip=True)
        return _clean_text(text)

    text = TAG_RE.sub(" ", page_html)
    return _clean_text(text)


def _build_snippet(page_text: str, query_terms: list[str], max_chars: int = 260) -> str:
    text = _clean_text(page_text)
    if not text:
        return ""

    lowered = text.casefold()
    for term in query_terms:
        position = lowered.find(term)
        if position >= 0:
            start = max(position - 80, 0)
            end = min(start + max_chars, len(text))
            snippet = text[start:end].strip()
            if start > 0:
                snippet = f"...{snippet}"
            if end < len(text):
                snippet = snippet.rstrip(" ,.;") + "..."
            return snippet

    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip(" ,.;") + "..."


def _query_terms(query: str) -> list[str]:
    cleaned = clean_search_query(query)
    terms = re.findall(r"[0-9A-Za-zÐ-Ð¯Ð°-ÑÐÑ‘_-]{3,}", cleaned)
    stop_words = {
        "Ñ‡Ñ‚Ð¾",
        "ÑÑ‚Ð¾",
        "ÐºÐ°Ðº",
        "Ð³Ð´Ðµ",
        "Ð¿Ñ€Ð¾",
        "ÐµÐ³Ð¾",
        "Ð´Ð»Ñ",
        "Ð¸Ð»Ð¸",
        "the",
        "and",
        "about",
        "what",
        "tell",
        "project",
        "projects",
        "Ð¿Ñ€Ð¾ÐµÐºÑ‚",
        "Ð¿Ñ€Ð¾ÐµÐºÑ‚Ñ‹",
    }
    unique: list[str] = []
    for term in terms:
        lowered = term.casefold()
        if lowered in stop_words:
            continue
        if lowered not in unique:
            unique.append(lowered)
    return unique[:6]


def _portfolio_link_priority(url: str, anchor_text: str) -> float:
    haystack = f"{url} {anchor_text}".casefold()
    score = 0.0
    if any(hint in haystack for hint in PROJECT_LINK_HINTS):
        score += 6.0
    if "/projects" in haystack or "projects.html" in haystack:
        score += 8.0
    if anchor_text:
        score += 0.5
    return score


def _score_portfolio_page(page: PortfolioPage, query_terms: list[str]) -> float:
    haystack = f"{page.title} {page.snippet} {page.anchor_text} {page.url}".casefold()
    title = page.title.casefold()
    score = page.score

    if any(hint in haystack for hint in PROJECT_CONTENT_HINTS):
        score += 4.0

    for term in query_terms:
        if term in haystack:
            score += 5.0
        if term in title:
            score += 2.0

    if page.depth == 0:
        score += 1.0

    return score


def _extract_portfolio_links(page_url: str, page_html: str, base_host: str) -> list[tuple[str, str]]:
    discovered: list[tuple[float, str, str]] = []
    seen: set[str] = set()

    if BeautifulSoup is not None:
        soup = BeautifulSoup(page_html, "html.parser")
        anchors = soup.find_all("a", href=True)
        for anchor in anchors:
            href = (anchor.get("href") or "").strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            absolute = _normalize_url(urljoin(page_url, href))
            if not _should_visit_portfolio_url(absolute, base_host):
                continue
            if absolute in seen:
                continue
            seen.add(absolute)
            anchor_text = _clean_text(anchor.get_text(" ", strip=True))
            discovered.append(
                (_portfolio_link_priority(absolute, anchor_text), absolute, anchor_text)
            )
    else:
        for match in re.finditer(r"""href=["'](?P<href>[^"']+)["']""", page_html, re.IGNORECASE):
            href = match.group("href").strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            absolute = _normalize_url(urljoin(page_url, href))
            if not _should_visit_portfolio_url(absolute, base_host):
                continue
            if absolute in seen:
                continue
            seen.add(absolute)
            discovered.append((_portfolio_link_priority(absolute, ""), absolute, ""))

    discovered.sort(key=lambda item: (-item[0], item[1]))
    return [(url, anchor_text) for _, url, anchor_text in discovered[:12]]


async def _fetch_portfolio_html(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        response = await client.get(
            url,
            headers={"User-Agent": "TelegramAIAssistantVisitor/1.0"},
        )
        response.raise_for_status()
    except Exception as exc:
        LOGGER.debug("portfolio_fetch_error url=%s error=%s", url, exc)
        return None

    content_type = response.headers.get("content-type", "")
    if (
        content_type
        and "html" not in content_type.casefold()
        and "text/" not in content_type.casefold()
    ):
        return None

    return response.text[:400000]


async def _crawl_portfolio(base_url: str) -> list[PortfolioPage]:
    normalized_base = _normalize_url(base_url)
    if not normalized_base:
        return []

    base_host = _normalize_host(normalized_base)
    queue: list[tuple[str, str, int]] = [(normalized_base, "portfolio", 0)]
    queued_urls = {normalized_base}
    visited: set[str] = set()
    pages: list[PortfolioPage] = []

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        while queue and len(visited) < PORTFOLIO_MAX_PAGES:
            current_url, anchor_text, depth = queue.pop(0)
            queued_urls.discard(current_url)
            if current_url in visited:
                continue
            visited.add(current_url)

            page_html = await _fetch_portfolio_html(client, current_url)
            if not page_html:
                continue

            title = _extract_page_title(page_html, current_url)
            page_text = _extract_page_text(page_html)
            snippet = _build_snippet(page_text, [])
            pages.append(
                PortfolioPage(
                    url=current_url,
                    title=title,
                    snippet=snippet,
                    anchor_text=anchor_text,
                    depth=depth,
                    score=_portfolio_link_priority(current_url, anchor_text),
                )
            )

            if depth >= PORTFOLIO_MAX_DEPTH:
                continue

            for next_url, next_anchor in _extract_portfolio_links(
                current_url, page_html, base_host
            ):
                if next_url in visited or next_url in queued_urls:
                    continue
                queue.append((next_url, next_anchor, depth + 1))
                queued_urls.add(next_url)

    return pages


async def _get_cached_portfolio_pages(base_url: str) -> list[PortfolioPage]:
    normalized_base = _normalize_url(base_url)
    if not normalized_base:
        return []

    now = time.time()
    cached = _PORTFOLIO_CACHE.get(normalized_base)
    if cached and now - cached[0] < PORTFOLIO_CACHE_TTL_SECONDS:
        return list(cached[1])

    pages = await _crawl_portfolio(normalized_base)
    _PORTFOLIO_CACHE[normalized_base] = (now, list(pages))
    return pages


async def search_portfolio(
    config: AppConfig,
    knowledge_text: str,
    query: str = "",
    limit: int = 3,
) -> str | None:
    """Search the owner's portfolio pages and return compact context."""
    _ = config
    portfolio_url = extract_portfolio_url(knowledge_text)
    if not portfolio_url:
        return None

    pages = await _get_cached_portfolio_pages(portfolio_url)
    if not pages:
        return None

    query_terms = _query_terms(query)
    ranked = sorted(
        pages,
        key=lambda page: (-_score_portfolio_page(page, query_terms), page.depth, page.url),
    )

    lines: list[str] = []
    for page in ranked[:limit]:
        page_text = _clean_text(page.snippet)
        if not page_text:
            continue
        lines.append(f"<b>{page.title}</b>")
        lines.append(_build_snippet(page_text, query_terms))
        lines.append(page.url)
        lines.append("")

    result = "\n".join(lines).strip()
    return result or None


async def search_github(username: str, query: str = "", limit: int = 5) -> str | None:
    """Search GitHub repos. Returns formatted text or None."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if query:
                resp = await client.get(
                    f"{GITHUB_API}/search/repositories",
                    params={"q": f"{query} user:{username}", "per_page": limit, "sort": "updated"},
                )
            else:
                resp = await client.get(
                    f"{GITHUB_API}/users/{username}/repos",
                    params={"per_page": limit, "sort": "updated"},
                )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", data) if isinstance(data, dict) else data
            if not items:
                return None
            lines = []
            for repo in items[:limit]:
                name = repo.get("name", "?")
                desc = (repo.get("description") or "Ð±ÐµÐ· Ð¾Ð¿Ð¸ÑÐ°Ð½Ð¸Ñ").strip()
                url = repo.get("html_url", "")
                lang = repo.get("language") or ""
                stars = repo.get("stargazers_count", 0)
                parts = [f"â€¢ <b>{name}</b>"]
                if lang:
                    parts.append(f"[{lang}]")
                if stars:
                    parts.append(f"â˜…{stars}")
                parts.append(f"â€” {desc}")
                if url:
                    parts.append(f"\n  {url}")
                lines.append(" ".join(parts))
            return "\n\n".join(lines)
    except Exception as exc:
        LOGGER.warning("github_search_error query=%s error=%s", query, exc)
        return None


async def search_web(config: AppConfig, query: str, limit: int = 3) -> str | None:
    """Web search via DuckDuckGo. Returns formatted text or None."""
    try:
        from live.search_tool import SearchTool
        async with httpx.AsyncClient(timeout=15) as client:
            tool = SearchTool(client, config)
            results = await tool.search_web(query, limit=limit)
            if not results:
                return None
            lines = []
            for r in results:
                title = r.title or ""
                snippet = r.snippet or ""
                url = r.url or ""
                if title:
                    lines.append(f"<b>{title}</b>")
                if snippet:
                    lines.append(f"{snippet[:200]}")
                if url:
                    lines.append(url)
                lines.append("")
            return "\n".join(lines)
    except Exception as exc:
        LOGGER.debug("web_search_error query=%s error=%s", query, exc)
        return None


