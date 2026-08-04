from __future__ import annotations

import html


def card_preview(card: dict) -> str:
    """Word card as Telegram HTML — send with parse_mode="HTML".

    The target-language word is bold; every interpolated field is
    HTML-escaped so a literal <, > or & in the data can't break Telegram's
    HTML parser.
    """
    def esc(value) -> str:
        return html.escape(str(value), quote=False)

    return (
        f"🔤 <b>{esc(card['word'])}</b>\n"
        f"🇷🇺 {esc(card['translation'])}\n"
        f"🗣 произношение: {esc(card['transcription'])}\n"
        f"📝 пример: {esc(card['example'])} — {esc(card['example_translation'])}"
    )


def answer_reveal(card: dict) -> str:
    return f"🇷🇺 {card['translation']}  ·  {card['transcription']}"


def word_list_line(number: int, card: dict) -> str:
    return f"{number}. {card['word']} — {card['translation']}"


def vocab_title(page: int, pages: int, total: int) -> str:
    """List header; page counter only when there is more than one page."""
    words = _plural_words(total)
    if pages > 1:
        return f"📖 Твой словарь (стр. {page + 1}/{pages}, {total} {words})"
    return f"📖 Твой словарь ({total} {words})"


def _plural_words(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "слово"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "слова"
    return "слов"
