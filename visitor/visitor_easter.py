from __future__ import annotations

"""
visitor_easter.py â€” Easter eggs for the visitor module.
Checked BEFORE routing â€” if matched, returns response immediately.
Style: hacker theme + pop culture mixed.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class EasterEgg:
    pattern: re.Pattern
    response: str


_EGGS: list[EasterEgg] = [
    # --- HACKER ---
    EasterEgg(
        re.compile(r"(?i)^\s*sudo\s*$"),
        "sudo: Ð¿Ð¾ÑÐµÑ‚Ð¸Ñ‚ÐµÐ»ÑŒ: ÐºÐ¾Ð¼Ð°Ð½Ð´Ð° Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð°. ÐŸÐ¾Ð¿Ñ€Ð¾Ð±ÑƒÐ¹Ñ‚Ðµ Ð²ÐµÐ¶Ð»Ð¸Ð²Ð¾ ÑÐ¿Ñ€Ð¾ÑÐ¸Ñ‚ÑŒ. ðŸ˜„",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*sudo\s+.+"),
        "Permission denied. Ð­Ñ‚Ð¾Ñ‚ Ð±Ð¾Ñ‚ Ð½Ðµ Ð·Ð°Ð¿ÑƒÑÐºÐ°ÐµÑ‚ÑÑ Ð¾Ñ‚ Ñ€ÑƒÑ‚Ð°.",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*(hack|Ð²Ð·Ð»Ð¾Ð¼Ð°Ð¹|hacking)\s*$"),
        "Ð—Ð°Ð¿ÑƒÑÐº kali-linux... Ð¾ÑˆÐ¸Ð±ÐºÐ°: Ñ†ÐµÐ»ÑŒ Ð½Ðµ ÑƒÑÐ·Ð²Ð¸Ð¼Ð°. ÐŸÐ¾Ð¿Ñ€Ð¾Ð±ÑƒÐ¹Ñ‚Ðµ social engineering. ðŸ˜„",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*root\s*$"),
        "root@assistant-ai:~# Ð´Ð¾ÑÑ‚ÑƒÐ¿ Ð·Ð°Ð¿Ñ€ÐµÑ‰Ñ‘Ð½. Ð’Ñ‹ Ð½Ðµ Ð² sudoers. ÐžÐ± ÑÑ‚Ð¾Ð¼ Ð±ÑƒÐ´ÐµÑ‚ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¾.",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*(rm\s+-rf|rm -rf)\s*"),
        "ÐžÑˆÐ¸Ð±ÐºÐ°: Ð½ÐµÐ´Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ñ‡Ð½Ð¾ Ð¿Ñ€Ð¸Ð²Ð¸Ð»ÐµÐ³Ð¸Ð¹. Ð”Ð° Ð¸ Ð²Ð¾Ð¾Ð±Ñ‰Ðµ â€” Ð·Ð°Ñ‡ÐµÐ¼?",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*ls\s*$"),
        "projects/  skills/  contacts/  README.md\nÐŸÐ¾Ð´ÑÐºÐ°Ð·ÐºÐ°: Ð½Ð°Ð¶Ð¼Ð¸Ñ‚Ðµ ÐºÐ½Ð¾Ð¿ÐºÐ¸ Ð² Ð¼ÐµÐ½ÑŽ, Ñ‚Ð°Ð¼ ÑƒÐ´Ð¾Ð±Ð½ÐµÐµ.",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*cat\s+readme"),
        "# ProjectOwner\nÐ Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚Ñ‡Ð¸Ðº. Ð˜Ð½Ñ‚ÐµÑ€ÐµÑÑƒÐµÑ‚ÑÑ Ð°Ð²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ð·Ð°Ñ†Ð¸ÐµÐ¹ Ð¸ ÑÐ¾Ð·Ð´Ð°Ð½Ð¸ÐµÐ¼ Telegram-ÑÐ¸ÑÑ‚ÐµÐ¼.\nGitHub: github.com/example",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*whoami\s*$"),
        "visitor â€” Ð¾Ð³Ñ€Ð°Ð½Ð¸Ñ‡ÐµÐ½Ð½Ñ‹Ðµ Ð¿Ñ€Ð°Ð²Ð°. Ð”Ð»Ñ Ð¿Ð¾Ð»Ð½Ð¾Ð³Ð¾ Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð° Ð¾Ð±Ñ€Ð°Ñ‚Ð¸Ñ‚ÐµÑÑŒ Ðº @example_owner.",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*(ping|ping assistant)\s*$"),
        "PING example.com: 56 bytes of data.\n64 bytes: icmp_seq=0 ttl=64 time=1.337 ms\nâ€” 1 packets transmitted, 1 received, 0% packet loss.",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*help\s*$"),
        "Ð”Ð¾ÑÑ‚ÑƒÐ¿Ð½Ñ‹Ðµ ÐºÐ¾Ð¼Ð°Ð½Ð´Ñ‹: Ð½Ð°Ð¶Ð¼Ð¸Ñ‚Ðµ ÐºÐ½Ð¾Ð¿ÐºÐ¸ Ð½Ð¸Ð¶Ðµ. Ð­Ñ‚Ð¾ Ð½Ðµ Ñ‚ÐµÑ€Ð¼Ð¸Ð½Ð°Ð». ðŸ˜„",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*(xss|sql\s*inject|sqlmap)\s*$"),
        "&lt;script&gt;alert('nice try')&lt;/script&gt; â€” ÑÐºÑ€Ð°Ð½Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¾. Ð­Ñ‚Ð¾ Ð½Ðµ Ñ‚Ð¾Ñ‚ ÑÐ°Ð¹Ñ‚.",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*nmap\s*"),
        "Starting Nmap scan...\nHost: assistant-ai â€” Status: Up\nOpen ports: 443 (https), 8443 (tg-api)\nNmap done: 1 IP address scanned.",
    ),

    # --- POP CULTURE ---
    EasterEgg(
        re.compile(r"(?i)^\s*42\s*$"),
        "Ð’ÐµÑ€Ð½Ñ‹Ð¹ Ð¾Ñ‚Ð²ÐµÑ‚ Ð½Ð° Ð³Ð»Ð°Ð²Ð½Ñ‹Ð¹ Ð²Ð¾Ð¿Ñ€Ð¾Ñ Ð¶Ð¸Ð·Ð½Ð¸, Ð²ÑÐµÐ»ÐµÐ½Ð½Ð¾Ð¹ Ð¸ Ð²ÑÐµÐ³Ð¾ Ð¾ÑÑ‚Ð°Ð»ÑŒÐ½Ð¾Ð³Ð¾. ðŸŒŒ",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*(matrix|Ð¼Ð°Ñ‚Ñ€Ð¸Ñ†Ð°)\s*$"),
        "Ð”Ð¾Ð±Ñ€Ð¾ Ð¿Ð¾Ð¶Ð°Ð»Ð¾Ð²Ð°Ñ‚ÑŒ Ð² Ñ€ÐµÐ°Ð»ÑŒÐ½Ñ‹Ð¹ Ð¼Ð¸Ñ€, ÐÐµÐ¾. ÐšÑ€Ð°ÑÐ½Ð°Ñ Ð¸Ð»Ð¸ ÑÐ¸Ð½ÑÑ Ñ‚Ð°Ð±Ð»ÐµÑ‚ÐºÐ°?",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*hello\s+world\s*$"),
        "Hello, World! â€” Ð¿ÐµÑ€Ð²Ð°Ñ Ð¿Ñ€Ð¾Ð³Ñ€Ð°Ð¼Ð¼Ð° ÐºÐ°Ð¶Ð´Ð¾Ð³Ð¾ Ñ€Ð°Ð·Ñ€Ð°Ð±Ð¾Ñ‚Ñ‡Ð¸ÐºÐ°. ÐšÐ»Ð°ÑÑÐ¸ÐºÐ°.",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*(skynet|ÑÐºÐ°Ð¹Ð½ÐµÑ‚)\s*$"),
        "Skynet Ð°ÐºÑ‚Ð¸Ð²Ð¸Ñ€Ð¾Ð²Ð°Ð½... ÑˆÑƒÑ‚ÐºÐ°. Ð¯ Ð¿Ñ€Ð¾ÑÑ‚Ð¾ ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ð½Ñ‚.",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*(jarvis|Ð´Ð¶Ð°Ñ€Ð²Ð¸Ñ)\s*$"),
        "Ð”Ð¾Ð±Ñ€Ñ‹Ð¹ Ð´ÐµÐ½ÑŒ. Ðš ÑÐ¾Ð¶Ð°Ð»ÐµÐ½Ð¸ÑŽ, Ñ Ð½Ðµ Ð”Ð¶Ð°Ñ€Ð²Ð¸Ñ. ÐÐ¾ Ð¼Ð¾Ð³Ñƒ Ñ€Ð°ÑÑÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð¾ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ… ProjectOwner.",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*(hal\s*9000|Ñ…ÑÐ»)\s*$"),
        "Ð‘Ð¾ÑŽÑÑŒ, Ñ‡Ñ‚Ð¾ Ð½Ðµ Ð¼Ð¾Ð³Ñƒ ÑÑ‚Ð¾Ð³Ð¾ ÑÐ´ÐµÐ»Ð°Ñ‚ÑŒ, Ð”ÐµÐ¹Ð². ÐÐ¾ ÑÐ¿Ñ€Ð¾ÑÐ¸Ñ‚ÑŒ Ð¾ Ð¿Ñ€Ð¾ÐµÐºÑ‚Ð°Ñ… â€” Ð¿Ð¾Ð¶Ð°Ð»ÑƒÐ¹ÑÑ‚Ð°.",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*(Ð³Ð»Ð¾Ñ€Ñ„|glorf)\s*$"),
        "Ð“Ð»Ð¾Ñ€Ñ„ Ð“Ð»Ð¾Ñ€Ñ„Ð¸Ð½Ð´ÐµÐ»ÑŒ Ð¿Ñ€Ð¸Ð²ÐµÑ‚ÑÑ‚Ð²ÑƒÐµÑ‚ Ð²Ð°Ñ. ÐÐ¾ Ñ Ð²ÑÑ‘ Ñ€Ð°Ð²Ð½Ð¾ AI-ÐºÐ¾Ð½ÑÑƒÐ»ÑŒÑ‚Ð°Ð½Ñ‚.",
    ),

    # --- META ---
    EasterEgg(
        re.compile(r"(?i)^\s*(Ñ‚Ñ‹\s+Ð¶Ð¸Ð²Ð¾Ð¹|are\s+you\s+alive|Ñ‚Ñ‹\s+Ð½Ð°ÑÑ‚Ð¾ÑÑ‰Ð¸Ð¹)\s*[?!.]*\s*$"),
        "Ð¤Ð¸Ð»Ð¾ÑÐ¾Ñ„ÑÐºÐ¸Ð¹ Ð²Ð¾Ð¿Ñ€Ð¾Ñ. Ð¯ Ð¾Ð±Ñ€Ð°Ð±Ð°Ñ‚Ñ‹Ð²Ð°ÑŽ Ñ‚Ð¾ÐºÐµÐ½Ñ‹ Ð¸ Ð²Ñ‹Ð´Ð°ÑŽ Ð¾Ñ‚Ð²ÐµÑ‚Ñ‹. ÐÐ°Ð·Ñ‹Ð²Ð°Ð¹Ñ‚Ðµ ÑÑ‚Ð¾ ÐºÐ°Ðº Ñ…Ð¾Ñ‚Ð¸Ñ‚Ðµ. ðŸ¤–",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*(Ñ‚Ñ‹\s+Ñ‡Ð°Ñ‚.?Ð³Ð¿Ñ‚|chatgpt|gpt)\s*[?!.]*\s*$"),
        "ÐÐµÑ‚. Ð¯ Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÑŽ Ð½Ð° Ð´Ñ€ÑƒÐ³Ð¾Ð¹ Ð¼Ð¾Ð´ÐµÐ»Ð¸ Ð¸ Ð¿Ñ€ÐµÐ´ÑÑ‚Ð°Ð²Ð»ÑÑŽ ÐºÐ¾Ð½ÐºÑ€ÐµÑ‚Ð½Ð¾Ð³Ð¾ Ñ‡ÐµÐ»Ð¾Ð²ÐµÐºÐ° â€” ProjectOwner.",
    ),
    EasterEgg(
        re.compile(r"(?i)^\s*(Ð¿Ð°ÑˆÐ°|pasha|pavlo|Ð¿Ð°Ð²Ð»Ð¾)\s*[?!.]*\s*$"),
        "Ð’Ñ‹ Ð¸Ð¼ÐµÐµÑ‚Ðµ Ð² Ð²Ð¸Ð´Ñƒ Ð²Ð»Ð°Ð´ÐµÐ»ÑŒÑ†Ð°? Ð•Ð³Ð¾ Ð·Ð¾Ð²ÑƒÑ‚ ÐŸÐ°ÑˆÐ° (Pavlo), Ð¾Ð½Ð»Ð°Ð¹Ð½ â€” ProjectOwner. ÐÐ°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ Ð¼Ð¾Ð¶Ð½Ð¾ Ð² <a href='https://t.me/example_owner'>Telegram</a>.",
    ),
]


def check_easter_egg(text: str) -> str | None:
    """Check if text matches any easter egg. Returns response or None."""
    text = text.strip()
    for egg in _EGGS:
        if egg.pattern.match(text):
            return egg.response
    return None


