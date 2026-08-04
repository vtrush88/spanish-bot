"""Автомиграция испаноязычных имён колонок на нейтральные.

Гард поколоночный: DDL в python-sqlite3 автокоммитится, транзакцией четыре
RENAME не обернуть — поэтому каждая колонка проверяется и переименовывается
отдельно, а упавшая на середине миграция дозавершается следующим запуском."""
from datetime import date

import db

OLD_SCHEMA = """
CREATE TABLE cards (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    kind           TEXT NOT NULL,
    spanish        TEXT NOT NULL,
    russian        TEXT,
    transcription  TEXT,
    example_es     TEXT,
    example_ru     TEXT,
    audio_file_id  TEXT,
    enriched       INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    due_at         TEXT NOT NULL,
    interval_days  INTEGER NOT NULL DEFAULT 0,
    reps           INTEGER NOT NULL DEFAULT 0,
    lapses         INTEGER NOT NULL DEFAULT 0
);
"""

NEW_COLUMNS = {"word", "translation", "example", "example_translation"}
OLD_COLUMNS = {"spanish", "russian", "example_es", "example_ru"}


def _columns(conn):
    return {row[1] for row in conn.execute("PRAGMA table_info(cards)")}


def _make_old_db(path):
    conn = db.connect(str(path))
    conn.executescript(OLD_SCHEMA)
    conn.execute(
        "INSERT INTO cards (user_id, kind, spanish, russian, transcription,"
        " example_es, example_ru, created_at, due_at, interval_days, reps,"
        " lapses) VALUES (1, 'word', 'mesa', 'стол', 'мЭса',"
        " 'La mesa es grande.', 'Стол большой.', '2026-06-01', '2026-08-01',"
        " 7, 3, 1)")
    conn.commit()
    return conn


def test_migrates_old_schema_and_keeps_data(tmp_path):
    conn = _make_old_db(tmp_path / "old.db")
    db.init_db(conn)
    cols = _columns(conn)
    assert NEW_COLUMNS <= cols
    assert not (OLD_COLUMNS & cols)
    row = conn.execute("SELECT * FROM cards").fetchone()
    assert row["word"] == "mesa"
    assert row["translation"] == "стол"
    assert row["example"] == "La mesa es grande."
    assert row["example_translation"] == "Стол большой."
    # SRS-поля пережили миграцию
    assert (row["interval_days"], row["reps"], row["lapses"]) == (7, 3, 1)
    assert row["due_at"] == "2026-08-01"


def test_migration_is_idempotent(tmp_path):
    conn = _make_old_db(tmp_path / "old.db")
    db.init_db(conn)
    db.init_db(conn)  # повторный запуск — no-op, не падает
    assert NEW_COLUMNS <= _columns(conn)


def test_partial_migration_completes_on_next_start(tmp_path):
    # «крэш на середине»: первая колонка уже переименована, остальные нет
    conn = _make_old_db(tmp_path / "old.db")
    conn.execute("ALTER TABLE cards RENAME COLUMN spanish TO word")
    db.init_db(conn)
    cols = _columns(conn)
    assert NEW_COLUMNS <= cols
    assert not (OLD_COLUMNS & cols)
    row = conn.execute("SELECT * FROM cards").fetchone()
    assert row["word"] == "mesa" and row["translation"] == "стол"


def test_fresh_db_gets_new_names(tmp_path):
    conn = db.connect(str(tmp_path / "fresh.db"))
    db.init_db(conn)
    cols = _columns(conn)
    assert NEW_COLUMNS <= cols
    assert not (OLD_COLUMNS & cols)


def test_add_and_read_roundtrip_with_new_names(tmp_path):
    conn = db.connect(str(tmp_path / "fresh.db"))
    db.init_db(conn)
    card_id = db.add_card(
        conn, user_id=1, kind="word", word="mesa", translation="стол",
        transcription="мЭса", example="La mesa.", example_translation="Стол.",
        enriched=True, today=date(2026, 8, 4))
    row = db.get_card(conn, card_id)
    assert row["word"] == "mesa"
    assert db.card_exists(conn, 1, "MESA")  # регистронезависимость сохранена
