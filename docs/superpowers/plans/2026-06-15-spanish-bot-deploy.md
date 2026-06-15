# Spanish Bot VPS Deploy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести бота на постоянный always-on хостинг на VPS (DigitalOcean): код из приватного GitHub-репо, запуск через systemd, ночной консистентный бэкап SQLite, без потери маминого словаря.

**Architecture:** Тот же `bot.py` (long-polling), но (1) путь к БД вынесен в `.env` (убирает класс ошибок «пишем не туда»), (2) добавлены два репо-артефакта — systemd-юнит и скрипт бэкапа, (3) написан пошаговый ран-бук провижининга. Код-артефакты пишутся TDD и коммитятся здесь; провижининг сервера — последняя задача, выполняется вживую по ран-буку.

**Tech Stack:** Python 3.12, aiogram, SQLite (`VACUUM INTO` для бэкапа), systemd, GitHub deploy key, DigitalOcean Ubuntu 24.04.

**Spec:** `docs/superpowers/specs/2026-06-15-spanish-bot-deploy-design.md`

---

## File Structure

- **Modify** `config.py` — добавить поле `db_path` в `Config`, читать `DB_PATH` из env (дефолт `spanish_bot.db`).
- **Modify** `bot.py` — убрать константу `DB_PATH`, брать путь из `cfg.db_path`.
- **Modify** `tests/test_config.py` — покрыть дефолт и явный `DB_PATH`.
- **Create** `scripts/backup-db.sh` — консистентный снапшот через `VACUUM INTO` + ротация (хранить 7), кросс-платформенно.
- **Create** `tests/test_backup_script.py` — прогон скрипта на временной БД: снапшот валиден и ротация работает.
- **Create** `spanish-bot.service` — шаблон systemd-юнита (в корне репо).
- **Create** `docs/superpowers/deploy.md` — пошаговый ран-бук провижининга.
- **Modify** `.env.example` — добавить `DB_PATH`.
- **Modify** `README.md` — заменить устаревший Railway/Fly-раздел ссылкой на ран-бук.
- **Modify** `AGENTS.md` — короткая ссылка на ран-бук в «Как запускать».

Задачи 1–2 — TDD-код. Задачи 3–5 — авторинг файлов (pytest неприменим; проверка — обзор/линт). Задача 6 — живой деплой по ран-буку.

---

### Task 1: Путь к БД через `.env` (хардненинг против «тихой пустой БД»)

