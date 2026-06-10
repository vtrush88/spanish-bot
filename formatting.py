from __future__ import annotations


def card_preview(card: dict) -> str:
    return (
        f"🔤 {card['spanish']}\n"
        f"🇷🇺 {card['russian']}\n"
        f"🗣 произношение: {card['transcription']}\n"
        f"📝 пример: {card['example_es']} — {card['example_ru']}"
    )


def answer_reveal(card: dict) -> str:
    return f"🇷🇺 {card['russian']}  ·  {card['transcription']}"


def word_list_line(number: int, card: dict) -> str:
    return f"{number}. {card['spanish']} — {card['russian']}"


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
