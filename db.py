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


def update_review(
    conn: sqlite3.Connection,
    card_id: int,
    *,
    interval_days: int,
    due_at: date,
    remembered: bool,
) -> None:
    conn.execute(
        """
        UPDATE cards
        SET interval_days = ?, due_at = ?, reps = reps + 1,
            lapses = lapses + ?
        WHERE id = ?
        """,
        (interval_days, due_at.isoformat(), 0 if remembered else 1, card_id),
    )
    conn.commit()


def get_due_cards(
    conn: sqlite3.Connection, user_id: int, today: date
) -> list[sqlite3.Row]:
    cur = conn.execute(
        "SELECT * FROM cards WHERE user_id = ? AND due_at <= ? ORDER BY due_at",
        (user_id, today.isoformat()),
    )
    return cur.fetchall()


def list_cards(
    conn: sqlite3.Connection, user_id: int, limit: int, offset: int
) -> list[sqlite3.Row]:
    cur = conn.execute(
        "SELECT * FROM cards WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
        (user_id, limit, offset),
    )
    return cur.fetchall()


def count_cards(conn: sqlite3.Connection, user_id: int) -> int:
    cur = conn.execute(
        "SELECT COUNT(*) AS n FROM cards WHERE user_id = ?", (user_id,)
    )
    return int(cur.fetchone()["n"])


def delete_card(conn: sqlite3.Connection, card_id: int) -> None:
    conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    conn.commit()


def set_audio_file_id(
    conn: sqlite3.Connection, card_id: int, file_id: str
) -> None:
    conn.execute(
        "UPDATE cards SET audio_file_id = ? WHERE id = ?", (file_id, card_id)
    )
    conn.commit()


def update_enrichment(
    conn: sqlite3.Connection,
    card_id: int,
    *,
    russian: str,
    transcription: str,
    example_es: str,
    example_ru: str,
) -> None:
    conn.execute(
        """
        UPDATE cards
        SET russian = ?, transcription = ?, example_es = ?, example_ru = ?,
            enriched = 1
        WHERE id = ?
        """,
        (russian, transcription, example_es, example_ru, card_id),
    )
    conn.commit()


def card_exists(conn: sqlite3.Connection, user_id: int, spanish: str) -> bool:
    """Case-insensitive check whether the user already has this Spanish word.

    Compares in Python so accented letters (á, ñ, …) fold correctly, which
    sqlite's ASCII-only lower() would miss.
    """
    target = spanish.strip().lower()
    rows = conn.execute(
        "SELECT spanish FROM cards WHERE user_id = ?", (user_id,)
    ).fetchall()
    return any((r["spanish"] or "").strip().lower() == target for r in rows)
