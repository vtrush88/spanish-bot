# Spanish Bot MVP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Telegram-бот — персональный тренажёр испанского для мамы: она добавляет слова/фразы, бот обогащает их (перевод, произношение аудио + русская транскрипция, пример) через Claude и тренирует тремя режимами (карточки с интервальным повторением, проверка перевода, аудирование).

**Architecture:** Один Python-процесс на `aiogram` (long-polling) + SQLite. Тонкие хендлеры зовут сервисы; вся логика — в `services/`, `db.py`, презентация — в `formatting.py`. Чистая логика (`srs`, `config`, парсинг ответов Claude, форматирование) покрыта юнит-тестами без живого Telegram и без реальных вызовов API. Хендлеры верифицируются ручным запуском.

**Tech Stack:** Python 3.11+, aiogram 3.x, anthropic SDK (модель `claude-haiku-4-5`), edge-tts, sqlite3 (stdlib), python-dotenv, pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-06-02-spanish-bot-design.md`

---

## File Structure

| Файл | Ответственность |
|---|---|
| `requirements.txt` | зависимости (runtime + dev) |
| `pytest.ini` | конфиг pytest (asyncio mode) |
| `config.py` | чтение env: `TELEGRAM_TOKEN`, `ANTHROPIC_API_KEY`, `ALLOWED_USER_IDS` |
| `db.py` | SQLite: схема, CRUD карточек, выборка «к повторению» |
| `services/srs.py` | чистая логика интервального повторения |
| `services/enrichment.py` | Claude: слово/фраза → перевод/транскрипция/пример |
| `services/grading.py` | Claude: проверка маминого перевода |
| `services/tts.py` | edge-tts: испанский текст → ogg-файл |
| `formatting.py` | чистые функции форматирования сообщений |
| `keyboards.py` | reply- и inline-клавиатуры |
| `states.py` | FSM-состояния (add / training) |
| `handlers/menu.py` | `/start`, главное меню, «Мой словарь» |
| `handlers/add.py` | добавление слова/фразы |
| `handlers/training.py` | три режима тренировки |
| `bot.py` | точка входа: Dispatcher, фильтр доступа, регистрация роутеров, polling |
| `tests/` | юнит-тесты |

Каждый `handlers/` и `services/` — пакет с `__init__.py`. Тесты и бот запускаются из корня репо (top-level модули импортируются напрямую: `import db`, `from services import srs`).

---

## Task 1: Scaffolding и smoke-тест

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `services/__init__.py`, `handlers/__init__.py`, `tests/__init__.py`, `tests/test_smoke.py`

- [ ] **Step 1: Создать `requirements.txt`**

```
aiogram==3.13.1
anthropic==0.39.0
edge-tts==6.1.12
python-dotenv==1.0.1
pytest==8.3.3
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Создать `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 3: Создать пустые `__init__.py`**

Создать пустыми: `services/__init__.py`, `handlers/__init__.py`, `tests/__init__.py`.

- [ ] **Step 4: Написать smoke-тест `tests/test_smoke.py`**

```python
def test_python_imports_work():
    import sqlite3
    import asyncio  # noqa: F401
    assert sqlite3.sqlite_version_info >= (3, 0, 0)
```

- [ ] **Step 5: Установить зависимости и прогнать**

Run:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```
Expected: `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt pytest.ini services/ handlers/ tests/
git commit -m "chore: project scaffolding (deps, pytest, package layout)"
```

---

## Task 2: `config.py`

**Files:**
- Create: `config.py`, `tests/test_config.py`

- [ ] **Step 1: Написать падающий тест `tests/test_config.py`**

```python
import config


def test_load_parses_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok123")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key456")
    monkeypatch.setenv("ALLOWED_USER_IDS", "111, 222 ,333")
    cfg = config.load()
    assert cfg.telegram_token == "tok123"
    assert cfg.anthropic_api_key == "key456"
    assert cfg.allowed_user_ids == {111, 222, 333}


def test_missing_required_raises(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    import pytest
    with pytest.raises(ValueError, match="TELEGRAM_TOKEN"):
        config.load()
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `pytest tests/test_config.py -v`
Expected: FAIL (`AttributeError: module 'config' has no attribute 'load'`).

- [ ] **Step 3: Реализовать `config.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    telegram_token: str
    anthropic_api_key: str
    allowed_user_ids: set[int]


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Missing required env var: {name}")
    return value


def load() -> Config:
    load_dotenv()
    raw_ids = _require("ALLOWED_USER_IDS")
    ids = {int(part.strip()) for part in raw_ids.split(",") if part.strip()}
    return Config(
        telegram_token=_require("TELEGRAM_TOKEN"),
        anthropic_api_key=_require("ANTHROPIC_API_KEY"),
        allowed_user_ids=ids,
    )
```

- [ ] **Step 4: Прогнать — убедиться, что проходит**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: config loader with env parsing and validation"
```

---

## Task 3: `services/srs.py` (чистая логика повторения)

**Files:**
- Create: `services/srs.py`, `tests/test_srs.py`

- [ ] **Step 1: Написать падающий тест `tests/test_srs.py`**

