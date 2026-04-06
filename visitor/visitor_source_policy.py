from __future__ import annotations

import html

from .visitor_cards import OwnerProfile, parse_knowledge

PROJECT_MARKERS = (
    "project",
    "projects",
    "portfolio",
    "case",
    "cases",
    "work",
    "works",
    "проект",
    "проекты",
    "портфолио",
    "кейс",
    "кейсы",
    "работы",
)
CODE_MARKERS = (
    "github",
    "repo",
    "repos",
    "repository",
    "repositories",
    "code",
    "open source",
    "репо",
    "репозитор",
    "код",
    "гитхаб",
)
CHANNEL_MARKERS = (
    "channel",
    "telegram channel",
    "tg channel",
    "post",
    "posts",
    "update",
    "updates",
    "latest",
    "news",
    "канал",
    "тгк",
    "пост",
    "посты",
    "апдейт",
    "апдейты",
    "обнов",
    "новост",
    "последн",
    "что нового",
)
CONTACT_MARKERS = (
    "contact",
    "contacts",
    "telegram",
    "email",
    "mail",
    "связ",
    "контакт",
    "телеграм",
    "почта",
    "написать",
)
SOURCE_REQUEST_MARKERS = (
    "where",
    "find",
    "look",
    "show",
    "read",
    "link",
    "links",
    "source",
    "где",
    "найти",
    "посмотреть",
    "покажи",
    "читать",
    "ссылка",
    "ссылки",
    "источник",
)
PORTFOLIO_HINT_MARKERS = (
    "site",
    "website",
    "portfolio",
    "портфолио",
    "сайт",
    "работы",
)


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = (text or "").casefold()
    return any(marker in lowered for marker in markers)


def query_mentions_projects(text: str) -> bool:
    return _has_any(text, PROJECT_MARKERS)


def query_mentions_code(text: str) -> bool:
    return _has_any(text, CODE_MARKERS)


def query_mentions_channel(text: str) -> bool:
    return _has_any(text, CHANNEL_MARKERS)


def query_mentions_contact(text: str) -> bool:
    return _has_any(text, CONTACT_MARKERS)


def query_mentions_source_request(text: str) -> bool:
    return _has_any(text, SOURCE_REQUEST_MARKERS)


def query_mentions_portfolio_hint(text: str) -> bool:
    return _has_any(text, PORTFOLIO_HINT_MARKERS)


def should_try_allowed_sources(text: str, category_value: str) -> bool:
    if category_value in {"about_projects", "project_specific_question", "links"}:
        return True

    if query_mentions_channel(text):
        return True

    if query_mentions_source_request(text) and (
        query_mentions_projects(text)
        or query_mentions_code(text)
        or query_mentions_channel(text)
        or query_mentions_contact(text)
        or query_mentions_portfolio_hint(text)
    ):
        return True

    return False


def extract_telegram_channel_lookup(raw_knowledge: str) -> str | None:
    profile = parse_knowledge(raw_knowledge)
    if profile.telegram_channel_url:
        return profile.telegram_channel_url
    if profile.telegram_channel_username:
        return f"@{profile.telegram_channel_username}"
    return None


def build_source_guidance(raw_knowledge: str, text: str) -> str | None:
    profile = parse_knowledge(raw_knowledge)
    lines = _select_source_lines(profile, text)
    if not lines:
        return None
    return "<b>Где это лучше смотреть:</b>\n\n" + "\n".join(lines)


def _select_source_lines(profile: OwnerProfile, text: str) -> list[str]:
    wants_projects = query_mentions_projects(text)
    wants_code = query_mentions_code(text)
    wants_channel = query_mentions_channel(text)
    wants_contact = query_mentions_contact(text)
    wants_source_request = query_mentions_source_request(text)
    wants_portfolio = wants_projects or query_mentions_portfolio_hint(text)

    lines: list[str] = []

    if wants_portfolio and profile.website_url:
        lines.append(_format_link_line("Проекты и кейсы", profile.website_url))

    if wants_code and profile.github_url:
        lines.append(_format_link_line("Открытый код и репозитории", profile.github_url))

    if wants_channel and profile.telegram_channel_url:
        lines.append(_format_link_line("Публичные апдейты и посты", profile.telegram_channel_url))

    if wants_contact and profile.telegram_url:
        lines.append(_format_link_line("Написать напрямую", profile.telegram_url))

    if wants_contact and profile.email:
        lines.append(f"• Email: {html.escape(profile.email)}")

    if not lines and wants_source_request:
        if profile.website_url:
            lines.append(_format_link_line("Портфолио", profile.website_url))
        if profile.github_url:
            lines.append(_format_link_line("GitHub", profile.github_url))
        if profile.telegram_channel_url:
            lines.append(_format_link_line("Telegram-канал", profile.telegram_channel_url))
        if profile.telegram_url:
            lines.append(_format_link_line("Telegram", profile.telegram_url))

    if not lines and wants_projects:
        if profile.website_url:
            lines.append(_format_link_line("Портфолио с проектами", profile.website_url))
        if profile.github_url:
            lines.append(_format_link_line("GitHub с открытым кодом", profile.github_url))
        if profile.telegram_channel_url:
            lines.append(_format_link_line("Telegram-канал с апдейтами", profile.telegram_channel_url))

    return lines


def _format_link_line(label: str, url: str) -> str:
    safe_label = html.escape(label)
    safe_url = html.escape(url, quote=True)
    display = html.escape(url.replace("https://", "").replace("http://", "").rstrip("/"))
    return f"• {safe_label}: <a href='{safe_url}'>{display}</a>"
