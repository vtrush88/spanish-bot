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
