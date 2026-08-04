import sqlite3
import subprocess
from datetime import date
from pathlib import Path

import db

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backup-db.sh"


def _seed_db(path, n):
    conn = db.connect(str(path))
    db.init_db(conn)
    for i in range(n):
        db.add_card(conn, user_id=1, kind="word", word=f"w{i}",
                    translation="x", transcription="x", example="x",
                    example_translation="x", enriched=True, today=date(2026, 6, 15))
    conn.close()


def test_backup_creates_consistent_snapshot(tmp_path):
    src = tmp_path / "spanish_bot.db"
    _seed_db(src, 3)
    backups = tmp_path / "backups"
    subprocess.run(["bash", str(SCRIPT), str(src), str(backups)], check=True)
    made = list(backups.glob("spanish_bot-*.db"))
    assert len(made) == 1
    c = sqlite3.connect(made[0])
    assert c.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 3
    c.close()


def test_backup_rotation_keeps_seven(tmp_path):
    src = tmp_path / "spanish_bot.db"
    _seed_db(src, 1)
    backups = tmp_path / "backups"
    backups.mkdir()
    # 8 older dated backups; names sort chronologically
    for d in range(1, 9):
        (backups / f"spanish_bot-2026-05-0{d}.db").write_text("old")
    subprocess.run(["bash", str(SCRIPT), str(src), str(backups)], check=True)
    remaining = sorted(p.name for p in backups.glob("spanish_bot-*.db"))
    assert len(remaining) == 7
    # today's snapshot (2026-06-..) is newest and kept; two oldest removed
    assert "spanish_bot-2026-05-01.db" not in remaining
    assert "spanish_bot-2026-05-02.db" not in remaining
    # Verify both ends of the keep window: today's newest + oldest survivor
    today_name = f"spanish_bot-{date.today().strftime('%Y-%m-%d')}.db"
    assert today_name in remaining          # today's snapshot kept
    assert "spanish_bot-2026-05-08.db" in remaining   # newest of the pre-seeded kept
    assert "spanish_bot-2026-05-03.db" in remaining   # oldest survivor (05-01 and 05-02 deleted)


def test_backup_same_day_rerun_is_idempotent(tmp_path):
    src = tmp_path / "spanish_bot.db"
    _seed_db(src, 2)
    backups = tmp_path / "backups"
    # twice on the same day must succeed (VACUUM INTO refuses to overwrite)
    subprocess.run(["bash", str(SCRIPT), str(src), str(backups)], check=True)
    subprocess.run(["bash", str(SCRIPT), str(src), str(backups)], check=True)
    made = list(backups.glob("spanish_bot-*.db"))
    assert len(made) == 1  # one snapshot per day, overwritten cleanly


def test_backup_prefix_follows_db_filename(tmp_path):
    src = tmp_path / "english_bot.db"
    _seed_db(src, 2)
    backups = tmp_path / "backups"
    subprocess.run(["bash", str(SCRIPT), str(src), str(backups)], check=True)
    made = list(backups.glob("english_bot-*.db"))
    assert len(made) == 1


def test_two_bots_share_backup_dir_without_clobbering(tmp_path):
    es_src = tmp_path / "spanish_bot.db"
    en_src = tmp_path / "english_bot.db"
    _seed_db(es_src, 1)
    _seed_db(en_src, 2)
    backups = tmp_path / "backups"
    subprocess.run(["bash", str(SCRIPT), str(es_src), str(backups)], check=True)
    subprocess.run(["bash", str(SCRIPT), str(en_src), str(backups)], check=True)
    assert len(list(backups.glob("spanish_bot-*.db"))) == 1
    assert len(list(backups.glob("english_bot-*.db"))) == 1
    # ротация одного бота не съедает бэкапы другого
    for d in range(1, 9):
        (backups / f"english_bot-2026-05-0{d}.db").write_text("old")
    subprocess.run(["bash", str(SCRIPT), str(en_src), str(backups)], check=True)
    assert len(list(backups.glob("spanish_bot-*.db"))) == 1  # уцелел
    assert len(list(backups.glob("english_bot-*.db"))) == 7
