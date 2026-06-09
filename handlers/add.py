from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from anthropic import Anthropic

import db
import formatting
import keyboards
from services import enrichment, tts
from states import AddCard

router = Router()


@router.message(F.text == keyboards.BTN_ADD)
async def start_add(message: Message, state: FSMContext) -> None:
    await state.set_state(AddCard.waiting_for_text)
    await message.answer("Напиши слово или фразу — на испанском или русском 🙂")


@router.message(AddCard.waiting_for_text, F.text)
async def receive_text(
    message: Message, state: FSMContext, anthropic: Anthropic
) -> None:
    text = message.text.strip()
    try:
        card = enrichment.enrich(anthropic, text)
    except enrichment.EnrichmentError:
        # Stay in waiting_for_text; next message retries. Save-as-is +
        # later re-enrichment is deferred (see out-of-MVP improvements).
        await message.answer(
            "Не получилось обработать сейчас 😕 Попробуй ещё раз через минутку "
            "или пришли другое слово."
        )
        return

    await state.update_data(card=card)
    await message.answer(formatting.card_preview(card))
    await _send_voice(message, card["spanish"])
    await message.answer("Сохранить?", reply_markup=keyboards.save_card_keyboard())


async def _send_voice(message: Message, spanish: str) -> None:
    """Best-effort voice; silent text-only fallback on TTS failure."""
    tmp = os.path.join(tempfile.gettempdir(), f"tts_{abs(hash(spanish))}.ogg")
    try:
        await tts.synthesize(spanish, tmp)
        with open(tmp, "rb") as fh:
            await message.answer_voice(
                BufferedInputFile(fh.read(), filename="word.ogg")
            )
    except (tts.TTSError, OSError):
        await message.answer("🔇 (озвучка временно недоступна)")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


@router.callback_query(F.data == "save:yes")
async def save_yes(
    call: CallbackQuery, state: FSMContext, conn: sqlite3.Connection
) -> None:
    data = await state.get_data()
    card = data["card"]
    db.add_card(
        conn, user_id=call.from_user.id, kind=card["kind"],
        spanish=card["spanish"], russian=card["russian"],
        transcription=card["transcription"], example_es=card["example_es"],
        example_ru=card["example_ru"], enriched=True, today=date.today(),
    )
    await state.clear()
    await call.message.answer("Сохранил! ✅")
    await call.answer()


@router.callback_query(F.data == "save:edit")
async def save_edit(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddCard.waiting_for_correction)
    await call.message.answer("Напиши свой перевод:")
    await call.answer()


@router.message(AddCard.waiting_for_correction, F.text)
async def receive_correction(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    data = await state.get_data()
    card = dict(data["card"])
    card["russian"] = message.text.strip()
    db.add_card(
        conn, user_id=message.from_user.id, kind=card["kind"],
        spanish=card["spanish"], russian=card["russian"],
        transcription=card["transcription"], example_es=card["example_es"],
        example_ru=card["example_ru"], enriched=True, today=date.today(),
    )
    await state.clear()
    await message.answer("Сохранил с твоим переводом! ✅")


@router.callback_query(F.data == "save:no")
async def save_no(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.answer("Ок, не сохраняю.")
    await call.answer()


@router.message(AddCard.waiting_for_text)
async def reject_non_text(message: Message) -> None:
    await message.answer("Я понимаю пока только текст 🙂 Напиши слово или фразу.")
