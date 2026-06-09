from datetime import date

import db


def test_add_and_get_card(conn):
    card_id = db.add_card(
        conn,
        user_id=111,
        kind="word",
        spanish="comida",
        russian="еда",
        transcription="комИда",
        example_es="La comida está lista.",
        example_ru="Еда готова.",
        enriched=True,
        today=date(2026, 6, 3),
    )
    assert isinstance(card_id, int)
    row = db.get_card(conn, card_id)
    assert row["spanish"] == "comida"
    assert row["russian"] == "еда"
    assert row["enriched"] == 1
    assert row["interval_days"] == 0
    assert row["reps"] == 0
    assert row["due_at"] == "2026-06-03"
    assert row["created_at"] == "2026-06-03"


def test_get_missing_card_returns_none(conn):
    assert db.get_card(conn, 999) is None