```python
from datetime import date

from services import srs


def test_new_card_remembered_goes_to_first_rung():
    assert srs.next_interval(0, remembered=True) == 1


def test_remembered_climbs_ladder():
    assert srs.next_interval(1, remembered=True) == 3
    assert srs.next_interval(3, remembered=True) == 7
    assert srs.next_interval(7, remembered=True) == 14
    assert srs.next_interval(14, remembered=True) == 30
    assert srs.next_interval(30, remembered=True) == 60


def test_remembered_caps_at_max():
    assert srs.next_interval(60, remembered=True) == 60


def test_not_remembered_resets_to_one():
    assert srs.next_interval(30, remembered=False) == 1
    assert srs.next_interval(0, remembered=False) == 1


def test_due_on_adds_interval_days():
    assert srs.due_on(date(2026, 6, 3), 7) == date(2026, 6, 10)
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `pytest tests/test_srs.py -v`
Expected: FAIL (`ModuleNotFoundError`/`AttributeError`).

- [ ] **Step 3: Реализовать `services/srs.py`**

```python
from __future__ import annotations

from datetime import date, timedelta

LADDER = [1, 3, 7, 14, 30, 60]


def next_interval(current: int, remembered: bool) -> int:
    """Leitner ladder. Remembered → next rung > current (capped). Forgot → reset to 1."""
    if not remembered:
        return LADDER[0]
    for rung in LADDER:
        if rung > current:
            return rung
    return LADDER[-1]


def due_on(today: date, interval_days: int) -> date:
    return today + timedelta(days=interval_days)
```

- [ ] **Step 4: Прогнать — убедиться, что проходит**

Run: `pytest tests/test_srs.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add services/srs.py tests/test_srs.py
git commit -m "feat: SRS Leitner ladder (pure logic)"
```

---

## Task 4: `db.py` — схема, добавление, чтение карточки

**Files:**
- Create: `db.py`, `tests/conftest.py`, `tests/test_db_basic.py`

- [ ] **Step 1: Создать фикстуру `tests/conftest.py`**

```python
import pytest

import db as db_module


@pytest.fixture()
def conn():
    c = db_module.connect(":memory:")
    db_module.init_db(c)
    yield c
    c.close()
```

- [ ] **Step 2: Написать падающий тест `tests/test_db_basic.py`**

```python
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
```

- [ ] **Step 3: Прогнать — убедиться, что падает**

Run: `pytest tests/test_db_basic.py -v`
Expected: FAIL (`AttributeError: module 'db' has no attribute 'connect'`).

- [ ] **Step 4: Реализовать `db.py` (часть 1)**

```python
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
```

- [ ] **Step 5: Прогнать — убедиться, что проходит**

Run: `pytest tests/test_db_basic.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add db.py tests/conftest.py tests/test_db_basic.py
git commit -m "feat: db schema, add_card, get_card"
```

---

## Task 5: `db.py` — повторение, выборка, список, удаление, обновления

**Files:**
- Modify: `db.py`
- Create: `tests/test_db_review.py`

- [ ] **Step 1: Написать падающий тест `tests/test_db_review.py`**

```python
from datetime import date

import db


def _add(conn, spanish, russian, today, enriched=True):
    return db.add_card(
        conn, user_id=111, kind="word", spanish=spanish, russian=russian,
        transcription="x", example_es="e", example_ru="э",
        enriched=enriched, today=today,
    )


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
    db.delete_card(conn, cid)
    assert db.count_cards(conn, 111) == 1


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
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `pytest tests/test_db_review.py -v`
Expected: FAIL (`AttributeError: ... 'update_review'`).

- [ ] **Step 3: Дописать функции в `db.py`**

```python
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
```

- [ ] **Step 4: Прогнать — убедиться, что проходит**

Run: `pytest tests/test_db_review.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db_review.py
git commit -m "feat: db review update, due selection, list/delete, enrichment update"
```

---

## Task 6: `services/enrichment.py`

**Files:**
- Create: `services/enrichment.py`, `tests/test_enrichment.py`

Обогащение через Claude tool use (форсированный структурированный вывод). Функция принимает уже созданный `anthropic.Anthropic` клиент — в тестах он мокается, реальные вызовы не идут.

- [ ] **Step 1: Написать падающий тест `tests/test_enrichment.py`**

```python
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services import enrichment


def _resp(input_dict):
    block = SimpleNamespace(type="tool_use", name="save_card", input=input_dict)
    return SimpleNamespace(content=[block])


GOOD = {
    "kind": "word",
    "spanish": "comida",
    "russian": "еда",
    "transcription": "комИда",
    "example_es": "La comida está lista.",
    "example_ru": "Еда готова.",
}


def test_enrich_returns_clean_dict():
    client = MagicMock()
    client.messages.create.return_value = _resp(GOOD)
    result = enrichment.enrich(client, "comida")
    assert result == GOOD
    assert client.messages.create.call_count == 1


def test_enrich_retries_once_then_succeeds():
    client = MagicMock()
    bad = SimpleNamespace(content=[SimpleNamespace(type="text", text="oops")])
    client.messages.create.side_effect = [bad, _resp(GOOD)]
    result = enrichment.enrich(client, "comida")
    assert result["spanish"] == "comida"
    assert client.messages.create.call_count == 2


def test_enrich_raises_after_two_bad_responses():
    client = MagicMock()
    bad = SimpleNamespace(content=[SimpleNamespace(type="text", text="oops")])
    client.messages.create.side_effect = [bad, bad]
    with pytest.raises(enrichment.EnrichmentError):
        enrichment.enrich(client, "comida")
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `pytest tests/test_enrichment.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реализовать `services/enrichment.py`**

