from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

BTN_ADD = "➕ Добавить слово"
BTN_FLASHCARDS = "🎴 Карточки"
BTN_TRANSLATE = "✍️ Проверить себя"
BTN_LISTEN = "🎧 Аудирование"
BTN_VOCAB = "📖 Мой словарь"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ADD)],
            [KeyboardButton(text=BTN_FLASHCARDS), KeyboardButton(text=BTN_TRANSLATE)],
            [KeyboardButton(text=BTN_LISTEN), KeyboardButton(text=BTN_VOCAB)],
        ],
        resize_keyboard=True,
    )


def reveal_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👁 Показать ответ", callback_data="show_answer")
    ]])


def grade_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Помню", callback_data="grade:remember"),
        InlineKeyboardButton(text="🔁 Не помню", callback_data="grade:forgot"),
    ]])


def save_card_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да", callback_data="save:yes"),
        InlineKeyboardButton(text="❌ Нет", callback_data="save:no"),
    ]])


PAGE_SIZE = 10


def vocab_keyboard(cards: list, page: int, total: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=f"🗑 {i + 1 + page * PAGE_SIZE}",
        callback_data=f"del:{c['id']}",
    )] for i, c in enumerate(cards)]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=f"vocab:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="▶", callback_data=f"vocab:{page + 1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)
