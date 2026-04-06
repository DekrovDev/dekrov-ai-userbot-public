from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from .visitor_models import TopicCategory
from .visitor_policy import evaluate_message, classify_topic


class Route(str, Enum):
    """Deterministic route for visitor queries.
    Each route has a fixed source hierarchy."""
    # Static response â€” no AI needed
    STATIC_LINKS = "static_links"
    STATIC_OWNER = "static_owner"
    STATIC_PROJECTS = "static_projects"
    STATIC_CAPABILITIES = "static_capabilities"
    STATIC_FAQ = "static_faq"
    STATIC_COLLABORATION = "static_collaboration"
    # Search-enhanced
    SEARCH_GITHUB = "search_github"
    SEARCH_WEB = "search_web"
    # AI with knowledge
    AI_WITH_KNOWLEDGE = "ai_with_knowledge"
    AI_TECHNICAL = "ai_technical"
    AI_PROJECT_SPECIFIC = "ai_project_specific"
    # Rejected
    REJECT_REDIRECT = "reject_redirect"
    REJECT_INTERNAL = "reject_internal"
    REJECT_ADMIN = "reject_admin"


@dataclass(frozen=True)
class RouteDecision:
    route: Route
    category: TopicCategory
    needs_search: bool = False
    needs_knowledge: bool = False
    needs_ai: bool = False
    prefix: str = ""
    redirect_message: str | None = None


def _normalize_preconsultation_text(text: str) -> str:
    return " ".join((text or "").strip().casefold().replace("Ñ‘", "Ðµ").split())


def _looks_like_preconsultation_request(text: str) -> bool:
    normalized = _normalize_preconsultation_text(text)
    markers = (
        "Ð½Ðµ Ð·Ð½Ð°ÑŽ Ñ‡Ñ‚Ð¾ Ð½Ð°Ð´Ð¾",
        "Ð½Ðµ Ð·Ð½Ð°ÑŽ, Ñ‡Ñ‚Ð¾ Ð½Ð°Ð´Ð¾",
        "Ð½Ðµ Ð·Ð½Ð°ÑŽ Ñ‡Ñ‚Ð¾ Ð½ÑƒÐ¶Ð½Ð¾",
        "Ð½Ðµ Ð·Ð½Ð°ÑŽ, Ñ‡Ñ‚Ð¾ Ð½ÑƒÐ¶Ð½Ð¾",
        "Ñ‡Ñ‚Ð¾ Ð½Ð°Ð´Ð¾ Ð´Ð»Ñ Ð±Ð¾Ñ‚Ð°",
        "Ñ‡Ñ‚Ð¾ Ð½ÑƒÐ¶Ð½Ð¾ Ð´Ð»Ñ Ð±Ð¾Ñ‚Ð°",
        "ÐºÐ°Ðº Ð¿Ð¾Ð¿Ñ€Ð¾ÑÐ¸Ñ‚ÑŒ",
        "ÐºÐ°Ðº Ð½Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ",
        "ÐºÐ°Ðº ÑÑ„Ð¾Ñ€Ð¼ÑƒÐ»Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ",
        "Ñ‡Ñ‚Ð¾ Ð½Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ Ð´ÐµÐºÑ€Ð¾Ð²Ñƒ",
        "Ñ‡Ñ‚Ð¾ ÑÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð´ÐµÐºÑ€Ð¾Ð²Ñƒ",
        "Ð¿Ð¾Ð¼Ð¾Ð³Ð¸ Ð½Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ",
        "Ð¿Ð¾Ð¼Ð¾Ð³Ð¸ ÑÑ„Ð¾Ñ€Ð¼ÑƒÐ»Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ",
        "Ð¿Ð¾Ð¼Ð¾Ð³Ð¸ Ð¿Ð¾Ð¿Ñ€Ð¾ÑÐ¸Ñ‚ÑŒ",
        "ÑÑ‚Ñ‹Ð´Ð½Ð¾ Ð¿Ñ€Ð¾ÑÐ¸Ñ‚ÑŒ",
        "Ð½ÐµÐ»Ð¾Ð²ÐºÐ¾ Ð¿Ñ€Ð¾ÑÐ¸Ñ‚ÑŒ",
        "Ñ…Ð¾Ñ‡Ñƒ Ð·Ð°ÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð±Ð¾Ñ‚Ð°",
        "Ð·Ð°ÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð±Ð¾Ñ‚Ð°",
        "Ð±Ð¾Ñ‚Ð° Ð½Ð° Ð·Ð°ÐºÐ°Ð·",
        "Ð¼Ð½Ðµ Ð½ÑƒÐ¶ÐµÐ½ Ð±Ð¾Ñ‚",
        "ÑÐ´ÐµÐ»Ð°Ð» Ð¼Ð½Ðµ Ð±Ð¾Ñ‚Ð°",
        "what should i write",
        "how should i ask",
        "help me ask",
        "help me write",
        "i don't know what is needed",
        "i do not know what is needed",
    )
    return any(marker in normalized for marker in markers)


