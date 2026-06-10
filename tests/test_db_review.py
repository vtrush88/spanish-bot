from datetime import date

import db


def _add(conn, spanish, russian, today, enriched=True):
    return db.add_card(
        conn, user_id=111, kind="word", spanish=spanish, russian=russian,
        transcription="x", example_es="e", example_ru="э",
        enriched=enriched, today=today,
    )


def test_card_exists_case_insensitive(conn):
    _add(conn, "comida", "еда", date(2026, 6, 3))
    assert db.card_exists(conn, 111, "comida") is True
    assert db.card_exists(conn, 111, "Comida") is True
    assert db.card_exists(conn, 111, "  COMIDA ") is True
    assert db.card_exists(conn, 111, "agua") is False
    # scoped per user
    assert db.card_exists(conn, 999, "comida") is False


def test_card_exists_handles_accents(conn):
    _add(conn, "años", "годы", date(2026, 6, 3))
    assert db.card_exists(conn, 111, "AÑOS") is True


def test_update_review_remembered(conn):
    cid = _add(conn, "comida", "еда", date(2026, 6, 3))
    db.update_review(conn, cid, interval_days=3,
                     due_at=date(2026, 6, 6), remembered=True)
    row = db.get_card(conn, cid)
    assert row["interval_days"] == 3
    assert row["due_at"] == "2026-06-06"
    assert row["reps"] == 1
    assert row["lapses"] == 0


def test_update_review_forgot_increments_lapses(conn):
    cid = _add(conn, "agua", "вода", date(2026, 6, 3))
    db.update_review(conn, cid, interval_days=1,
                     due_at=date(2026, 6, 4), remembered=False)
    row = db.get_card(conn, cid)
    assert row["lapses"] == 1
    assert row["reps"] == 1


def test_get_due_cards_filters_by_date(conn):
    _add(conn, "due_today", "сегодня", date(2026, 6, 3))
    future = _add(conn, "future", "будущее", date(2026, 6, 3))
    db.update_review(conn, future, interval_days=30,
                     due_at=date(2026, 7, 3), remembered=True)
    due = db.get_due_cards(conn, user_id=111, today=date(2026, 6, 3))
    spanish = {r["spanish"] for r in due}
    assert "due_today" in spanish
    assert "future" not in spanish


def test_list_and_delete(conn):
    cid = _add(conn, "uno", "один", date(2026, 6, 3))
    _add(conn, "dos", "два", date(2026, 6, 3))
    assert db.count_cards(conn, 111) == 2
    cards = db.list_cards(conn, user_id=111, limit=10, offset=0)
    assert len(cards) == 2
    db.delete_card(conn, cid, user_id=111)
    assert db.count_cards(conn, 111) == 1


def test_delete_card_scoped_to_owner(conn):
    cid = _add(conn, "uno", "один", date(2026, 6, 3))
    db.delete_card(conn, cid, user_id=999)  # someone else's id
    assert db.get_card(conn, cid) is not None  # card survives
    db.delete_card(conn, cid, user_id=111)
    assert db.get_card(conn, cid) is None


def test_set_audio_and_enrich(conn):
    cid = _add(conn, "hola", None, date(2026, 6, 3), enriched=False)
    db.set_audio_file_id(conn, cid, "FILEID123")
    db.update_enrichment(conn, cid, russian="привет",
                         transcription="Ола", example_es="¡Hola!",
                         example_ru="Привет!")
    row = db.get_card(conn, cid)
    assert row["audio_file_id"] == "FILEID123"
    assert row["russian"] == "привет"
    assert row["enriched"] == 1