```python
from __future__ import annotations

MODEL = "claude-haiku-4-5"

REQUIRED_KEYS = (
    "kind", "spanish", "russian", "transcription", "example_es", "example_ru",
)

SYSTEM = (
    "Ты помогаешь русскоязычному новичку учить испанский. "
    "На вход даётся слово или фраза на испанском ИЛИ на русском. "
    "Определи язык. Верни испанский вариант (spanish), его русский перевод "
    "(russian), произношение русскими буквами с ударением (transcription, "
    "напр. 'комИда'), и короткий пример-предложение на испанском (example_es) "
    "с переводом (example_ru). Поле kind = 'word' для одного слова, 'phrase' "
    "для фразы/предложения. Всё кратко и для начинающего."
)

TOOL = {
    "name": "save_card",
    "description": "Сохранить обогащённую карточку для изучения.",
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["word", "phrase"]},
            "spanish": {"type": "string"},
            "russian": {"type": "string"},
            "transcription": {"type": "string"},
            "example_es": {"type": "string"},
            "example_ru": {"type": "string"},
        },
        "required": list(REQUIRED_KEYS),
    },
}


class EnrichmentError(Exception):
    pass


def _extract(response) -> dict | None:
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "save_card":
            data = block.input
            if all(k in data and data[k] for k in REQUIRED_KEYS):
                return {k: data[k] for k in REQUIRED_KEYS}
    return None


def enrich(client, text: str) -> dict:
    last_error = None
    for _ in range(2):
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=[{"type": "text", "text": SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "save_card"},
            messages=[{"role": "user", "content": text}],
        )
        result = _extract(response)
        if result is not None:
            return result
        last_error = "Claude вернул ответ без валидного tool_use save_card"
    raise EnrichmentError(last_error or "enrichment failed")
```

- [ ] **Step 4: Прогнать — убедиться, что проходит**

Run: `pytest tests/test_enrichment.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add services/enrichment.py tests/test_enrichment.py
git commit -m "feat: Claude enrichment service (forced tool use + retry)"
```

---

## Task 7: `services/grading.py`

**Files:**
- Create: `services/grading.py`, `tests/test_grading.py`

- [ ] **Step 1: Написать падающий тест `tests/test_grading.py`**

```python
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services import grading


def _resp(input_dict):
    block = SimpleNamespace(type="tool_use", name="save_grade", input=input_dict)
    return SimpleNamespace(content=[block])


def test_grade_returns_verdict():
    client = MagicMock()
    client.messages.create.return_value = _resp(
        {"verdict": "typo", "correct_spanish": "comida",
         "note": "маленькая опечатка"}
    )
    result = grading.grade(client, prompt_ru="еда",
                           expected_es="comida", answer="komida")
    assert result["verdict"] == "typo"
    assert result["correct_spanish"] == "comida"


def test_grade_raises_on_bad_response():
    client = MagicMock()
    bad = SimpleNamespace(content=[SimpleNamespace(type="text", text="x")])
    client.messages.create.side_effect = [bad, bad]
    with pytest.raises(grading.GradingError):
        grading.grade(client, prompt_ru="еда",
                      expected_es="comida", answer="komida")
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `pytest tests/test_grading.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реализовать `services/grading.py`**

```python
from __future__ import annotations

MODEL = "claude-haiku-4-5"
REQUIRED_KEYS = ("verdict", "correct_spanish", "note")

SYSTEM = (
    "Ты мягко проверяешь, как русскоязычный новичок перевёл слово/фразу на "
    "испанский. Тебе дают: русский запрос, ожидаемый испанский перевод и ответ "
    "ученика. Оцени verdict: 'correct' (всё верно), 'typo' (правильно по сути, "
    "но мелкая опечатка/регистр/акцент), 'wrong' (неверно). В correct_spanish "
    "дай правильное написание. В note — короткое доброе пояснение по-русски."
)

TOOL = {
    "name": "save_grade",
    "description": "Сохранить оценку перевода.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string",
                        "enum": ["correct", "typo", "wrong"]},
            "correct_spanish": {"type": "string"},
            "note": {"type": "string"},
        },
        "required": list(REQUIRED_KEYS),
    },
}


class GradingError(Exception):
    pass


def _extract(response) -> dict | None:
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "save_grade":
            data = block.input
            if all(k in data and data[k] for k in REQUIRED_KEYS):
                return {k: data[k] for k in REQUIRED_KEYS}
    return None


def grade(client, *, prompt_ru: str, expected_es: str, answer: str) -> dict:
    user = (
        f"Русский запрос: {prompt_ru}\n"
        f"Ожидаемый испанский: {expected_es}\n"
        f"Ответ ученика: {answer}"
    )
    last_error = None
    for _ in range(2):
        response = client.messages.create(
            model=MODEL,
            max_tokens=256,
            system=[{"type": "text", "text": SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "save_grade"},
            messages=[{"role": "user", "content": user}],
        )
        result = _extract(response)
        if result is not None:
            return result
        last_error = "Claude вернул ответ без валидного tool_use save_grade"
    raise GradingError(last_error or "grading failed")
```

- [ ] **Step 4: Прогнать — убедиться, что проходит**

Run: `pytest tests/test_grading.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add services/grading.py tests/test_grading.py
git commit -m "feat: Claude grading service for translation checks"
```

---

## Task 8: `services/tts.py`

**Files:**
- Create: `services/tts.py`, `tests/test_tts.py`

edge-tts асинхронно генерирует ogg-озвучку. В юнит-тесте мокаем `edge_tts.Communicate`, чтобы не ходить в сеть.

- [ ] **Step 1: Написать падающий тест `tests/test_tts.py`**

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import tts


@pytest.mark.asyncio
async def test_synthesize_calls_edge_and_returns_path(tmp_path):
    out = tmp_path / "hola.ogg"
    fake_comm = MagicMock()
    fake_comm.save = AsyncMock()
    with patch("services.tts.edge_tts.Communicate", return_value=fake_comm) as ctor:
        result = await tts.synthesize("hola", str(out))
    ctor.assert_called_once()
    fake_comm.save.assert_awaited_once_with(str(out))
    assert result == str(out)


