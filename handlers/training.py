from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

import db
import formatting
import keyboards
from services import grading, srs, tts
from states import Training

router = Router()
EMPTY = ("На сегодня всё повторили! 🎉 Можешь добавить новые слова "
         "или зайти позже.")


async def _send_voice(message: Message, conn: sqlite3.Connection, card) -> None:
    """Send cached voice by file_id, else synthesize and cache the file_id."""
    if card["audio_file_id"]:
        await message.answer_voice(card["audio_file_id"])
        return
    tmp = os.path.join(tempfile.gettempdir(), f"tts_{card['id']}.ogg")
    try:
        await tts.synthesize(card["spanish"], tmp)
        with open(tmp, "rb") as fh:
            sent = await message.answer_voice(
                BufferedInputFile(fh.read(), filename="word.ogg")
            )
        db.set_audio_file_id(conn, card["id"], sent.voice.file_id)
    except (tts.TTSError, OSError):
        pass  # text card already shown; audio is best-effort
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


async def _show_next_flashcard(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    data = await state.get_data()
    queue = data.get("queue", [])
    if not queue:
        await state.clear()
        await message.answer("Готово на сегодня! 👏", reply_markup=keyboards.main_menu())
        return
    card_id = queue[0]
    card = db.get_card(conn, card_id)
    await message.answer(f"🎴 {card['spanish']}")
    await _send_voice(message, conn, card)
    await message.answer("…вспомни перевод…",
                         reply_markup=keyboards.reveal_keyboard())


@router.message(F.text == keyboards.BTN_FLASHCARDS)
async def start_flashcards(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    due = db.get_due_cards(conn, message.from_user.id, date.today())
    if not due:
        await message.answer(EMPTY)
        return
    await state.set_state(Training.flashcards)
    await state.update_data(queue=[r["id"] for r in due])
    await _show_next_flashcard(message, state, conn)


@router.callback_query(Training.flashcards, F.data == "show_answer")
async def reveal(call: CallbackQuery, state: FSMContext,
                 conn: sqlite3.Connection) -> None:
    data = await state.get_data()
    card = db.get_card(conn, data["queue"][0])
    await call.message.answer(formatting.answer_reveal(card),
                              reply_markup=keyboards.grade_keyboard())
    await call.answer()


@router.callback_query(Training.flashcards, F.data.startswith("grade:"))
async def grade_flashcard(call: CallbackQuery, state: FSMContext,
                          conn: sqlite3.Connection) -> None:
    remembered = call.data == "grade:remember"
    data = await state.get_data()
    queue = data["queue"]
    card = db.get_card(conn, queue[0])
    new_interval = srs.next_interval(card["interval_days"], remembered)
    db.update_review(conn, card["id"], interval_days=new_interval,
                     due_at=srs.due_on(date.today(), new_interval),
                     remembered=remembered)
    await state.update_data(queue=queue[1:])
    await call.answer("👍" if remembered else "Повторим ещё")
    await _show_next_flashcard(call.message, state, conn)


async def _ask_next_translation(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    data = await state.get_data()
    queue = data.get("queue", [])
    if not queue:
        await state.clear()
        await message.answer("Готово на сегодня! 👏",
                             reply_markup=keyboards.main_menu())
        return
    card = db.get_card(conn, queue[0])
    await message.answer(f"Как по-испански: «{card['russian']}»?")


@router.message(F.text == keyboards.BTN_TRANSLATE)
async def start_translate(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    due = db.get_due_cards(conn, message.from_user.id, date.today())
    if not due:
        await message.answer(EMPTY)
        return
    await state.set_state(Training.translate)
    await state.update_data(queue=[r["id"] for r in due])
    await _ask_next_translation(message, state, conn)


@router.message(Training.translate, F.text)
async def check_translation(
    message: Message, state: FSMContext, conn: sqlite3.Connection, anthropic
) -> None:
    data = await state.get_data()
    queue = data["queue"]
    card = db.get_card(conn, queue[0])
    try:
        verdict = grading.grade(
            anthropic, prompt_ru=card["russian"],
            expected_es=card["spanish"], answer=message.text.strip(),
        )
        ok = verdict["verdict"] in ("correct", "typo")
        if verdict["verdict"] == "correct":
            await message.answer(f"✅ Верно! {verdict['note']}")
        elif verdict["verdict"] == "typo":
            await message.answer(
                f"✅ Почти! Правильно: {verdict['correct_spanish']} "
                f"({verdict['note']})"
            )
        else:
            await message.answer(
                f"❌ Не совсем. Правильно: {verdict['correct_spanish']} "
                f"({verdict['note']})"
            )
    except grading.GradingError:
        # Fall back to a forgiving exact-match check if Claude is unavailable.
        ok = message.text.strip().lower() == card["spanish"].lower()
        await message.answer("✅ Верно!" if ok
                             else f"❌ Правильно: {card['spanish']}")

    new_interval = srs.next_interval(card["interval_days"], ok)
    db.update_review(conn, card["id"], interval_days=new_interval,
                     due_at=srs.due_on(date.today(), new_interval),
                     remembered=ok)
    await state.update_data(queue=queue[1:])
    await _ask_next_translation(message, state, conn)


async def _ask_next_listen(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    data = await state.get_data()
    queue = data.get("queue", [])
    if not queue:
        await state.clear()
        await message.answer("Готово на сегодня! 👏",
                             reply_markup=keyboards.main_menu())
        return
    card = db.get_card(conn, queue[0])
    await message.answer("🔊 Что это за слово? Напиши, что услышала:")
    await _send_voice(message, conn, card)


@router.message(F.text == keyboards.BTN_LISTEN)
async def start_listen(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    due = db.get_due_cards(conn, message.from_user.id, date.today())
    if not due:
        await message.answer(EMPTY)
        return
    await state.set_state(Training.listen)
    await state.update_data(queue=[r["id"] for r in due])
    await _ask_next_listen(message, state, conn)


@router.message(Training.listen, F.text)
async def check_listen(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    data = await state.get_data()
    queue = data["queue"]
    card = db.get_card(conn, queue[0])
    ok = message.text.strip().lower() == card["spanish"].lower()
    if ok:
        await message.answer(f"✅ Да! 🔤 {card['spanish']} — {card['russian']}")
    else:
        await message.answer(
            f"Услышалось: {card['spanish']} — {card['russian']}"
        )
    new_interval = srs.next_interval(card["interval_days"], ok)
    db.update_review(conn, card["id"], interval_days=new_interval,
                     due_at=srs.due_on(date.today(), new_interval),
                     remembered=ok)
    await state.update_data(queue=queue[1:])
    await _ask_next_listen(message, state, conn)