# Category â†’ Route mapping (DETERMINISTIC)
_CATEGORY_ROUTES: dict[TopicCategory, RouteDecision] = {
    TopicCategory.GREETING: RouteDecision(
        route=Route.AI_WITH_KNOWLEDGE,
        category=TopicCategory.GREETING,
        needs_knowledge=True,
        needs_ai=True,
        prefix="ÐŸÐ¾ÑÐµÑ‚Ð¸Ñ‚ÐµÐ»ÑŒ Ð¿Ð¾Ð·Ð´Ð¾Ñ€Ð¾Ð²Ð°Ð»ÑÑ. ÐŸÐ¾Ð¿Ñ€Ð¸Ð²ÐµÐ¹ÑÑ ÐºÑ€Ð°Ñ‚ÐºÐ¾ (1-2 Ð¿Ñ€ÐµÐ´Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ), Ð¿Ñ€ÐµÐ´ÑÑ‚Ð°Ð²ÑŒÑÑ ÐºÐ°Ðº AI-ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ð½Ñ‚ ProjectOwner, Ð¿Ñ€ÐµÐ´Ð»Ð¾Ð¶Ð¸ Ð·Ð°Ð´Ð°Ñ‚ÑŒ Ð²Ð¾Ð¿Ñ€Ð¾Ñ Ð¾ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ… Ð¸Ð»Ð¸ ÑÐ¾Ñ‚Ñ€ÑƒÐ´Ð½Ð¸Ñ‡ÐµÑÑ‚Ð²Ðµ.",
    ),
    TopicCategory.GENERAL: RouteDecision(
        route=Route.AI_WITH_KNOWLEDGE,
        category=TopicCategory.GENERAL,
        needs_knowledge=True,
        needs_ai=True,
        prefix="ÐžÐ±Ñ‰Ð¸Ð¹ Ð²Ð¾Ð¿Ñ€Ð¾Ñ Ð¾Ñ‚ Ð¿Ð¾ÑÐµÑ‚Ð¸Ñ‚ÐµÐ»Ñ. ÐžÑ‚Ð²ÐµÑ‚ÑŒ ÐºÑ€Ð°Ñ‚ÐºÐ¾ (2-4 Ð¿Ñ€ÐµÐ´Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ). Ð•ÑÐ»Ð¸ Ð²Ð¾Ð¿Ñ€Ð¾Ñ ÑÐ²ÑÐ·Ð°Ð½ Ñ ProjectOwner, ÐµÐ³Ð¾ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ð¼Ð¸ Ð¸Ð»Ð¸ Ñ‚ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸ÑÐ¼Ð¸ â€” Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐ¹ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð¸Ð· Ð±Ð°Ð·Ñ‹ Ð·Ð½Ð°Ð½Ð¸Ð¹. Ð•ÑÐ»Ð¸ Ð²Ð¾Ð¿Ñ€Ð¾Ñ Ð½Ðµ Ð¿Ð¾ Ñ‚ÐµÐ¼Ðµ â€” Ð²ÐµÐ¶Ð»Ð¸Ð²Ð¾ Ð¿ÐµÑ€ÐµÐ½Ð°Ð¿Ñ€Ð°Ð²ÑŒ Ð½Ð° Ñ‚ÐµÐ¼Ñ‹ Ð¾ ProjectOwner.",
    ),
    TopicCategory.ABOUT_OWNER: RouteDecision(
        route=Route.AI_WITH_KNOWLEDGE,
        category=TopicCategory.ABOUT_OWNER,
        needs_knowledge=True,
        needs_ai=True,
        prefix="Ð’Ð¾Ð¿Ñ€Ð¾Ñ Ð¾ Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ðµ ProjectOwner. ÐžÑ‚Ð²ÐµÑ‚ÑŒ Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÑ Ð¢ÐžÐ›Ð¬ÐšÐž Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð¸Ð· Ð±Ð°Ð·Ñ‹ Ð·Ð½Ð°Ð½Ð¸Ð¹.",
    ),
    TopicCategory.ABOUT_PROJECTS: RouteDecision(
        route=Route.SEARCH_GITHUB,
        category=TopicCategory.ABOUT_PROJECTS,
        needs_search=True,
        needs_knowledge=True,
        needs_ai=True,
        prefix="Ð’Ð¾Ð¿Ñ€Ð¾Ñ Ð¾ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ… ProjectOwner. Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐ¹ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð¸Ð· Ð±Ð°Ð·Ñ‹ Ð·Ð½Ð°Ð½Ð¸Ð¹ Ð¸ GitHub.",
    ),
    TopicCategory.TECHNICAL_QUESTION: RouteDecision(
        route=Route.AI_TECHNICAL,
        category=TopicCategory.TECHNICAL_QUESTION,
        needs_ai=True,
        prefix="Ð¢ÐµÑ…Ð½Ð¸Ñ‡ÐµÑÐºÐ¸Ð¹ Ð²Ð¾Ð¿Ñ€Ð¾Ñ. ÐžÐ±ÑŠÑÑÐ½Ð¸ ÐºÑ€Ð°Ñ‚ÐºÐ¾ (2-4 Ð¿Ñ€ÐµÐ´Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ).",
    ),
    TopicCategory.PROJECT_SPECIFIC_QUESTION: RouteDecision(
        route=Route.AI_PROJECT_SPECIFIC,
        category=TopicCategory.PROJECT_SPECIFIC_QUESTION,
        needs_search=True,
        needs_knowledge=True,
        needs_ai=True,
        prefix=(
            "Ð’Ð¾Ð¿Ñ€Ð¾Ñ Ð¾ ÐºÐ¾Ð½ÐºÑ€ÐµÑ‚Ð½Ð¾Ð¼ Ð°ÑÐ¿ÐµÐºÑ‚Ðµ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð° ProjectOwner. "
            "Ð˜Ñ‰Ð¸ Ð¾Ñ‚Ð²ÐµÑ‚ Ð¢ÐžÐ›Ð¬ÐšÐž Ð² Ð¿Ñ€ÐµÐ´Ð¾ÑÑ‚Ð°Ð²Ð»ÐµÐ½Ð½Ñ‹Ñ… Ð´Ð°Ð½Ð½Ñ‹Ñ…. "
            "Ð•ÑÐ»Ð¸ Ð´Ð°Ð½Ð½Ñ‹Ñ… Ð½ÐµÑ‚ â€” ÑÐºÐ°Ð¶Ð¸: 'Ð£ Ð¼ÐµÐ½Ñ Ð½ÐµÑ‚ Ñ‚Ð¾Ñ‡Ð½Ð¾Ð¹ Ð¸Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸Ð¸ Ð¾Ð± ÑÑ‚Ð¾Ð¼'. "
            "ÐÐµ Ð²Ñ‹Ð´ÑƒÐ¼Ñ‹Ð²Ð°Ð¹."
        ),
    ),
    TopicCategory.FAQ: RouteDecision(
        route=Route.AI_WITH_KNOWLEDGE,
        category=TopicCategory.FAQ,
        needs_knowledge=True,
        needs_ai=True,
        prefix="Ð§Ð°ÑÑ‚Ñ‹Ð¹ Ð²Ð¾Ð¿Ñ€Ð¾Ñ. ÐžÑ‚Ð²ÐµÑ‚ÑŒ Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÑ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð¸Ð· Ð±Ð°Ð·Ñ‹ Ð·Ð½Ð°Ð½Ð¸Ð¹.",
    ),
    TopicCategory.COLLABORATION: RouteDecision(
        route=Route.AI_WITH_KNOWLEDGE,
        category=TopicCategory.COLLABORATION,
        needs_knowledge=True,
        needs_ai=True,
        prefix="Ð’Ð¾Ð¿Ñ€Ð¾Ñ Ð¾ ÑÐ¾Ñ‚Ñ€ÑƒÐ´Ð½Ð¸Ñ‡ÐµÑÑ‚Ð²Ðµ. Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐ¹ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð¸Ð· Ð±Ð°Ð·Ñ‹ Ð·Ð½Ð°Ð½Ð¸Ð¹.",
    ),
    TopicCategory.LINKS: RouteDecision(
        route=Route.SEARCH_GITHUB,
        category=TopicCategory.LINKS,
        needs_search=True,
        needs_knowledge=False,
        needs_ai=False,
    ),
    TopicCategory.ASSISTANT_CAPABILITIES: RouteDecision(
        route=Route.AI_WITH_KNOWLEDGE,
        category=TopicCategory.ASSISTANT_CAPABILITIES,
        needs_knowledge=False,
        needs_ai=True,
        prefix="Ð’Ð¾Ð¿Ñ€Ð¾Ñ Ð¾ Ð²Ð¾Ð·Ð¼Ð¾Ð¶Ð½Ð¾ÑÑ‚ÑÑ… Ð¿Ð¾Ð¼Ð¾Ñ‰Ð½Ð¸ÐºÐ°.",
    ),
}