@pytest.mark.asyncio
async def test_synthesize_wraps_errors():
    fake_comm = MagicMock()
    fake_comm.save = AsyncMock(side_effect=RuntimeError("network"))
    with patch("services.tts.edge_tts.Communicate", return_value=fake_comm):
        with pytest.raises(tts.TTSError):
            await tts.synthesize("hola", "/tmp/x.ogg")
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `pytest tests/test_tts.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реализовать `services/tts.py`**

```python
from __future__ import annotations

import edge_tts

VOICE = "es-ES-ElviraNeural"


class TTSError(Exception):
    pass


async def synthesize(text: str, out_path: str) -> str:
    """Сгенерировать испанскую озвучку в ogg-файл. Возвращает путь."""
    try:
        comm = edge_tts.Communicate(text, VOICE)
        await comm.save(out_path)
    except Exception as exc:  # noqa: BLE001 - graceful degradation by design
        raise TTSError(str(exc)) from exc
    return out_path
```

- [ ] **Step 4: Прогнать — убедиться, что проходит**

Run: `pytest tests/test_tts.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add services/tts.py tests/test_tts.py
git commit -m "feat: edge-tts Spanish voice synthesis with error wrapping"
```

---

## Task 9: `formatting.py` (чистые функции сообщений)

**Files:**
- Create: `formatting.py`, `tests/test_formatting.py`

- [ ] **Step 1: Написать падающий тест `tests/test_formatting.py`**

```python
import formatting


def test_card_preview_includes_all_fields():
    text = formatting.card_preview({
        "spanish": "comida", "russian": "еда", "transcription": "комИда",
        "example_es": "La comida está lista.", "example_ru": "Еда готова.",
    })
    assert "comida" in text
    assert "еда" in text
    assert "комИда" in text
    assert "La comida está lista." in text


def test_answer_reveal():
    text = formatting.answer_reveal({"russian": "еда", "transcription": "комИда"})
    assert "еда" in text and "комИда" in text


def test_word_list_line_numbered():
    line = formatting.word_list_line(3, {"spanish": "agua", "russian": "вода"})
    assert line.startswith("3.")
    assert "agua" in line and "вода" in line
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `pytest tests/test_formatting.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реализовать `formatting.py`**

```python
from __future__ import annotations


def card_preview(card: dict) -> str:
    return (
        f"🔤 {card['spanish']}\n"
        f"🇷🇺 {card['russian']}\n"
        f"🗣 произношение: {card['transcription']}\n"
        f"📝 пример: {card['example_es']} — {card['example_ru']}"
    )


def answer_reveal(card: dict) -> str:
    return f"🇷🇺 {card['russian']}  ·  {card['transcription']}"


def word_list_line(number: int, card: dict) -> str:
    return f"{number}. {card['spanish']} — {card['russian']}"
```

- [ ] **Step 4: Прогнать — убедиться, что проходит**

Run: `pytest tests/test_formatting.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add formatting.py tests/test_formatting.py
git commit -m "feat: pure message formatting helpers"
```

---

## Task 10: `keyboards.py` и `states.py`

**Files:**
- Create: `keyboards.py`, `states.py`, `tests/test_keyboards.py`

- [ ] **Step 1: Написать падающий тест `tests/test_keyboards.py`**

```python
import keyboards


def test_main_menu_has_all_buttons():
    kb = keyboards.main_menu()
    labels = {btn.text for row in kb.keyboard for btn in row}
    assert keyboards.BTN_ADD in labels
    assert keyboards.BTN_FLASHCARDS in labels
    assert keyboards.BTN_TRANSLATE in labels
    assert keyboards.BTN_LISTEN in labels
    assert keyboards.BTN_VOCAB in labels


def test_reveal_keyboard_has_callback_data():
    kb = keyboards.reveal_keyboard()
    datas = {btn.callback_data for row in kb.inline_keyboard for btn in row}
    assert "show_answer" in datas


def test_grade_keyboard_has_remember_and_forgot():
    kb = keyboards.grade_keyboard()
    datas = {btn.callback_data for row in kb.inline_keyboard for btn in row}
    assert "grade:remember" in datas
    assert "grade:forgot" in datas
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `pytest tests/test_keyboards.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реализовать `keyboards.py`**

```python
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

BTN_ADD = "➕ Добавить слово"
BTN_FLASHCARDS = "🎴 Карточки"
BTN_TRANSLATE = "✍️ Проверить себя"
BTN_LISTEN = "🎧 Аудирование"
BTN_VOCAB = "📖 Мой словарь"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ADD)],
            [KeyboardButton(text=BTN_FLASHCARDS), KeyboardButton(text=BTN_TRANSLATE)],
            [KeyboardButton(text=BTN_LISTEN), KeyboardButton(text=BTN_VOCAB)],
        ],
        resize_keyboard=True,
    )


def reveal_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👁 Показать ответ", callback_data="show_answer")
    ]])


def grade_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Помню", callback_data="grade:remember"),
        InlineKeyboardButton(text="🔁 Не помню", callback_data="grade:forgot"),
    ]])


def save_card_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да", callback_data="save:yes"),
        InlineKeyboardButton(text="✏️ Исправить перевод", callback_data="save:edit"),
        InlineKeyboardButton(text="❌ Нет", callback_data="save:no"),
    ]])
```

- [ ] **Step 4: Реализовать `states.py`**

```python
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AddCard(StatesGroup):
    waiting_for_text = State()
    waiting_for_correction = State()


