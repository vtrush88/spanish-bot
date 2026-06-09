from __future__ import annotations

import sqlite3
from datetime import date

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
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


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def add_card(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    kind: str,
    spanish: str,
    russian: str | None,
    transcription: str | None,
    example_es: str | None,
    example_ru: str | None,
    enriched: bool,
    today: date,
) -> int:
    iso = today.isoformat()
    cur = conn.execute(
        """
        INSERT INTO cards (user_id, kind, spanish, russian, transcription,
                           example_es, example_ru, enriched, created_at, due_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, kind, spanish, russian, transcription, example_es,
         example_ru, int(enriched), iso, iso),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_card(conn: sqlite3.Connection, card_id: int) -> sqlite3.Row | None:
    cur = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
    return cur.fetchone()