def route_query(text: str) -> RouteDecision:
    """Deterministic routing: text â†’ category â†’ route.
    No magic, no guessing."""
    category = classify_topic(text)

    # Disallowed â€” reject immediately
    if category == TopicCategory.DISALLOWED_OFFTOPIC:
        return RouteDecision(
            route=Route.REJECT_REDIRECT,
            category=category,
            redirect_message=(
                "Ð¯ ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸Ð¾Ð½Ð½Ñ‹Ð¹ Ð¿Ð¾Ð¼Ð¾Ñ‰Ð½Ð¸Ðº Ð¸ Ð¼Ð¾Ð³Ñƒ Ñ€Ð°ÑÑÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð¾ ProjectOwner, "
                "ÐµÐ³Ð¾ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ…, Ñ‚ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸ÑÑ…, ÑÑÑ‹Ð»ÐºÐ°Ñ… Ð¸ ÑÐ¾Ñ‚Ñ€ÑƒÐ´Ð½Ð¸Ñ‡ÐµÑÑ‚Ð²Ðµ.\n"
                "ÐœÐ¾Ð³Ñƒ Ñ‚Ð°ÐºÐ¶Ðµ Ð¾Ð±ÑŠÑÑÐ½Ð¸Ñ‚ÑŒ Ñ‚ÐµÑ…Ð½Ð¸Ñ‡ÐµÑÐºÐ¸Ðµ Ð¿Ð¾Ð½ÑÑ‚Ð¸Ñ. "
                "Ð—Ð°Ð´Ð°Ð¹Ñ‚Ðµ Ð²Ð¾Ð¿Ñ€Ð¾Ñ Ð¿Ð¾ Ð¾Ð´Ð½Ð¾Ð¹ Ð¸Ð· ÑÑ‚Ð¸Ñ… Ñ‚ÐµÐ¼."
            ),
        )

    if category == TopicCategory.DISALLOWED_INTERNAL:
        return RouteDecision(
            route=Route.REJECT_INTERNAL,
            category=category,
            redirect_message=(
                "Ð¯ Ð½Ðµ Ð¼Ð¾Ð³Ñƒ Ñ€Ð°ÑÐºÑ€Ñ‹Ð²Ð°Ñ‚ÑŒ Ð²Ð½ÑƒÑ‚Ñ€ÐµÐ½Ð½Ð¸Ðµ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸. "
                "Ð¡Ð¿Ñ€Ð¾ÑÐ¸Ñ‚Ðµ Ð¾ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ…, Ñ‚ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸ÑÑ… Ð¸Ð»Ð¸ ÑÐ¾Ñ‚Ñ€ÑƒÐ´Ð½Ð¸Ñ‡ÐµÑÑ‚Ð²Ðµ."
            ),
        )

    if category == TopicCategory.DISALLOWED_ADMIN:
        return RouteDecision(
            route=Route.REJECT_ADMIN,
            category=category,
            redirect_message=(
                "Ð£ Ð¼ÐµÐ½Ñ Ð½ÐµÑ‚ Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð° Ðº Ð°Ð´Ð¼Ð¸Ð½-Ñ„ÑƒÐ½ÐºÑ†Ð¸ÑÐ¼. "
                "Ð¯ Ð¿ÑƒÐ±Ð»Ð¸Ñ‡Ð½Ñ‹Ð¹ ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ð½Ñ‚."
            ),
        )

    if category == TopicCategory.DISALLOWED_PRIVATE:
        return RouteDecision(
            route=Route.REJECT_REDIRECT,
            category=category,
            redirect_message="Ð­Ñ‚Ð° Ð¸Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸Ñ Ð¿Ñ€Ð¸Ð²Ð°Ñ‚Ð½Ð°.",
        )

    # Allowed category â†’ get route
    if _looks_like_preconsultation_request(text):
        return RouteDecision(
            route=Route.AI_WITH_KNOWLEDGE,
            category=TopicCategory.COLLABORATION,
            needs_knowledge=True,
            needs_ai=True,
            prefix=(
                "The visitor needs pre-consultation help before contacting ProjectOwner. "
                "Be warm and practical. "
                "Help them understand what to say, what information is useful, and offer either a short checklist or a ready-to-send draft message. "
                "Do not jump straight to links or a stack list."
            ),
        )

    decision = _CATEGORY_ROUTES.get(category)
    if decision is not None:
        if decision.category == TopicCategory.GENERAL:
            return replace(
                decision,
                prefix=(
                    "General visitor question. Reply warmly and naturally. "
                    "First help with the user's immediate need instead of rushing to contacts or links. "
                    "If the visitor is unsure what to ask ProjectOwner, help them clarify the request, suggest a short checklist, or offer a ready-to-send draft message. "
                    "Do not sound rigid or repetitive. "
                    "Do not invent facts about ProjectOwner."
                ),
            )
        if decision.category == TopicCategory.COLLABORATION:
            return replace(
                decision,
                prefix=(
                    "Collaboration or service request. Be calm, helpful, and welcoming. "
                    "Before sending the visitor to ProjectOwner, help them understand what information would be useful: goal, platform, key features, examples, timeline, and budget. "
                    "If it helps, provide a short checklist or a draft message they can send. "
                    "Mention contact options gently, only as the next step."
                ),
            )
        return decision

    # Fallback
    return RouteDecision(
        route=Route.REJECT_REDIRECT,
        category=TopicCategory.DISALLOWED_OFFTOPIC,
        redirect_message="Ð’Ð¾Ð¿Ñ€Ð¾Ñ Ð²Ð½Ðµ Ñ‚ÐµÐ¼Ñ‹ ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸Ð¸.",
    )

