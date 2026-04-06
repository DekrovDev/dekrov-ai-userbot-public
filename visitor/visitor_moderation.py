from __future__ import annotations

import html
import re
from dataclasses import dataclass

from config.identity import is_non_owner_threat


@dataclass(frozen=True, slots=True)
class ModerationHit:
    reason: str
    label: str
    warning_message: str


_ABUSE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?iu)\b("
            r"идиот|идиотка|дебил|дебилка|тупой|тупая|тупое|тупые|"
            r"мразь|мудак|пид[ао]р|пидр|сука|сучка|соси|"
            r"ебан(ый|ая|ое|ые)?|ебать|ебал|ебло|хуй|ху[йе]вый|"
            r"нахуй|нахер|пош[её]л\s+на"
            r")\b"
        ),
        "оскорбления",
    ),
    (
        re.compile(
            r"(?iu)\b("
            r"idiot|moron|stupid|dumb|retard|bitch|asshole|"
            r"fuck\s+you|fucking\s+bot"
            r")\b"
        ),
        "оскорбления",
    ),
)


def detect_abusive_message(text: str | None) -> ModerationHit | None:
    sample = " ".join((text or "").split()).strip()
    if not sample:
        return None

    if is_non_owner_threat(sample):
        return ModerationHit(
            reason="threat",
            label="угрозы",
            warning_message=(
                "⚠️ Я не продолжаю разговор в таком тоне. "
                "Если хотите продолжить, сформулируйте вопрос нормально."
            ),
        )

    for pattern, label in _ABUSE_PATTERNS:
        if pattern.search(sample):
            return ModerationHit(
                reason="abuse",
                label=label,
                warning_message=(
                    "⚠️ Давайте без оскорблений. "
                    "Если хотите продолжить, напишите вопрос нормально."
                ),
            )

    return None


def format_moderation_owner_notification(
    *,
    user_id: int,
    username: str | None,
    first_name: str | None,
    text: str,
    reason_label: str,
    strikes: int,
    blocked_now: bool,
    source: str,
) -> str:
    display_name = first_name or (f"@{username}" if username else f"user_{user_id}")
    source_label = "visitor" if source == "visitor" else "chat bot"
    action_line = (
        "Пользователь автоматически ограничен на 24 часа."
        if blocked_now
        else "Автоблок ещё не выдан. Можно решить вручную."
    )
    safe_text = html.escape((text or "").strip())
    if len(safe_text) > 700:
        safe_text = safe_text[:700].rstrip() + "..."

    return (
        "⚠️ <b>Сработала модерация публичного бота</b>\n\n"
        f"<b>Пользователь:</b> {html.escape(display_name)}\n"
        f"<b>ID:</b> <code>{user_id}</code>\n"
        f"<b>Источник:</b> {html.escape(source_label)}\n"
        f"<b>Причина:</b> {html.escape(reason_label)}\n"
        f"<b>Страйки:</b> {strikes}/3\n"
        f"<b>Статус:</b> {html.escape(action_line)}\n\n"
        f"<b>Сообщение:</b>\n<blockquote>{safe_text}</blockquote>\n\n"
        f"<code>/vblock {user_id}</code>\n"
        f"<code>/vunblock {user_id}</code>"
    )
