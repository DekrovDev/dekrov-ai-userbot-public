from __future__ import annotations

"""
visitor_cards.py â€” Structured card builders for visitor button callbacks.

No AI involved. Parses owner knowledge and builds formatted HTML cards.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

LOGGER = logging.getLogger("assistant.visitor.cards")


@dataclass
class OwnerProfile:
    """Parsed owner profile data."""
    nickname: str = "ProjectOwner"
    real_name_ru: str = ""
    real_name_en: str = ""
    occupation: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    github_url: str = ""
    github_username: str = ""
    website_url: str = ""
    telegram_url: str = ""
    telegram_username: str = ""
    telegram_channel_url: str = ""
    telegram_channel_username: str = ""
    email: str = ""
    location: str = ""
    bio: list[str] = field(default_factory=list)


def parse_knowledge(raw_knowledge: str) -> OwnerProfile:
    """Parse knowledge markdown into structured profile.
    
    Format expected:
    # Identity
    - Preferred nickname: ProjectOwner
    - Real name (RU/UA): ÐŸÐ°ÑˆÐ°
    
    # Websites
    - Portfolio: https://example.com
    
    # Telegram
    - Main Telegram channel: https://t.me/example_channel
    
    # Contacts
    - Telegram: https://t.me/example_owner
    - Mail: contact@example.com
    
    # Interests
    - Interested in cybersecurity.
    
    # Technical environment
    - Uses Linux systems.
    
    # Security related activity
    - Studies web vulnerabilities...
    
    # Development
    - Builds Telegram bots...
    """
    profile = OwnerProfile()
    
    if not raw_knowledge:
        return profile
    
    lines = raw_knowledge.splitlines()
    current_section = ""
    
    for line in lines:
        line_stripped = line.strip()
        
        # Skip empty lines, comments, and architecture section
        if not line_stripped:
            continue
        if line_stripped.startswith("#"):
            # Extract section name
            current_section = line_stripped.lstrip("#").strip().lower()
            # Stop at architecture section
            if "about assistant-ai" in current_section or "architecture" in current_section:
                break
            continue
        if line_stripped.startswith("##"):
            continue
        
        # Parse bullet points
        if line_stripped.startswith("- "):
            content = line_stripped[2:].strip()
            
            # Skip notes and meta-info
            if content.startswith("This is ") or content.startswith("Put "):
                continue
            
            # Identity section
            if current_section == "identity":
                if "preferred nickname:" in content.lower():
                    profile.nickname = _extract_value(content)
                elif "main online alias:" in content.lower():
                    value = _extract_value(content)
                    if len(value) < 30:  # Skip long descriptive lines
                        profile.nickname = value
                elif "real name (ru" in content.lower():
                    profile.real_name_ru = _extract_value(content)
                elif "real name (en" in content.lower():
                    profile.real_name_en = _extract_value(content)
            
            # Websites section
            elif current_section == "websites":
                if "portfolio:" in content.lower():
                    value = _extract_value(content)
                    if "http" in value:
                        profile.website_url = value
                    elif "example.com" in value.lower():
                        profile.website_url = "https://example.com"
                elif "github:" in content.lower():
                    value = _extract_value(content)
                    if "github/" in value and "github.com/" not in value:
                        value = value.replace("https://github/", "https://github.com/")
                        value = value.replace("http://github/", "https://github.com/")
                        if value.startswith("github/"):
                            value = value.replace("github/", "https://github.com/", 1)
                    profile.github_url = value
                    # Extract username from URL - handle both github.com/ and github/
                    if "github.com/" in value:
                        match = re.search(r'github\.com/([a-zA-Z0-9_-]+)', value)
                        if match:
                            profile.github_username = match.group(1)
                    elif "github/" in value:
                        match = re.search(r'github/([a-zA-Z0-9_-]+)', value)
                        if match:
                            profile.github_username = match.group(1)
            
            # Telegram section
            elif current_section == "telegram":
                if "channel:" in content.lower():
                    value = _extract_value(content)
                    profile.telegram_channel_url = value
                    if "t.me/" in value:
                        match = re.search(r't\.me/([a-zA-Z0-9_]+)', value)
                        if match:
                            profile.telegram_channel_username = match.group(1)
            
            # Contacts section
            elif current_section == "contacts":
                if "telegram:" in content.lower() and "official" not in content.lower():
                    value = _extract_value(content)
                    profile.telegram_url = value
                    if "t.me/" in value:
                        match = re.search(r't\.me/([a-zA-Z0-9_]+)', value)
                        if match:
                            profile.telegram_username = match.group(1)
                elif "telegram-official:" in content.lower() or "telegram (official)" in content.lower():
                    value = _extract_value(content)
                    if not profile.telegram_url:
                        profile.telegram_url = value
                        if "t.me/" in value:
                            match = re.search(r't\.me/([a-zA-Z0-9_]+)', value)
                            if match:
                                profile.telegram_username = match.group(1)
                elif "mail:" in content.lower() or "email:" in content.lower():
                    value = _extract_value(content)
                    if "@" in value:
                        profile.email = value
            
            # Interests section
            elif current_section == "interests":
                # Remove "Interested in" prefix and translate
                text = re.sub(r'^interested in\s+', '', content, flags=re.IGNORECASE)
                text = text.rstrip(".")
                if text:
                    # Translate common phrases
                    translations = {
                        "cybersecurity": "ÐšÐ¸Ð±ÐµÑ€Ð±ÐµÐ·Ð¾Ð¿Ð°ÑÐ½Ð¾ÑÑ‚ÑŒ",
                        "web security and penetration testing": "Ð’ÐµÐ±-Ð±ÐµÐ·Ð¾Ð¿Ð°ÑÐ½Ð¾ÑÑ‚ÑŒ Ð¸ Ð¿ÐµÐ½Ñ‚ÐµÑÑ‚Ð¸Ð½Ð³",
                        "web security": "Ð’ÐµÐ±-Ð±ÐµÐ·Ð¾Ð¿Ð°ÑÐ½Ð¾ÑÑ‚ÑŒ",
                        "internet infrastructure and how the web works": "Ð˜Ð½Ñ„Ñ€Ð°ÑÑ‚Ñ€ÑƒÐºÑ‚ÑƒÑ€Ð° Ð¸Ð½Ñ‚ÐµÑ€Ð½ÐµÑ‚Ð° Ð¸ ÑƒÑÑ‚Ñ€Ð¾Ð¹ÑÑ‚Ð²Ð¾ Ð²ÐµÐ±Ð°",
                        "programming and automation": "ÐŸÑ€Ð¾Ð³Ñ€Ð°Ð¼Ð¼Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ Ð¸ Ð°Ð²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ð·Ð°Ñ†Ð¸Ñ",
                    }
                    lower_text = text.lower().strip()
                    translated = translations.get(lower_text)
                    if translated:
                        profile.interests.append(translated)
                    else:
                        profile.interests.append(text.capitalize())
            
            # Technical environment section
            elif current_section == "technical environment":
                # Remove prefixes like "Uses", "Works with" and translate
                text = re.sub(r'^(uses|works with)\s+', '', content, flags=re.IGNORECASE)
                text = text.rstrip(".")
                if text:
                    # Translate common phrases
                    translations = {
                        "linux systems": "Linux ÑÐ¸ÑÑ‚ÐµÐ¼Ñ‹",
                        "kali linux for security testing": "Kali Linux Ð´Ð»Ñ Ñ‚ÐµÑÑ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ Ð±ÐµÐ·Ð¾Ð¿Ð°ÑÐ½Ð¾ÑÑ‚Ð¸",
                        "windows for everyday work": "Windows Ð´Ð»Ñ Ð¿Ð¾Ð²ÑÐµÐ´Ð½ÐµÐ²Ð½Ð¾Ð¹ Ñ€Ð°Ð±Ð¾Ñ‚Ñ‹",
                        "terminal tools and command line utilities": "Ð¢ÐµÑ€Ð¼Ð¸Ð½Ð°Ð»ÑŒÐ½Ñ‹Ðµ Ð¸Ð½ÑÑ‚Ñ€ÑƒÐ¼ÐµÐ½Ñ‚Ñ‹ Ð¸ ÑƒÑ‚Ð¸Ð»Ð¸Ñ‚Ñ‹ ÐºÐ¾Ð¼Ð°Ð½Ð´Ð½Ð¾Ð¹ ÑÑ‚Ñ€Ð¾ÐºÐ¸",
                        "linux": "Linux",
                        "kali linux": "Kali Linux",
                        "windows": "Windows",
                    }
                    lower_text = text.lower().strip()
                    translated = translations.get(lower_text)
                    if translated:
                        profile.skills.append(translated)
                    else:
                        profile.skills.append(text.capitalize())
            
            # Security related activity section
            elif current_section == "security related activity":
                # Remove prefixes and translate
                text = re.sub(r'^(studies|uses|works with)\s+', '', content, flags=re.IGNORECASE)
                text = text.rstrip(".")
                if text:
                    # Translate common phrases
                    translations = {
                        "web vulnerabilities such as sql injection, xss, and other common web security issues": "Ð’ÐµÐ±-ÑƒÑÐ·Ð²Ð¸Ð¼Ð¾ÑÑ‚Ð¸: SQL-Ð¸Ð½ÑŠÐµÐºÑ†Ð¸Ð¸, XSS Ð¸ Ð´Ñ€ÑƒÐ³Ð¸Ðµ Ñ€Ð°ÑÐ¿Ñ€Ð¾ÑÑ‚Ñ€Ð°Ð½Ñ‘Ð½Ð½Ñ‹Ðµ ÑƒÐ³Ñ€Ð¾Ð·Ñ‹",
                        "web vulnerabilities": "Ð’ÐµÐ±-ÑƒÑÐ·Ð²Ð¸Ð¼Ð¾ÑÑ‚Ð¸",
                        "security scanners and open-source tools for testing websites": "Ð¡ÐºÐ°Ð½ÐµÑ€Ñ‹ Ð±ÐµÐ·Ð¾Ð¿Ð°ÑÐ½Ð¾ÑÑ‚Ð¸ Ð¸ open-source Ð¸Ð½ÑÑ‚Ñ€ÑƒÐ¼ÐµÐ½Ñ‚Ñ‹ Ð´Ð»Ñ Ñ‚ÐµÑÑ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ ÑÐ°Ð¹Ñ‚Ð¾Ð²",
                        "how web applications work and how they can be analyzed": "ÐŸÑ€Ð¸Ð½Ñ†Ð¸Ð¿Ñ‹ Ñ€Ð°Ð±Ð¾Ñ‚Ñ‹ Ð¸ Ð°Ð½Ð°Ð»Ð¸Ð·Ð° Ð²ÐµÐ±-Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ð¹",
                    }
                    lower_text = text.lower().strip()
                    translated = translations.get(lower_text)
                    if translated:
                        profile.skills.append(translated)
                    else:
                        profile.skills.append(text.capitalize())
            
            # Development section
            elif current_section == "development":
                # Remove prefixes and translate to Russian
                text = re.sub(r'^(builds|works with|uses|develops|creates)\s+', '', content, flags=re.IGNORECASE)
                text = text.rstrip(".")
                if text:
                    # Translate common phrases
                    translations = {
                        "telegram bots and automation tools": "Ð Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Telegram-Ð±Ð¾Ñ‚Ð¾Ð² Ð¸ Ð¸Ð½ÑÑ‚Ñ€ÑƒÐ¼ÐµÐ½Ñ‚Ð¾Ð² Ð°Ð²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ð·Ð°Ñ†Ð¸Ð¸",
                        "telegram bots": "Ð Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Telegram-Ð±Ð¾Ñ‚Ð¾Ð²",
                        "open source projects from github": "Open-source Ð¿Ñ€Ð¾ÐµÐºÑ‚Ñ‹ Ð½Ð° GitHub",
                        "scripts and tools to analyze websites": "Ð¡ÐºÑ€Ð¸Ð¿Ñ‚Ñ‹ Ð¸ Ð¸Ð½ÑÑ‚Ñ€ÑƒÐ¼ÐµÐ½Ñ‚Ñ‹ Ð´Ð»Ñ Ð°Ð½Ð°Ð»Ð¸Ð·Ð° Ð²ÐµÐ±-ÑÐ°Ð¹Ñ‚Ð¾Ð²",
                        "python": "Python",
                    }
                    lower_text = text.lower().strip()
                    translated = translations.get(lower_text)
                    if translated:
                        profile.occupation.append(translated)
                    else:
                        profile.occupation.append(text.capitalize())
            
            # Internet activity section
            elif current_section == "internet activity":
                if "runs" in content.lower() and "website" in content.lower():
                    # Extract domain
                    match = re.search(r'domain\s+(\S+)', content, re.IGNORECASE)
                    if match:
                        domain = match.group(1).rstrip(".")
                        if not profile.website_url:
                            profile.website_url = f"https://{domain}"
                elif "uses the nickname" in content.lower():
                    # Skip - we already have nickname from Identity
                    pass
            
            # Personal traits section
            elif current_section == "personal traits":
                text = content.rstrip(".")
                if text:
                    profile.bio.append(text)
    
    # Post-processing: fill gaps
    if not profile.github_username and profile.github_url:
        if "github.com/" in profile.github_url:
            match = re.search(r'github\.com/([a-zA-Z0-9_-]+)', profile.github_url)
            if match:
                profile.github_username = match.group(1)
    
    if not profile.telegram_username and profile.telegram_url:
        if "t.me/" in profile.telegram_url:
            match = re.search(r't\.me/([a-zA-Z0-9_]+)', profile.telegram_url)
            if match:
                profile.telegram_username = match.group(1)
    
    return profile


def _extract_value(line: str) -> str:
    """Extract value after colon from a line."""
    if ":" in line:
        return line.split(":", 1)[1].strip()
    return line.strip()


# ========================
# CARD BUILDERS
# ========================

def build_owner_card(profile: OwnerProfile) -> str:
    """Build 'About Owner' card HTML."""
    lines = []
    
    # Header
    lines.append(f"<b>ðŸ‘¤ {profile.nickname}</b>")
    
    if profile.real_name_ru or profile.real_name_en:
        names = []
        if profile.real_name_ru:
            names.append(profile.real_name_ru)
        if profile.real_name_en:
            names.append(profile.real_name_en)
        lines.append(f"<i>{' / '.join(names)}</i>")
    
    lines.append("")
    
    # Occupation
    if profile.occupation:
        lines.append("<b>Ð—Ð°Ð½Ð¸Ð¼Ð°ÐµÑ‚ÑÑ:</b>")
        for item in profile.occupation[:4]:
            lines.append(f"â€¢ {item}")
        lines.append("")
    
    # Interests
    if profile.interests:
        lines.append("<b>Ð˜Ð½Ñ‚ÐµÑ€ÐµÑÑ‹:</b>")
        for item in profile.interests[:4]:
            lines.append(f"â€¢ {item}")
        lines.append("")
    
    # Skills
    if profile.skills:
        lines.append("<b>ÐÐ°Ð²Ñ‹ÐºÐ¸:</b>")
        for item in profile.skills[:5]:
            lines.append(f"â€¢ {item}")
        lines.append("")
    
    # Bio
    if profile.bio:
        lines.append("<b>Ðž ÑÐµÐ±Ðµ:</b>")
        for item in profile.bio[:3]:
            lines.append(item)
        lines.append("")
    
    return "\n".join(lines).strip()


def build_links_card(profile: OwnerProfile) -> str:
    """Build 'Links' card HTML."""
    lines = []
    lines.append("<b>ðŸ”— Ð¡ÑÑ‹Ð»ÐºÐ¸ Ð¸ ÐºÐ¾Ð½Ñ‚Ð°ÐºÑ‚Ñ‹</b>")
    lines.append("")
    
    # Website
    if profile.website_url:
        display = profile.website_url.replace("https://", "").replace("http://", "").rstrip("/")
        lines.append(f"<b>Ð¡Ð°Ð¹Ñ‚:</b> <a href='{profile.website_url}'>{display}</a>")
    
    # GitHub
    if profile.github_url:
        username = profile.github_username or "example"
        display = f"github.com/{username}"
        lines.append(f"<b>GitHub:</b> <a href='{profile.github_url}'>{display}</a>")
    
    # Telegram
    if profile.telegram_url:
        username = profile.telegram_username or "ProjectOwner"
        display = f"@{username}"
        lines.append(f"<b>Telegram:</b> <a href='{profile.telegram_url}'>{display}</a>")
    
    # Telegram channel
    if profile.telegram_channel_url:
        username = profile.telegram_channel_username or "ProjectOwner_channel"
        display = f"@{username}"
        lines.append(f"<b>ÐšÐ°Ð½Ð°Ð»:</b> <a href='{profile.telegram_channel_url}'>{display}</a>")
    
    # Email
    if profile.email:
        lines.append(f"<b>Email:</b> <a href='mailto:{profile.email}'>{profile.email}</a>")
    
    if len(lines) == 2:  # Only header and empty line
        lines.append("<i>ÐšÐ¾Ð½Ñ‚Ð°ÐºÑ‚Ñ‹ Ð½ÐµÐ´Ð¾ÑÑ‚ÑƒÐ¿Ð½Ñ‹</i>")
    
    return "\n".join(lines).strip()


def build_projects_card(profile: OwnerProfile, raw_knowledge: str = "") -> str:
    """Build 'Projects' card HTML."""
    lines = []
    lines.append("<b>ðŸ“‚ ÐŸÑ€Ð¾ÐµÐºÑ‚Ñ‹</b>")
    lines.append("")
    
    projects = []
    
    # Extract from Development section
    if raw_knowledge:
        in_development = False
        for line in raw_knowledge.splitlines():
            line_stripped = line.strip()
            if line_stripped.lower().startswith("# development"):
                in_development = True
                continue
            if in_development:
                if line_stripped.startswith("#"):
                    break
                if line_stripped.startswith("- "):
                    content = line_stripped[2:].strip()
                    # Skip generic lines
                    if content.startswith("Works with") or content.startswith("Uses"):
                        continue
                    text = content.rstrip(".")
                    # Translate
                    translations = {
                        "builds telegram bots and automation tools": "Telegram-Ð±Ð¾Ñ‚Ñ‹ Ð¸ Ð¸Ð½ÑÑ‚Ñ€ÑƒÐ¼ÐµÐ½Ñ‚Ñ‹ Ð°Ð²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ð·Ð°Ñ†Ð¸Ð¸",
                        "builds telegram bots": "Telegram-Ð±Ð¾Ñ‚Ñ‹",
                        "open source projects from github": "Open-source Ð¿Ñ€Ð¾ÐµÐºÑ‚Ñ‹ Ð½Ð° GitHub",
                        "scripts and tools to analyze websites": "Ð¡ÐºÑ€Ð¸Ð¿Ñ‚Ñ‹ Ð´Ð»Ñ Ð°Ð½Ð°Ð»Ð¸Ð·Ð° ÑÐ°Ð¹Ñ‚Ð¾Ð²",
                    }
                    lower_text = text.lower()
                    translated = translations.get(lower_text)
                    if translated:
                        projects.append(translated)
                    elif text:
                        projects.append(text)
    
    # Default projects
    if not projects:
        if profile.occupation:
            projects.extend(profile.occupation[:3])
        else:
            projects = ["Telegram-Ð±Ð¾Ñ‚Ñ‹", "ÐÐ²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ð·Ð°Ñ†Ð¸Ñ", "Ð’ÐµÐ±-Ñ€Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ°"]
    
    for project in projects[:5]:
        lines.append(f"â€¢ {project}")
    
    lines.append("")
    
    if profile.website_url:
        display = profile.website_url.replace("https://", "").replace("http://", "").rstrip("/")
        lines.append(f"<a href='{profile.website_url}'>ÐŸÐ¾Ñ€Ñ‚Ñ„Ð¾Ð»Ð¸Ð¾: {display}</a>")
        lines.append("")

    # GitHub link
    if profile.github_url:
        username = profile.github_username or "example"
        lines.append(f"<a href='{profile.github_url}'>Ð‘Ð¾Ð»ÑŒÑˆÐµ Ð½Ð° github.com/{username}</a>")
    else:
        lines.append("<i>Ð‘Ð¾Ð»ÑŒÑˆÐµ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð¾Ð² Ð½Ð° GitHub</i>")
    
    return "\n".join(lines).strip()


def build_collaboration_card(profile: OwnerProfile) -> str:
    """Build 'Collaboration' card HTML."""
    lines = []
    lines.append("<b>ðŸ¤ Ð¡Ð¾Ñ‚Ñ€ÑƒÐ´Ð½Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾</b>")
    lines.append("")
    
    # Services based on occupation/interests
    services = []
    
    all_text = " ".join(profile.occupation + profile.interests).lower()
    
    if "Ð±Ð¾Ñ‚" in all_text or "telegram" in all_text or "automation" in all_text:
        services.append("Ð Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Telegram-Ð±Ð¾Ñ‚Ð¾Ð²")
    if "Ð²ÐµÐ±" in all_text or "web" in all_text:
        services.append("Ð’ÐµÐ±-Ñ€Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ°")
    if "Ð±ÐµÐ·Ð¾Ð¿Ð°Ñ" in all_text or "security" in all_text:
        services.append("ÐÑƒÐ´Ð¸Ñ‚ Ð±ÐµÐ·Ð¾Ð¿Ð°ÑÐ½Ð¾ÑÑ‚Ð¸")
    if "Ð°Ð²Ñ‚Ð¾Ð¼Ð°Ñ‚" in all_text or "automat" in all_text:
        services.append("ÐÐ²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ð·Ð°Ñ†Ð¸Ñ Ð¿Ñ€Ð¾Ñ†ÐµÑÑÐ¾Ð²")
    if "pentest" in all_text or "penetration" in all_text:
        services.append("Ð¢ÐµÑÑ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ Ð½Ð° Ð¿Ñ€Ð¾Ð½Ð¸ÐºÐ½Ð¾Ð²ÐµÐ½Ð¸Ðµ")
    
    # Default services
    if not services:
        services = [
            "Ð Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Telegram-Ð±Ð¾Ñ‚Ð¾Ð²",
            "Ð’ÐµÐ±-Ñ€Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ°",
            "ÐÐ²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ð·Ð°Ñ†Ð¸Ñ",
            "ÐšÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ñ†Ð¸Ð¸",
        ]
    
    for service in services:
        lines.append(f"â€¢ {service}")
    
    lines.append("")
    lines.append("<b>Ð¡Ð²ÑÐ·Ð°Ñ‚ÑŒÑÑ:</b>")
    
    if profile.telegram_url:
        username = profile.telegram_username or "ProjectOwner"
        lines.append(f"Telegram: <a href='{profile.telegram_url}'>@{username}</a>")
    if profile.email:
        lines.append(f"Email: <a href='mailto:{profile.email}'>{profile.email}</a>")
    
    if not profile.telegram_url and not profile.email:
        lines.append("ÐÐ°Ð¶Ð¼Ð¸Ñ‚Ðµ Â«âœ‰ï¸ Ð—Ð°Ð´Ð°Ñ‚ÑŒ Ð²Ð¾Ð¿Ñ€Ð¾Ñ Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†ÑƒÂ»")
    
    return "\n".join(lines).strip()


def build_faq_card(profile: OwnerProfile) -> str:
    """Build 'FAQ' card HTML."""
    lines = []
    lines.append("<b>â“ Ð§Ð°ÑÑ‚Ñ‹Ðµ Ð²Ð¾Ð¿Ñ€Ð¾ÑÑ‹</b>")
    lines.append("")
    
    # Q1: ÐšÐ°Ðº ÑÐ²ÑÐ·Ð°Ñ‚ÑŒÑÑ?
    lines.append("<b>ÐšÐ°Ðº ÑÐ²ÑÐ·Ð°Ñ‚ÑŒÑÑ?</b>")
    contacts = []
    if profile.telegram_url:
        username = profile.telegram_username or "ProjectOwner"
        contacts.append(f"Telegram: <a href='{profile.telegram_url}'>@{username}</a>")
    if profile.email:
        contacts.append(f"Email: {profile.email}")
    lines.append(" Â· ".join(contacts) if contacts else "Ð§ÐµÑ€ÐµÐ· Ñ„Ð¾Ñ€Ð¼Ñƒ Ð²Ð¾Ð¿Ñ€Ð¾ÑÐ° Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ñƒ")
    lines.append("")
    
    # Q2: Ð§ÐµÐ¼ Ð·Ð°Ð½Ð¸Ð¼Ð°ÐµÑ‚ÑÑ?
    lines.append("<b>Ð§ÐµÐ¼ Ð·Ð°Ð½Ð¸Ð¼Ð°ÐµÑ‚ÑÑ?</b>")
    if profile.occupation:
        lines.append(", ".join(profile.occupation[:3]))
    else:
        lines.append("ÐŸÑ€Ð¾Ð³Ñ€Ð°Ð¼Ð¼Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ, Ð²ÐµÐ±-Ñ€Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ°, Ð±Ð¾Ñ‚Ñ‹")
    lines.append("")
    
    # Q3: Ð¢ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸Ð¸?
    lines.append("<b>Ð¢ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸Ð¸?</b>")
    tech = []
    if profile.skills:
        for skill in profile.skills[:4]:
            tech.append(skill)
    lines.append(", ".join(tech) if tech else "Python, Telegram Bot API, Linux")
    lines.append("")
    
    # Q4: Ð—Ð°ÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð¿Ñ€Ð¾ÐµÐºÑ‚?
    lines.append("<b>Ð—Ð°ÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð¿Ñ€Ð¾ÐµÐºÑ‚?</b>")
    lines.append("ÐÐ°Ð¶Ð¼Ð¸Ñ‚Ðµ Â«âœ‰ï¸ Ð—Ð°Ð´Ð°Ñ‚ÑŒ Ð²Ð¾Ð¿Ñ€Ð¾Ñ Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†ÑƒÂ» Ð¸Ð»Ð¸ Ð½Ð°Ð¿Ð¸ÑˆÐ¸Ñ‚Ðµ Ð½Ð°Ð¿Ñ€ÑÐ¼ÑƒÑŽ")
    
    return "\n".join(lines).strip()


def build_capabilities_card() -> str:
    """Build 'Capabilities' card HTML."""
    lines = []
    lines.append("<b>âš¡ Ð§Ñ‚Ð¾ ÑƒÐ¼ÐµÐµÑ‚ ÑÑ‚Ð¾Ñ‚ Ð°ÑÑÐ¸ÑÑ‚ÐµÐ½Ñ‚</b>")
    lines.append("")
    
    capabilities = [
        "Ð Ð°ÑÑÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð¾ ProjectOwner Ð¸ ÐµÐ³Ð¾ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ…",
        "ÐžÐ±ÑŠÑÑÐ½Ð¸Ñ‚ÑŒ Ñ‚ÐµÑ…Ð½Ð¸Ñ‡ÐµÑÐºÐ¸Ðµ Ð¿Ð¾Ð½ÑÑ‚Ð¸Ñ",
        "ÐÐ°Ð¹Ñ‚Ð¸ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ñ‹ Ð½Ð° GitHub",
        "Ð”Ð°Ñ‚ÑŒ ÑÑÑ‹Ð»ÐºÐ¸ Ð½Ð° ÐºÐ¾Ð½Ñ‚Ð°ÐºÑ‚Ñ‹",
        "Ð Ð°ÑÑÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð¾ Ð²Ð¾Ð·Ð¼Ð¾Ð¶Ð½Ð¾ÑÑ‚ÑÑ… ÑÐ¾Ñ‚Ñ€ÑƒÐ´Ð½Ð¸Ñ‡ÐµÑÑ‚Ð²Ð°",
        "Ð¡Ð²ÑÐ·Ð°Ñ‚ÑŒ Ñ‚ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸Ð¸ Ñ Ñ€ÐµÐ°Ð»ÑŒÐ½Ñ‹Ð¼Ð¸ ÐºÐµÐ¹ÑÐ°Ð¼Ð¸",
    ]
    
    for cap in capabilities:
        lines.append(f"â€¢ {cap}")
    
    lines.append("")
    lines.append("<i>Ð¯ Ð¾Ñ‚Ð²ÐµÑ‡Ð°ÑŽ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð¿Ð¾ Ñ‚ÐµÐ¼Ðµ â€” Ð±ÐµÐ· Ð²Ð¾Ð´Ñ‹ Ð¸ Ð²Ñ‹Ð´ÑƒÐ¼Ð¾Ðº.</i>")
    
    return "\n".join(lines).strip()


# ========================
# MAIN ENTRY POINT
# ========================

def build_card(topic: str, profile: OwnerProfile, raw_knowledge: str = "") -> str:
    """Build card for a given topic."""
    cards = {
        "about_owner": build_owner_card,
        "links": build_links_card,
        "projects": lambda p: build_projects_card(p, raw_knowledge),
        "collaboration": build_collaboration_card,
        "faq": build_faq_card,
        "capabilities": lambda p: build_capabilities_card(),
    }
    
    builder = cards.get(topic)
    if builder:
        return builder(profile)
    
    return "Ð˜Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸Ñ Ð½ÐµÐ´Ð¾ÑÑ‚ÑƒÐ¿Ð½Ð°."


