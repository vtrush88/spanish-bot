"""Quota-degradation branches in the handlers (F2 — untested before this).

asyncio_mode = auto (pytest.ini) — plain `async def test_...` needs no marker.
Handlers are exercised directly (no live aiogram dispatch); aiogram objects
are MagicMock/AsyncMock, pure helper modules (srs, session, intents,
formatting) run for real since they don't touch the network.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from handlers import add, training
from services.llm import QuotaExceededError


async def test_receive_text_quota_exceeded_shows_friendly_message_no_save(
    monkeypatch,
):
    monkeypatch.setattr(
        add.enrichment, "enrich", MagicMock(side_effect=QuotaExceededError())
    )
    card_exists = MagicMock()
    monkeypatch.setattr(add.db, "card_exists", card_exists)

    message = MagicMock()
    message.text = "hola"
    message.from_user.id = 1
    message.answer = AsyncMock()

    state = MagicMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()

    conn = MagicMock()

    await add.receive_text(message, state, conn, MagicMock())

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "Лимит бесплатных ИИ-запросов" in text
    card_exists.assert_not_called()  # quota branch returns before touching db


async def test_check_translation_quota_exceeded_marks_not_remembered(monkeypatch):
    monkeypatch.setattr(
        training.grading, "grade", MagicMock(side_effect=QuotaExceededError())
    )
    monkeypatch.setattr(
        training.grading, "answers_match", MagicMock(return_value=False)
    )
    monkeypatch.setattr(training.intents, "is_giveup", MagicMock(return_value=False))

    card = {"id": 1, "spanish": "mesa", "russian": "стол", "interval_days": 1}
    monkeypatch.setattr(training.db, "get_card", MagicMock(return_value=card))
    update_review = MagicMock()
    monkeypatch.setattr(training.db, "update_review", update_review)
    monkeypatch.setattr(training, "_ask_next_translation", AsyncMock())

    message = MagicMock()
    message.text = "mesaa"
    message.answer = AsyncMock()

    state = MagicMock()
    state.get_data = AsyncMock(return_value={"queue": [1], "retried": []})
    state.update_data = AsyncMock()

    conn = MagicMock()

    await training.check_translation(message, state, conn, MagicMock())

    update_review.assert_called_once()
    assert update_review.call_args.kwargs["remembered"] is False

    texts = [call.args[0] for call in message.answer.await_args_list]
    assert any("умная проверка" in t and "mesa" in t for t in texts)
