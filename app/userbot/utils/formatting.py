"""Функции форматирования для userbot.

Конвертация Markdown в Telegram HTML, форматирование команд.
"""

from __future__ import annotations

import re


def md_to_tg_html(text: str) -> str:
    """Конвертировать Markdown-вывод модели в Telegram HTML.

    Поддерживает:
    - fenced code blocks (```lang ... ```)
    - inline code (`code`)
    - bold (**text** или __text__)
    - italic (*text* или _text_)
    - strikethrough (~~text~~)
    - spoiler (||text||)
    - blockquote (> text)

    Args:
        text: Текст в Markdown-формате

    Returns:
        Текст в Telegram HTML-формате
    """
    import html as _html

    result = text

    # Fenced code blocks
    def replace_fenced(m: re.Match) -> str:
        lang = (m.group(1) or "").strip()
        code = _html.escape(m.group(2))
        if lang:
            return f'<pre><code class="language-{lang}">{code}</code></pre>'
        return f"<pre><code>{code}</code></pre>"

    result = re.sub(r"```([^\n`]*)\n(.*?)```", replace_fenced, result, flags=re.DOTALL)

    # Inline code
    result = re.sub(
        r"`([^`\n]+)`", lambda m: f"<code>{_html.escape(m.group(1))}</code>", result
    )

    # Bold
    result = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", result, flags=re.DOTALL)
    result = re.sub(r"__(.+?)__", r"<b>\1</b>", result, flags=re.DOTALL)

    # Italic
    result = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", result)
    result = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", result)

    # Strikethrough
    result = re.sub(r"~~(.+?)~~", r"<s>\1</s>", result, flags=re.DOTALL)

    # Spoiler
    result = re.sub(
        r"\|\|(.+?)\|\|", r"<tg-spoiler>\1</tg-spoiler>", result, flags=re.DOTALL
    )

    # Blockquote
    def replace_blockquote(m: re.Match) -> str:
        inner = re.sub(r"^>\s?", "", m.group(0), flags=re.MULTILINE).strip()
        return f"<blockquote>{inner}</blockquote>"

    result = re.sub(r"(?:^|\n)((?:>[^\n]*\n?)+)", replace_blockquote, result)

    return result


def quote_for_command(text: str) -> str:
    """Экранировать текст для использования в команде.

    Args:
        text: Текст для экранирования

    Returns:
        Экранированный текст в кавычках
    """
    escaped = (text or "").replace("\\", "\\\\").replace('"', '\\"').strip()
    return f'"{escaped}"'


def build_command_mode_usage_hint() -> str:
    """Построить справку по режимам команд.

    Returns:
        Строка с описанием префиксов команд
    """
    return (
        ".д / .d / .chat - диалог, анализ, планирование\n"
        ".к / .k / .tg / .cmd - Telegram actions\n"
        ".б / .b / .ai / .bot - поиск, выводки, текст, картинки\n"
        "Для подтверждения: Д / Н"
    )


def build_dialogue_action_hint(prompt: str) -> str:
    """Построить подсказку для диалогового действия.

    Args:
        prompt: Исходный промпт команды

    Returns:
        Каноническая форма команды
    """
    canonical = prompt.strip()
    if canonical.casefold().startswith((".к", ".k")):
        canonical = canonical[2:].lstrip(" :")
    return canonical