class Training(StatesGroup):
    flashcards = State()
    translate = State()
    listen = State()
```

- [ ] **Step 5: Прогнать — убедиться, что проходит**

Run: `pytest tests/test_keyboards.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add keyboards.py states.py tests/test_keyboards.py
git commit -m "feat: keyboards and FSM states"
```

---

## Task 11: `bot.py` — каркас, фильтр доступа, /start, запуск

**Files:**
- Create: `bot.py`, `handlers/menu.py`
- Create: `.env.example`

На этом шаге бот уже запускается и отвечает на `/start` главным меню. Остальные хендлеры подключим в следующих задачах.

- [ ] **Step 1: Создать `.env.example`**

```
TELEGRAM_TOKEN=put-bot-token-here
ANTHROPIC_API_KEY=put-anthropic-key-here
ALLOWED_USER_IDS=123456789
```

- [ ] **Step 2: Реализовать `handlers/menu.py`**

```python
from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

import keyboards

router = Router()

GREETING = (
    "¡Hola! 🌞 Я помогу учить испанский.\n\n"
    "• «➕ Добавить слово» — пришли слово или фразу, я переведу, озвучу и "
    "запомню.\n"
    "• «🎴 Карточки», «✍️ Проверить себя», «🎧 Аудирование» — тренировки.\n"
    "• «📖 Мой словарь» — все добавленные слова."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(GREETING, reply_markup=keyboards.main_menu())
```

- [ ] **Step 3: Реализовать `bot.py`**

```python
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.fsm.storage.memory import MemoryStorage
from anthropic import Anthropic

import config
import db
from handlers import menu

DB_PATH = "spanish_bot.db"


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cfg = config.load()

    conn = db.connect(DB_PATH)
    db.init_db(conn)
    anthropic_client = Anthropic(api_key=cfg.anthropic_api_key)

    bot = Bot(token=cfg.telegram_token)
    dp = Dispatcher(storage=MemoryStorage())

    # Inject shared deps into every handler via the data dict.
    dp["conn"] = conn
    dp["anthropic"] = anthropic_client

    # Access control: ignore anyone not in the allow-list.
    dp.message.filter(F.from_user.id.in_(cfg.allowed_user_ids))
    dp.callback_query.filter(F.from_user.id.in_(cfg.allowed_user_ids))

    dp.include_router(menu.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Прогнать весь тест-сьют (регрессия)**

Run: `pytest -q`
Expected: все предыдущие тесты PASS.

- [ ] **Step 5: Ручная проверка запуска**

Создать `.env` из `.env.example` (реальный токен от @BotFather и ключ Anthropic, свой Telegram user_id в `ALLOWED_USER_IDS`). Запустить:
```bash
source .venv/bin/activate
python bot.py
```
В Telegram открыть бота, отправить `/start`. Expected: приветствие + клавиатура с 5 кнопками. Нажатия на кнопки пока ничего не делают — это нормально.

- [ ] **Step 6: Commit**

```bash
git add bot.py handlers/menu.py .env.example
git commit -m "feat: bot entry point, access filter, /start menu"
```

---

## Task 12: `handlers/add.py` — добавление слова/фразы

**Files:**
- Create: `handlers/add.py`
- Modify: `bot.py` (подключить router)

Поток: кнопка «➕ Добавить слово» → бот просит текст → мама пишет → enrichment → превью карточки + озвучка + inline-кнопки [Да / Исправить / Нет] → сохранение. При ошибке enrichment — предложить сохранить «как есть» (`enriched=false`). При ошибке TTS — сохранить без голосового.

- [ ] **Step 1: Реализовать `handlers/add.py`**

```python
from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from anthropic import Anthropic

import db
import formatting
import keyboards
from services import enrichment, tts
from states import AddCard

router = Router()


@router.message(F.text == keyboards.BTN_ADD)
async def start_add(message: Message, state: FSMContext) -> None:
    await state.set_state(AddCard.waiting_for_text)
    await message.answer("Напиши слово или фразу — на испанском или русском 🙂")


@router.message(AddCard.waiting_for_text, F.text)
async def receive_text(
    message: Message, state: FSMContext, anthropic: Anthropic
) -> None:
    text = message.text.strip()
    try:
        card = enrichment.enrich(anthropic, text)
    except enrichment.EnrichmentError:
        # Stay in waiting_for_text; next message retries. Save-as-is +
        # later re-enrichment is deferred (see out-of-MVP improvements).
        await message.answer(
            "Не получилось обработать сейчас 😕 Попробуй ещё раз через минутку "
            "или пришли другое слово."
        )
        return

    await state.update_data(card=card)
    await message.answer(formatting.card_preview(card))
    await _send_voice(message, card["spanish"])
    await message.answer("Сохранить?", reply_markup=keyboards.save_card_keyboard())


async def _send_voice(message: Message, spanish: str) -> None:
    """Best-effort voice; silent text-only fallback on TTS failure."""
    tmp = os.path.join(tempfile.gettempdir(), f"tts_{abs(hash(spanish))}.ogg")
    try:
        await tts.synthesize(spanish, tmp)
        with open(tmp, "rb") as fh:
            await message.answer_voice(
                BufferedInputFile(fh.read(), filename="word.ogg")
            )
    except (tts.TTSError, OSError):
        await message.answer("🔇 (озвучка временно недоступна)")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


@router.callback_query(F.data == "save:yes")
async def save_yes(
    call: CallbackQuery, state: FSMContext, conn: sqlite3.Connection
) -> None:
    data = await state.get_data()
    card = data["card"]
    db.add_card(
        conn, user_id=call.from_user.id, kind=card["kind"],
        spanish=card["spanish"], russian=card["russian"],
        transcription=card["transcription"], example_es=card["example_es"],
        example_ru=card["example_ru"], enriched=True, today=date.today(),
    )
    await state.clear()
    await call.message.answer("Сохранил! ✅")
    await call.answer()


@router.callback_query(F.data == "save:edit")
async def save_edit(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddCard.waiting_for_correction)
    await call.message.answer("Напиши свой перевод:")
    await call.answer()


@router.message(AddCard.waiting_for_correction, F.text)
async def receive_correction(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    data = await state.get_data()
    card = dict(data["card"])
    card["russian"] = message.text.strip()
    db.add_card(
        conn, user_id=message.from_user.id, kind=card["kind"],
        spanish=card["spanish"], russian=card["russian"],
        transcription=card["transcription"], example_es=card["example_es"],
        example_ru=card["example_ru"], enriched=True, today=date.today(),
    )
    await state.clear()
    await message.answer("Сохранил с твоим переводом! ✅")


@router.callback_query(F.data == "save:no")
async def save_no(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.answer("Ок, не сохраняю.")
    await call.answer()


@router.message(AddCard.waiting_for_text)
async def reject_non_text(message: Message) -> None:
    await message.answer("Я понимаю пока только текст 🙂 Напиши слово или фразу.")
```

- [ ] **Step 2: Подключить router в `bot.py`**

Modify `bot.py` — добавить импорт и include после `menu`:

```python
from handlers import add, menu
```
и
```python
    dp.include_router(menu.router)
    dp.include_router(add.router)
```

- [ ] **Step 3: Регрессия тестов**

Run: `pytest -q`
Expected: все PASS (новых юнит-тестов нет — хендлер тонкий, проверяется вручную).

- [ ] **Step 4: Ручная проверка**

`python bot.py`, в Telegram: «➕ Добавить слово» → отправить `comida`. Expected: превью (перевод, транскрипция, пример) + голосовое + кнопки. Нажать «✅ Да» → «Сохранил!». Проверить запись:
```bash
sqlite3 spanish_bot.db "SELECT spanish, russian, transcription FROM cards;"
```
Expected: строка с `comida | еда | ...`.

- [ ] **Step 5: Commit**

```bash
git add handlers/add.py bot.py
git commit -m "feat: add-card flow (enrich, preview, voice, save/edit)"
```

---

## Task 13: `handlers/training.py` — карточки

**Files:**
- Create: `handlers/training.py`
- Modify: `bot.py` (подключить router)

Очередь карточек «к повторению» храним в FSM-данных как список id. Показываем по одной: испанское + озвучка → «Показать ответ» → перевод → «Помню/Не помню» → обновляем SRS → следующая.

- [ ] **Step 1: Реализовать `handlers/training.py` (режим карточек)**

```python
from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

import db
import formatting
import keyboards
from services import srs, tts
from states import Training

router = Router()
EMPTY = ("На сегодня всё повторили! 🎉 Можешь добавить новые слова "
         "или зайти позже.")


async def _send_voice(message: Message, conn: sqlite3.Connection, card) -> None:
    """Send cached voice by file_id, else synthesize and cache the file_id."""
    if card["audio_file_id"]:
        await message.answer_voice(card["audio_file_id"])
        return
    tmp = os.path.join(tempfile.gettempdir(), f"tts_{card['id']}.ogg")
    try:
        await tts.synthesize(card["spanish"], tmp)
        with open(tmp, "rb") as fh:
            sent = await message.answer_voice(
                BufferedInputFile(fh.read(), filename="word.ogg")
            )
        db.set_audio_file_id(conn, card["id"], sent.voice.file_id)
    except (tts.TTSError, OSError):
        pass  # text card already shown; audio is best-effort
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


async def _show_next_flashcard(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    data = await state.get_data()
    queue = data.get("queue", [])
    if not queue:
        await state.clear()
        await message.answer("Готово на сегодня! 👏", reply_markup=keyboards.main_menu())
        return
    card_id = queue[0]
    card = db.get_card(conn, card_id)
    await message.answer(f"🎴 {card['spanish']}")
    await _send_voice(message, conn, card)
    await message.answer("…вспомни перевод…",
                         reply_markup=keyboards.reveal_keyboard())


@router.message(F.text == keyboards.BTN_FLASHCARDS)
async def start_flashcards(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    due = db.get_due_cards(conn, message.from_user.id, date.today())
    if not due:
        await message.answer(EMPTY)
        return
    await state.set_state(Training.flashcards)
    await state.update_data(queue=[r["id"] for r in due])
    await _show_next_flashcard(message, state, conn)


@router.callback_query(Training.flashcards, F.data == "show_answer")
async def reveal(call: CallbackQuery, state: FSMContext,
                 conn: sqlite3.Connection) -> None:
    data = await state.get_data()
    card = db.get_card(conn, data["queue"][0])
    await call.message.answer(formatting.answer_reveal(card),
                              reply_markup=keyboards.grade_keyboard())
    await call.answer()


@router.callback_query(Training.flashcards, F.data.startswith("grade:"))
async def grade_flashcard(call: CallbackQuery, state: FSMContext,
                          conn: sqlite3.Connection) -> None:
    remembered = call.data == "grade:remember"
    data = await state.get_data()
    queue = data["queue"]
    card = db.get_card(conn, queue[0])
    new_interval = srs.next_interval(card["interval_days"], remembered)
    db.update_review(conn, card["id"], interval_days=new_interval,
                     due_at=srs.due_on(date.today(), new_interval),
                     remembered=remembered)
    await state.update_data(queue=queue[1:])
    await call.answer("👍" if remembered else "Повторим ещё")
    await _show_next_flashcard(call.message, state, conn)
```

- [ ] **Step 2: Подключить router в `bot.py`**

```python
from handlers import add, menu, training
```
и
```python
    dp.include_router(training.router)
```

- [ ] **Step 3: Регрессия тестов**

Run: `pytest -q`
Expected: все PASS.

- [ ] **Step 4: Ручная проверка**

Добавить 2-3 слова (Task 12), затем «🎴 Карточки». Expected: показ слова + озвучка → «Показать ответ» → перевод + «Помню/Не помню» → следующая, пока очередь не пуста → «Готово на сегодня!». Проверить, что у карточки вырос `interval_days`:
```bash
sqlite3 spanish_bot.db "SELECT spanish, interval_days, reps, due_at FROM cards;"
```

- [ ] **Step 5: Commit**

```bash
git add handlers/training.py bot.py
git commit -m "feat: flashcards training mode with SRS + audio caching"
```

---

## Task 14: `handlers/training.py` — проверка перевода

**Files:**
- Modify: `handlers/training.py`

- [ ] **Step 1: Дописать режим перевода в `handlers/training.py`**

Добавить импорт `grading` к существующим импортам сервисов:
```python
from services import grading, srs, tts
```
И добавить в конец файла:
```python
async def _ask_next_translation(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    data = await state.get_data()
    queue = data.get("queue", [])
    if not queue:
        await state.clear()
        await message.answer("Готово на сегодня! 👏",
                             reply_markup=keyboards.main_menu())
        return
    card = db.get_card(conn, queue[0])
    await message.answer(f"Как по-испански: «{card['russian']}»?")


@router.message(F.text == keyboards.BTN_TRANSLATE)
async def start_translate(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    due = db.get_due_cards(conn, message.from_user.id, date.today())
    if not due:
        await message.answer(EMPTY)
        return
    await state.set_state(Training.translate)
    await state.update_data(queue=[r["id"] for r in due])
    await _ask_next_translation(message, state, conn)


@router.message(Training.translate, F.text)
async def check_translation(
    message: Message, state: FSMContext, conn: sqlite3.Connection, anthropic
) -> None:
    data = await state.get_data()
    queue = data["queue"]
    card = db.get_card(conn, queue[0])
    try:
        verdict = grading.grade(
            anthropic, prompt_ru=card["russian"],
            expected_es=card["spanish"], answer=message.text.strip(),
        )
        ok = verdict["verdict"] in ("correct", "typo")
        if verdict["verdict"] == "correct":
            await message.answer(f"✅ Верно! {verdict['note']}")
        elif verdict["verdict"] == "typo":
            await message.answer(
                f"✅ Почти! Правильно: {verdict['correct_spanish']} "
                f"({verdict['note']})"
            )
        else:
            await message.answer(
                f"❌ Не совсем. Правильно: {verdict['correct_spanish']} "
                f"({verdict['note']})"
            )
    except grading.GradingError:
        # Fall back to a forgiving exact-match check if Claude is unavailable.
        ok = message.text.strip().lower() == card["spanish"].lower()
        await message.answer("✅ Верно!" if ok
                             else f"❌ Правильно: {card['spanish']}")

    new_interval = srs.next_interval(card["interval_days"], ok)
    db.update_review(conn, card["id"], interval_days=new_interval,
                     due_at=srs.due_on(date.today(), new_interval),
                     remembered=ok)
    await state.update_data(queue=queue[1:])
    await _ask_next_translation(message, state, conn)
```

- [ ] **Step 2: Регрессия тестов**

Run: `pytest -q`
Expected: все PASS.

- [ ] **Step 3: Ручная проверка**

«✍️ Проверить себя» → бот спрашивает «Как по-испански: «еда»?» → ответить `komida` → Expected: «✅ Почти! Правильно: comida (опечатка)». Ответить неверно → «❌ Не совсем…». Очередь идёт до конца.

- [ ] **Step 4: Commit**

```bash
git add handlers/training.py
git commit -m "feat: translation-check mode with Claude grading + fallback"
```

---

## Task 15: `handlers/training.py` — аудирование

**Files:**
- Modify: `handlers/training.py`

- [ ] **Step 1: Дописать режим аудирования в `handlers/training.py`**

Добавить в конец файла:
```python
async def _ask_next_listen(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    data = await state.get_data()
    queue = data.get("queue", [])
    if not queue:
        await state.clear()
        await message.answer("Готово на сегодня! 👏",
                             reply_markup=keyboards.main_menu())
        return
    card = db.get_card(conn, queue[0])
    await message.answer("🔊 Что это за слово? Напиши, что услышала:")
    await _send_voice(message, conn, card)


@router.message(F.text == keyboards.BTN_LISTEN)
async def start_listen(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    due = db.get_due_cards(conn, message.from_user.id, date.today())
    if not due:
        await message.answer(EMPTY)
        return
    await state.set_state(Training.listen)
    await state.update_data(queue=[r["id"] for r in due])
    await _ask_next_listen(message, state, conn)


@router.message(Training.listen, F.text)
async def check_listen(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    data = await state.get_data()
    queue = data["queue"]
    card = db.get_card(conn, queue[0])
    ok = message.text.strip().lower() == card["spanish"].lower()
    if ok:
        await message.answer(f"✅ Да! 🔤 {card['spanish']} — {card['russian']}")
    else:
        await message.answer(
            f"Услышалось: {card['spanish']} — {card['russian']}"
        )
    new_interval = srs.next_interval(card["interval_days"], ok)
    db.update_review(conn, card["id"], interval_days=new_interval,
                     due_at=srs.due_on(date.today(), new_interval),
                     remembered=ok)
    await state.update_data(queue=queue[1:])
    await _ask_next_listen(message, state, conn)
```

- [ ] **Step 2: Регрессия тестов**

Run: `pytest -q`
Expected: все PASS.

- [ ] **Step 3: Ручная проверка**

«🎧 Аудирование» → бот шлёт голосовое → ответить тем, что услышала. Верно → «✅ Да!»; неверно → показывает правильное. Проверить, что `audio_file_id` закэшировался после первого показа:
```bash
sqlite3 spanish_bot.db "SELECT spanish, audio_file_id FROM cards WHERE audio_file_id IS NOT NULL;"
```

- [ ] **Step 4: Commit**

```bash
git add handlers/training.py
git commit -m "feat: listening training mode"
```

---

## Task 16: «Мой словарь» — список и удаление

**Files:**
- Modify: `handlers/menu.py`, `keyboards.py`

Простая пагинация по 10 слов с кнопками ◀/▶ и удалением по номеру через inline-кнопки.

- [ ] **Step 1: Добавить клавиатуру словаря в `keyboards.py`**

```python
PAGE_SIZE = 10


def vocab_keyboard(cards: list, page: int, total: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=f"🗑 {i + 1 + page * PAGE_SIZE}",
        callback_data=f"del:{c['id']}",
    )] for i, c in enumerate(cards)]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=f"vocab:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="▶", callback_data=f"vocab:{page + 1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

- [ ] **Step 2: Добавить хендлеры словаря в `handlers/menu.py`**

Заменить импорты в начале файла на:
```python
import sqlite3

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

import db
import formatting
import keyboards
```
Добавить в конец файла:
```python
def _render_page(conn: sqlite3.Connection, user_id: int, page: int):
    total = db.count_cards(conn, user_id)
    cards = db.list_cards(conn, user_id, limit=keyboards.PAGE_SIZE,
                          offset=page * keyboards.PAGE_SIZE)
    if not cards:
        return "Словарь пуст. Добавь первое слово через «➕ Добавить слово».", None
    lines = [formatting.word_list_line(i + 1 + page * keyboards.PAGE_SIZE, c)
             for i, c in enumerate(cards)]
    text = "📖 Твой словарь:\n\n" + "\n".join(lines)
    return text, keyboards.vocab_keyboard(cards, page, total)


@router.message(F.text == keyboards.BTN_VOCAB)
async def show_vocab(message: Message, conn: sqlite3.Connection) -> None:
    text, kb = _render_page(conn, message.from_user.id, 0)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("vocab:"))
async def paginate_vocab(call: CallbackQuery, conn: sqlite3.Connection) -> None:
    page = int(call.data.split(":")[1])
    text, kb = _render_page(conn, call.from_user.id, page)
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("del:"))
async def delete_word(call: CallbackQuery, conn: sqlite3.Connection) -> None:
    card_id = int(call.data.split(":")[1])
    db.delete_card(conn, card_id)
    text, kb = _render_page(conn, call.from_user.id, 0)
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer("Удалено")
```

- [ ] **Step 3: Регрессия тестов**

Run: `pytest -q`
Expected: все PASS.

- [ ] **Step 4: Ручная проверка**

«📖 Мой словарь» → список с номерами и кнопками удаления; ◀/▶ если >10 слов; нажать 🗑 → слово исчезает из списка и из БД.

- [ ] **Step 5: Commit**

```bash
git add handlers/menu.py keyboards.py
git commit -m "feat: vocabulary list with pagination and delete"
```

---

## Task 17: README и финальная проверка

**Files:**
- Create: `README.md`

- [ ] **Step 1: Написать `README.md`**

```markdown
# Spanish Bot

