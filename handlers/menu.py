from __future__ import annotations

import sqlite3

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

import db
import formatting
import keyboards
import voice

router = Router()

GREETING = (
    "¡Hola! 🌞 Я помогу учить испанский.\n\n"
    "• «➕ Добавить слово» — пришли слово или фразу, я переведу, озвучу и "
    "запомню.\n"
    "• «🎴 Карточки», «✍️ Проверить себя», «🎧 Аудирование» — тренировки.\n"
    "• «📖 Мой словарь» — все добавленные слова."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(GREETING, reply_markup=keyboards.main_menu())


def _render_page(conn: sqlite3.Connection, user_id: int, page: int):
    """Render one vocab page; clamps page after deletions shrink the list."""
    total = db.count_cards(conn, user_id)
    if total == 0:
        return "Словарь пуст. Добавь первое слово через «➕ Добавить слово».", None
    pages = (total + keyboards.PAGE_SIZE - 1) // keyboards.PAGE_SIZE
    page = max(0, min(page, pages - 1))
    cards = db.list_cards(conn, user_id, limit=keyboards.PAGE_SIZE,
                          offset=page * keyboards.PAGE_SIZE)
    lines = [formatting.word_list_line(i + 1 + page * keyboards.PAGE_SIZE, c)
             for i, c in enumerate(cards)]
    text = (formatting.vocab_title(page, pages, total)
            + "\n\n" + "\n".join(lines))
    return text, keyboards.vocab_keyboard(cards, page, total)


@router.message(F.text == keyboards.BTN_VOCAB)
async def show_vocab(message: Message, conn: sqlite3.Connection) -> None:
    text, kb = _render_page(conn, message.from_user.id, 0)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("vocab:"))
async def paginate_vocab(call: CallbackQuery, conn: sqlite3.Connection) -> None:
    """Page navigation; also the «back to list» button on a card."""
    page = int(call.data.split(":")[1])
    text, kb = _render_page(conn, call.from_user.id, page)
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("card:"))
async def show_card(call: CallbackQuery, conn: sqlite3.Connection) -> None:
    _, card_id, page = call.data.split(":")
    card = db.get_card(conn, int(card_id))
    if card is None:
        text, kb = _render_page(conn, call.from_user.id, int(page))
        await call.message.edit_text(text, reply_markup=kb)
        await call.answer("Это слово уже удалено")
        return
    await call.message.edit_text(
        formatting.card_preview(card),
        reply_markup=keyboards.card_detail_keyboard(card["id"], int(page)),
    )
    await voice.send_card_voice(call.message, conn, card)
    await call.answer()


@router.callback_query(F.data.startswith("del:"))
async def delete_word(call: CallbackQuery, conn: sqlite3.Connection) -> None:
    parts = call.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 0
    db.delete_card(conn, int(parts[1]))
    text, kb = _render_page(conn, call.from_user.id, page)
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer("Удалено")
