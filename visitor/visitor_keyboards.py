from __future__ import annotations

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def visitor_main_menu() -> InlineKeyboardMarkup:
    """Main visitor menu — shown when visitor starts the bot."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💬 Начать консультацию", callback_data="visitor_start_chat"),
            ],
            [
                InlineKeyboardButton("👤 О владельце", callback_data="visitor_about_owner"),
                InlineKeyboardButton("📂 Проекты", callback_data="visitor_projects"),
            ],
            [
                InlineKeyboardButton("🔗 Ссылки", callback_data="visitor_links"),
                InlineKeyboardButton("🤝 Сотрудничество", callback_data="visitor_collaboration"),
            ],
            [
                InlineKeyboardButton("❓ FAQ", callback_data="visitor_faq"),
                InlineKeyboardButton("⚡ Возможности", callback_data="visitor_capabilities"),
            ],
            [
                InlineKeyboardButton("✉️ Задать вопрос владельцу", callback_data="visitor_ask_owner"),
            ],
        ]
    )


def visitor_disabled_menu() -> InlineKeyboardMarkup:
    """Visitor menu when visitor mode is disabled — read-only, no consultation."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👤 О владельце", callback_data="visitor_about_owner"),
                InlineKeyboardButton("📂 Проекты", callback_data="visitor_projects"),
            ],
            [
                InlineKeyboardButton("🔗 Ссылки", callback_data="visitor_links"),
                InlineKeyboardButton("🤝 Сотрудничество", callback_data="visitor_collaboration"),
            ],
            [
                InlineKeyboardButton("❓ FAQ", callback_data="visitor_faq"),
                InlineKeyboardButton("⚡ Возможности", callback_data="visitor_capabilities"),
            ],
        ]
    )


def visitor_chat_active_menu() -> InlineKeyboardMarkup:
    """Menu shown while visitor is in active chat session."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👤 О владельце", callback_data="visitor_about_owner"),
                InlineKeyboardButton("📂 Проекты", callback_data="visitor_projects"),
            ],
            [
                InlineKeyboardButton("🔗 Ссылки", callback_data="visitor_links"),
                InlineKeyboardButton("🤝 Сотрудничество", callback_data="visitor_collaboration"),
            ],
            [
                InlineKeyboardButton("✉️ Спросить владельца", callback_data="visitor_ask_owner"),
                InlineKeyboardButton("🚪 Завершить", callback_data="visitor_end"),
            ],
        ]
    )


def visitor_back_menu() -> InlineKeyboardMarkup:
    """Back to main menu button."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💬 Начать консультацию", callback_data="visitor_start_chat"),
                InlineKeyboardButton("🔙 В меню", callback_data="visitor_menu"),
            ],
        ]
    )


def visitor_after_answer_menu() -> InlineKeyboardMarkup:
    """Shown after AI answer during active session."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📂 Проекты", callback_data="visitor_projects"),
                InlineKeyboardButton("🔗 Ссылки", callback_data="visitor_links"),
            ],
            [
                InlineKeyboardButton("🚪 Завершить", callback_data="visitor_end"),
            ],
        ]
    )


def visitor_end_suggestion_menu() -> InlineKeyboardMarkup:
    """Shown when AI suggests ending the conversation."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Завершить", callback_data="visitor_end"),
                InlineKeyboardButton("💬 Продолжить", callback_data="visitor_menu"),
            ],
        ]
    )


# ========================
# ADMIN KEYBOARDS
# ========================

def admin_visitor_panel_menu() -> InlineKeyboardMarkup:
    """Admin panel main menu for visitor module."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 Статистика", callback_data="vadmin_stats"),
                InlineKeyboardButton("👥 Активные сессии", callback_data="vadmin_sessions"),
            ],
            [
                InlineKeyboardButton("📈 Топ тем", callback_data="vadmin_topics"),
                InlineKeyboardButton("🗑 Очистить всё", callback_data="vadmin_clear_all"),
            ],
            [
                InlineKeyboardButton("📢 Рассылка", callback_data="vadmin_broadcast_prompt"),
                InlineKeyboardButton("🔕 Режим тишины", callback_data="vadmin_toggle_quiet"),
            ],
            [
                InlineKeyboardButton("📬 Входящие", callback_data="vadmin_inbox"),
                InlineKeyboardButton("📋 FAQ авто", callback_data="vadmin_faq_list"),
            ],
            [
                InlineKeyboardButton("🔙 Закрыть", callback_data="vadmin_close"),
            ],
        ]
    )


def admin_confirm_clear() -> InlineKeyboardMarkup:
    """Confirm destructive action."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Да, очистить", callback_data="vadmin_clear_confirm"),
                InlineKeyboardButton("❌ Отмена", callback_data="vadmin_stats"),
            ],
        ]
    )


def admin_back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Назад", callback_data="vadmin_stats")]]
    )


def visitor_cancel_menu() -> InlineKeyboardMarkup:
    """Shown when visitor is typing a question for owner."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Отмена", callback_data="visitor_cancel_question")]]
    )


def admin_inbox_menu() -> InlineKeyboardMarkup:
    """Admin inbox actions."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📬 Входящие", callback_data="vadmin_inbox"),
                InlineKeyboardButton("📋 FAQ", callback_data="vadmin_faq_list"),
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="vadmin_stats")],
        ]
    )
