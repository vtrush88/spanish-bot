from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AddCard(StatesGroup):
    waiting_for_text = State()


class Training(StatesGroup):
    flashcards = State()
    translate = State()
    listen = State()