Персональный телеграм-тренажёр испанского. Полное описание для агентов — в
[AGENTS.md](AGENTS.md); дизайн — в `docs/superpowers/specs/`.

## Запуск локально

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. Скопировать `.env.example` → `.env`, заполнить:
   - `TELEGRAM_TOKEN` — от @BotFather
   - `ANTHROPIC_API_KEY` — ключ Anthropic
   - `ALLOWED_USER_IDS` — Telegram user_id (через запятую)
4. `python bot.py`

## Тесты

`pytest -q`

## Деплой

Управляемый хост (Railway / Fly.io): задеплоить процесс `python bot.py`,
проставить переменные окружения, том для `spanish_bot.db`.
```

- [ ] **Step 2: Финальный прогон всех тестов**

Run: `pytest -q`
Expected: все PASS (config, srs, db ×2, enrichment, grading, tts, formatting, keyboards, smoke).

- [ ] **Step 3: Полная ручная проверка end-to-end**

Пройти все 5 кнопок подряд: добавить слово → карточки → проверить себя → аудирование → словарь. Убедиться, что чужой аккаунт (не из `ALLOWED_USER_IDS`) бот игнорирует.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README with setup, test, and deploy instructions"
```

---

## Открытые улучшения (вне MVP)

Реализовать только по запросу, в отдельных планах:
- Дообогащение карточек с `enriched=false` (фоновая до-генерация перевода).
- Пуш-напоминания раз в день (планировщик).
- Статистика прогресса (`review_log`).
- Распознавание речи мамы (мама произносит — бот проверяет).
- Переезд хранилища с локального файла на постоянный том при деплое.
```