**Files:**
- Modify: `config.py`
- Modify: `bot.py:14` (константа `DB_PATH`) и `bot.py:21` (вызов `db.connect`)
- Test: `tests/test_config.py`

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/test_config.py`:

```python
def test_load_defaults_db_path(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    monkeypatch.delenv("DB_PATH", raising=False)
    cfg = config.load()
    assert cfg.db_path == "spanish_bot.db"


def test_load_reads_db_path(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    monkeypatch.setenv("DB_PATH", "/var/lib/spanish-bot/spanish_bot.db")
    cfg = config.load()
    assert cfg.db_path == "/var/lib/spanish-bot/spanish_bot.db"
```

- [ ] **Step 2: Прогнать — убедиться, что падают**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: FAIL — `Config.__init__() ... unexpected keyword 'db_path'` или `AttributeError: 'Config' object has no attribute 'db_path'`.

- [ ] **Step 3: Реализовать в `config.py`**

Поле в dataclass и чтение в `load()`:

```python
@dataclass(frozen=True)
class Config:
    telegram_token: str
    anthropic_api_key: str
    allowed_user_ids: set[int]
    db_path: str


def load() -> Config:
    load_dotenv()
    raw_ids = _require("ALLOWED_USER_IDS")
    ids = {int(part.strip()) for part in raw_ids.split(",") if part.strip()}
    return Config(
        telegram_token=_require("TELEGRAM_TOKEN"),
        anthropic_api_key=_require("ANTHROPIC_API_KEY"),
        allowed_user_ids=ids,
        db_path=os.environ.get("DB_PATH", "spanish_bot.db"),
    )
```

- [ ] **Step 4: Подключить в `bot.py`**

Удалить строку `DB_PATH = "spanish_bot.db"` и использовать конфиг:

```python
async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cfg = config.load()

    conn = db.connect(cfg.db_path)
    db.init_db(conn)
```

- [ ] **Step 5: Прогнать тесты + смоук импортов**

Run: `.venv/bin/pytest -q && .venv/bin/python -c "import bot"`
Expected: PASS (67 passed) и `import bot` без ошибок.

- [ ] **Step 6: Коммит**

```bash
git add config.py bot.py tests/test_config.py
git commit -m "Make DB path configurable via DB_PATH env (deploy hardening)"
```

---

### Task 2: Скрипт бэкапа БД с ротацией

**Files:**
- Create: `scripts/backup-db.sh`
- Test: `tests/test_backup_script.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_backup_script.py`:

```python
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
        db.add_card(conn, user_id=1, kind="word", spanish=f"w{i}",
                    russian="x", transcription="x", example_es="x",
                    example_ru="x", enriched=True, today=date(2026, 6, 15))
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
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `.venv/bin/pytest tests/test_backup_script.py -q`
Expected: FAIL — скрипта нет (`bash: .../backup-db.sh: No such file or directory`, ненулевой код → `CalledProcessError`).

- [ ] **Step 3: Написать `scripts/backup-db.sh`**

```bash
#!/usr/bin/env bash
# Consistent SQLite backup with 7-file rotation.
# Usage: backup-db.sh <db_path> <backup_dir>
set -euo pipefail

DB_PATH="${1:?usage: backup-db.sh <db_path> <backup_dir>}"
BACKUP_DIR="${2:?usage: backup-db.sh <db_path> <backup_dir>}"

mkdir -p "$BACKUP_DIR"
DEST="$BACKUP_DIR/spanish_bot-$(date +%Y-%m-%d).db"

# VACUUM INTO is a consistent snapshot even while the bot is writing —
# never plain cp of a live SQLite file.
sqlite3 "$DB_PATH" "VACUUM INTO '$DEST'"

# Keep the 7 newest by name (dated names sort chronologically); delete older.
# awk+while is portable across BSD (macOS) and GNU (Ubuntu) — no head -n -N / xargs -r.
ls -1 "$BACKUP_DIR"/spanish_bot-*.db | sort -r | awk 'NR>7' | while read -r f; do
    rm -f "$f"
done
```

- [ ] **Step 4: Сделать исполняемым и прогнать тесты**

Run: `chmod +x scripts/backup-db.sh && .venv/bin/pytest tests/test_backup_script.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Прогнать весь набор**

Run: `.venv/bin/pytest -q`
Expected: PASS (69 passed).

- [ ] **Step 6: Коммит**

```bash
git add scripts/backup-db.sh tests/test_backup_script.py
git commit -m "Add SQLite backup script (VACUUM INTO + keep-7 rotation)"
```

---

### Task 3: systemd-юнит

**Files:**
- Create: `spanish-bot.service`

Юнит — шаблон с путями под пользователя `spanishbot`. pytest неприменим; реальная проверка — на сервере (Task 6). Здесь проверяем синтаксис обзором.

- [ ] **Step 1: Создать `spanish-bot.service`**

```ini
[Unit]
Description=Spanish Bot (Telegram, long-polling)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=spanishbot
WorkingDirectory=/home/spanishbot/spanish-bot
# .env читается самим кодом (config.load() -> load_dotenv()) из WorkingDirectory.
ExecStart=/home/spanishbot/spanish-bot/.venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Проверить, что это валидный ini и пути согласованы**

Run: `grep -E "ExecStart|WorkingDirectory|User" spanish-bot.service`
Expected: три строки; `WorkingDirectory` и префикс `ExecStart` совпадают (`/home/spanishbot/spanish-bot`), интерпретатор — `.venv/bin/python`. (Полная проверка `systemd-analyze verify` — на сервере в Task 6; на macOS systemd нет.)

- [ ] **Step 3: Коммит**

```bash
git add spanish-bot.service
git commit -m "Add systemd unit template for the bot service"
```

---

### Task 4: Ран-бук провижининга `docs/superpowers/deploy.md`

**Files:**
- Create: `docs/superpowers/deploy.md`

- [ ] **Step 1: Создать `docs/superpowers/deploy.md` со следующим содержимым**

````markdown
# Spanish Bot — Deploy Run-book (DigitalOcean)

Пошаговый провижининг с нуля. Значения в угловых скобках (`<DROPLET_IP>`,
`<MAC_REPO>`) подставляются по ходу. Дизайн: `specs/2026-06-15-spanish-bot-deploy-design.md`.

## 0. Предусловия (на маке)
- Аккаунт DigitalOcean и SSH-ключ для входа на дроплет (`~/.ssh/id_ed25519`).
- Локальный репо: `<MAC_REPO>` = `Projects/Spanish Bot/app`.
- Рабочий `.env` и `spanish_bot.db` в `<MAC_REPO>`.

## 1. Приватный GitHub-репозиторий
```bash
cd "<MAC_REPO>"
# через gh (если установлен) — создаёт приватный репо и добавляет remote:
gh repo create spanish-bot --private --source=. --remote=origin --push
# либо вручную: создать приватный репо на github.com, затем:
#   git remote add origin git@github.com:<USER>/spanish-bot.git && git push -u origin main
```
Проверка: `git remote -v` показывает `origin`, на GitHub виден `main`.

## 2. Дроплет
- DigitalOcean → Create Droplet: Ubuntu 24.04 LTS, Basic, самый дешёвый
  (512 MiB $4/mo или 1 GiB $6/mo), регион Frankfurt/Amsterdam, аутентификация — твой SSH-ключ.
- Запиши `<DROPLET_IP>`.
```bash
ssh root@<DROPLET_IP>          # первый вход
```

## 3. Пользователь, пакеты, firewall (на сервере, под root)
```bash
adduser --disabled-password --gecos "" spanishbot
apt update && apt install -y python3.12 python3.12-venv git sqlite3
ufw allow OpenSSH && ufw --force enable
```

## 4. Deploy key — доступ сервера к приватному репо (read-only)
```bash
su - spanishbot
ssh-keygen -t ed25519 -f ~/.ssh/spanish_bot_deploy -N ""
cat ~/.ssh/spanish_bot_deploy.pub        # скопировать вывод
```
На GitHub: репо → Settings → Deploy keys → Add deploy key → вставить ключ,
**не** включать «Allow write access». Затем на сервере направить git на этот ключ:
```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
    IdentityFile ~/.ssh/spanish_bot_deploy
    IdentitiesOnly yes
EOF
ssh -T git@github.com    # ожидается "Hi <USER>/spanish-bot! You've successfully authenticated"
```

## 5. Клонирование и окружение (под spanishbot)
```bash
cd ~
git clone git@github.com:<USER>/spanish-bot.git
cd spanish-bot
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 6. Секреты и стартовая БД (с мака, в новом терминале)
Остановить локального бота, чтобы БД не писалась при копировании:
```bash
pkill -f "MacOS/Python bot.py"   # на маке
```
Скопировать `.env` и БД на сервер:
```bash
cd "<MAC_REPO>"
scp .env spanishbot@<DROPLET_IP>:/home/spanishbot/spanish-bot/.env
scp spanish_bot.db spanishbot@<DROPLET_IP>:/home/spanishbot/spanish-bot/spanish_bot.db
```
На сервере выставить права/владельца и абсолютный путь к БД:
```bash
chmod 600 ~/spanish-bot/.env
chown spanishbot:spanishbot ~/spanish-bot/.env ~/spanish-bot/spanish_bot.db
echo "DB_PATH=/home/spanishbot/spanish-bot/spanish_bot.db" >> ~/spanish-bot/.env
```

## 7. СВЕРКА МИГРАЦИИ (до запуска сервиса!)
```bash
# на сервере:
sqlite3 ~/spanish-bot/spanish_bot.db "SELECT COUNT(*) FROM cards;"
# на маке:
sqlite3 "<MAC_REPO>/spanish_bot.db" "SELECT COUNT(*) FROM cards;"
```
Числа ДОЛЖНЫ совпасть. Если на сервере 0 — БД не доехала/не читается; НЕ запускать
сервис (иначе init_db создаст пустую базу), разобраться с путём/правами и повторить.

## 8. systemd-сервис (на сервере, под root)
```bash
cp /home/spanishbot/spanish-bot/spanish-bot.service /etc/systemd/system/
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/spanish-bot.service   # синтаксис/пути
systemctl enable --now spanish-bot
systemctl status spanish-bot          # active (running)
journalctl -u spanish-bot -n 20       # "Start polling", без TelegramConflictError
```
⚠️ Локальный бот на маке с этого момента запускать НЕЛЬЗЯ (один поллер на токен).

## 9. Ночной бэкап (cron, под spanishbot)
```bash
crontab -e
# добавить строку (бэкап в 03:30 каждый день):
30 3 * * * /home/spanishbot/spanish-bot/scripts/backup-db.sh /home/spanishbot/spanish-bot/spanish_bot.db /home/spanishbot/backups >> /home/spanishbot/backup.log 2>&1
```
Проверить разово:
```bash
~/spanish-bot/scripts/backup-db.sh ~/spanish-bot/spanish_bot.db ~/backups
ls -1 ~/backups        # появился spanish_bot-<сегодня>.db
```

## 10. Проверка устойчивости
```bash
sudo reboot
# через минуту:
ssh spanishbot@<DROPLET_IP> 'systemctl is-active spanish-bot'   # active
```
Живой тест в Telegram: `/start`, «Мой словарь» (старые слова на месте), добавить
слово, тренировка, аудио.

## Рутина обновлений
```bash
# на маке
git push
# на сервере
cd ~/spanish-bot && git pull
.venv/bin/pip install -r requirements.txt   # только если менялся requirements.txt
sudo systemctl restart spanish-bot
journalctl -u spanish-bot -n 20
```
````

- [ ] **Step 2: Коммит**

```bash
git add docs/superpowers/deploy.md
git commit -m "Add step-by-step VPS deploy run-book"
```

---

### Task 5: Документация — `.env.example`, README, AGENTS.md

**Files:**
- Modify: `.env.example`
- Modify: `README.md` (раздел «Деплой», сейчас Railway/Fly)
- Modify: `AGENTS.md` (раздел «Как запускать»)

- [ ] **Step 1: Добавить `DB_PATH` в `.env.example`**

Дописать строку:

```
DB_PATH=spanish_bot.db
```

- [ ] **Step 2: Заменить раздел «Деплой» в `README.md`**

Заменить блок:

```markdown
## Деплой

Управляемый хост (Railway / Fly.io): задеплоить процесс `python bot.py`,
проставить переменные окружения, том для `spanish_bot.db`.
```

на:

```markdown
## Деплой

VPS (DigitalOcean) + systemd. Пошаговый ран-бук:
[`docs/superpowers/deploy.md`](docs/superpowers/deploy.md). Дизайн:
`docs/superpowers/specs/2026-06-15-spanish-bot-deploy-design.md`.
```

- [ ] **Step 3: Добавить ссылку в `AGENTS.md`**

В разделе «## Как запускать», после строки про `.gitignore`, добавить:

```markdown

**Деплой на сервер:** пошаговый ран-бук — `docs/superpowers/deploy.md`
(VPS/DigitalOcean + systemd + ночной бэкап). На сервере бот запущен один —
локально с тем же токеном не поднимать (TelegramConflictError).
```

- [ ] **Step 4: Проверить отсутствие устаревших упоминаний**

Run: `grep -rin "railway\|fly.io" README.md AGENTS.md`
Expected: пусто (нет вывода).

- [ ] **Step 5: Коммит**

```bash
git add .env.example README.md AGENTS.md
git commit -m "Docs: point deploy at the VPS run-book; add DB_PATH to env example"
```

---

### Task 6: Живой провижининг по ран-буку

**Files:** none (выполнение на сервере; правок в репо нет).

Это ручной деплой — выполняется вживую вместе с Victoria по `docs/superpowers/deploy.md`.
Требует её действий в веб-панели DigitalOcean и GitHub (создание дроплета, добавление
deploy key) и доступа к секретам — Claude не вставляет токены в чат, `.env` копирует сама
Victoria или Claude по её команде, без печати значений.

- [ ] **Step 1:** Пройти ран-бук разделы 1–6 (репо, дроплет, пользователь, deploy key, клон, секреты+БД).
- [ ] **Step 2:** Раздел 7 — сверка `SELECT COUNT(*) FROM cards` сервер == мак. Не идти дальше, пока не совпало.
- [ ] **Step 3:** Раздел 8 — `systemctl enable --now`, `systemd-analyze verify` чистый, статус `active`, в логах `Start polling` без конфликта. Погасить локального бота навсегда.
- [ ] **Step 4:** Раздел 9 — cron-бэкап, разовый прогон даёт файл в `~/backups`.
- [ ] **Step 5:** Раздел 10 — `reboot`, бот сам поднялся; живой тест в Telegram (старые слова на месте, добавление/тренировка/аудио работают).
- [ ] **Step 6:** Обновить статус в `AGENTS.md` (бэклог: «постоянный хостинг» → сделано) и в ваултовой overview-заметке; закоммитить.

---

## Notes for the implementer

- Задачи 1–5 — обычный repo-флоу (TDD где есть код, мелкие коммиты), модель не важна.
- Задача 6 НЕ автономна: это совместная сессия с Victoria, с доступом к внешним
  сервисам и секретам. Не выполнять её как фоновую/субагентную — только интерактивно.
- Один поллер на токен: пока на сервере бот жив, локально с боевым токеном не стартовать.
  Для локальной отладки — отдельный тестовый токен от @BotFather.
