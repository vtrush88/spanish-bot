#!/usr/bin/env bash
# Consistent SQLite backup with 7-file rotation.
# Usage: backup-db.sh <db_path> <backup_dir>
set -euo pipefail

DB_PATH="${1:?usage: backup-db.sh <db_path> <backup_dir>}"
BACKUP_DIR="${2:?usage: backup-db.sh <db_path> <backup_dir>}"

mkdir -p "$BACKUP_DIR"
# Префикс бэкапа = имя файла БД: spanish_bot.db -> spanish_bot-YYYY-MM-DD.db,
# english_bot.db -> english_bot-YYYY-MM-DD.db. Два бота могут делить одну
# папку бэкапов: ротация каждого считает только свои файлы.
PREFIX="$(basename "$DB_PATH" .db)"
DEST="$BACKUP_DIR/${PREFIX}-$(date +%Y-%m-%d).db"

# VACUUM INTO is a consistent snapshot even while the bot is writing —
# never plain cp of a live SQLite file. It REFUSES to overwrite, so a
# second run on the same day would fail — drop today's file first to stay
# idempotent (one snapshot per day).
rm -f "$DEST"
sqlite3 "$DB_PATH" "VACUUM INTO '$DEST'"

# Keep the 7 newest by name (dated names sort chronologically); delete older.
# awk+while is portable across BSD (macOS) and GNU (Ubuntu) — no head -n -N / xargs -r.
ls -1 "$BACKUP_DIR/${PREFIX}"-*.db | sort -r | awk 'NR>7' | while read -r f; do
    rm -f "$f"
done
