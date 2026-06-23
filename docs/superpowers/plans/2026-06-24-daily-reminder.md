# Daily Review Reminder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Once a day, at a configured time, the bot messages each non-excluded user how many words are due for review today — silent when nothing is due.

**Architecture:** A new `reminders.py` module (pure scheduling/text functions + an async sender + an async loop), started as a background `asyncio` task from `bot.py` and gated by config. No new dependency: timing uses stdlib `zoneinfo`. The loop sleeps until the next fire time, computes each user's due count via the existing `db.get_due_cards`, and sends a Telegram message to those with ≥1 due.

**Tech Stack:** Python 3.12 · aiogram 3.13.1 (long-polling, MemoryStorage FSM) · SQLite (stdlib) · stdlib `zoneinfo`. Bot is live on a VPS under systemd. Spec: `docs/superpowers/specs/2026-06-23-daily-reminder-design.md`.

## Global Constraints

- **No new dependency.** Use stdlib `zoneinfo` (Python 3.12). Do not add APScheduler or any package.
- **Absolute-time sleep delay.** The sleep must be `target.timestamp() - now.timestamp()`, NOT `(target - now).total_seconds()`: CPython subtracts two same-`tzinfo` aware datetimes by wall clock (skips UTC conversion), so that delta is off by ±1h on a DST-transition day (verified: 86400 s vs the real 82800 s). `next_fire` must build the target as a fresh aware datetime for the calendar day, never `now + timedelta`.
- **`REMINDER_AT` gates the feature and the other vars.** Absent → loop never starts, and `REMINDER_TZ` / `REMINDER_EXCLUDE_IDS` are not read or validated (a typo there must never crash a disabled feature). Present but malformed → `ValueError` at startup. Daytime value expected (see spec Date basis).
- **HTML parse mode.** The bot has no default parse mode; the reminder's bold must be sent with `parse_mode="HTML"` and `<b>…</b>`, else the tags show literally.
- **Gender-neutral copy only** (one male user among the users): no gendered or first-person past-tense bot phrasing.
- **Regression gate:** `.venv/bin/pytest -q` stays green after every task; also `.venv/bin/python -c "import bot"` for import breakage. Baseline is **81 passed**; new tests bring it to **94** (5 config + 2 text + 3 scheduling + 3 send).
- **Frequent commits:** one commit per task. Commit with `--no-gpg-sign` (non-interactive commits on this mac otherwise fail GPG signing).
- **Do NOT restart the live bot until the final task.** Single poller per token; restart is deliberate.
- **Router/startup order in `bot.py` unchanged** except the additions in Task 5.

---

### Task 1: Reminder configuration (`config.py`)

Add three gated config fields and document them in `.env.example`. `REMINDER_AT` is the on/off switch; the other two are parsed only when it is set. This is pure parsing logic the repo already unit-tests (`tests/test_config.py`), so it is done test-first.

**Files:**
- Modify: `config.py` (imports, `Config` dataclass, `load()`, add `_parse_hhmm`)
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config.reminder_at: datetime.time | None`, `Config.reminder_tz: str | None`, `Config.reminder_exclude_ids: set[int]` — consumed by Tasks 4 and 5.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def _base_env(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "111,222")


def test_reminder_off_by_default(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.delenv("REMINDER_AT", raising=False)
    cfg = config.load()
    assert cfg.reminder_at is None
    assert cfg.reminder_tz is None
    assert cfg.reminder_exclude_ids == set()


def test_reminder_parsed_when_set(monkeypatch):
    from datetime import time
    _base_env(monkeypatch)
    monkeypatch.setenv("REMINDER_AT", "10:00")
    monkeypatch.setenv("REMINDER_TZ", "Europe/Madrid")
    monkeypatch.setenv("REMINDER_EXCLUDE_IDS", "222")
    cfg = config.load()
    assert cfg.reminder_at == time(10, 0)
    assert cfg.reminder_tz == "Europe/Madrid"
    assert cfg.reminder_exclude_ids == {222}


def test_reminder_default_tz_when_at_set(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("REMINDER_AT", "9:30")
    monkeypatch.delenv("REMINDER_TZ", raising=False)
    cfg = config.load()
    assert cfg.reminder_tz == "Europe/Madrid"


def test_reminder_malformed_at_raises(monkeypatch):
    import pytest
    _base_env(monkeypatch)
    monkeypatch.setenv("REMINDER_AT", "25:99")
    with pytest.raises(ValueError, match="REMINDER_AT"):
        config.load()


def test_reminder_off_ignores_bad_tz(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.delenv("REMINDER_AT", raising=False)
    monkeypatch.setenv("REMINDER_TZ", "Bogus/Zone")  # must NOT be read/validated
    cfg = config.load()
    assert cfg.reminder_at is None
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: FAIL — `Config` has no `reminder_at` (`TypeError`/`AttributeError`).

- [ ] **Step 3: Add imports and the parse helper to `config.py`**

At the top, alongside the existing imports:

```python
from datetime import time
from zoneinfo import ZoneInfo
```

Above `load()` (after `_require`):

```python
def _parse_hhmm(raw: str) -> time:
    parts = raw.split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise ValueError(f"REMINDER_AT must be HH:MM, got: {raw!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"REMINDER_AT out of range: {raw!r}")
    return time(hour, minute)
```

- [ ] **Step 4: Add the dataclass fields**

```python
@dataclass(frozen=True)
class Config:
    telegram_token: str
    anthropic_api_key: str
    allowed_user_ids: set[int]
    db_path: str
    reminder_at: time | None
    reminder_tz: str | None
    reminder_exclude_ids: set[int]
```

- [ ] **Step 5: Parse the gated vars in `load()`**

Inside `load()`, after `ids = {...}` and before `return Config(...)`:

```python
    reminder_at: time | None = None
    reminder_tz: str | None = None
    reminder_exclude_ids: set[int] = set()
    raw_at = os.environ.get("REMINDER_AT", "").strip()
    if raw_at:
        reminder_at = _parse_hhmm(raw_at)
        reminder_tz = (os.environ.get("REMINDER_TZ", "").strip()
                       or "Europe/Madrid")
        ZoneInfo(reminder_tz)  # validate IANA name (raises if unknown)
        raw_excl = os.environ.get("REMINDER_EXCLUDE_IDS", "")
        reminder_exclude_ids = {
            int(p.strip()) for p in raw_excl.split(",") if p.strip()
        }
```

And extend the `return Config(...)` call with:

```python
        reminder_at=reminder_at,
        reminder_tz=reminder_tz,
        reminder_exclude_ids=reminder_exclude_ids,
```

- [ ] **Step 6: Document the vars in `.env.example`**

Append:

```
# Daily review reminder (optional). Unset => feature off.
# REMINDER_AT is also the on/off switch; the other two are read only when it is set.
# REMINDER_AT=10:00
# REMINDER_TZ=Europe/Madrid
# REMINDER_EXCLUDE_IDS=
```

- [ ] **Step 7: Run tests + import check**

Run: `.venv/bin/pytest tests/test_config.py -q && .venv/bin/python -c "import bot"`
Expected: PASS (5 new config tests green), import clean.

- [ ] **Step 8: Commit**

```bash
git add config.py .env.example tests/test_config.py
git commit --no-gpg-sign -m "feat(config): gated REMINDER_AT/TZ/EXCLUDE_IDS for daily reminder"
```

---

### Task 2: Reminder text + pluralization (`reminders.py`)

Create the module with its two pure text functions. Spec Wording section.

**Files:**
- Create: `reminders.py`
- Test: `tests/test_reminders.py`

**Interfaces:**
- Produces: `plural_words(n: int) -> str`, `reminder_text(count: int) -> str` (HTML) — consumed by Task 4.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reminders.py`:

```python
import reminders


def test_plural_words():
    assert reminders.plural_words(1) == "слово"
    assert reminders.plural_words(2) == "слова"
    assert reminders.plural_words(4) == "слова"
    assert reminders.plural_words(5) == "слов"
    assert reminders.plural_words(11) == "слов"
    assert reminders.plural_words(14) == "слов"
    assert reminders.plural_words(21) == "слово"
    assert reminders.plural_words(22) == "слова"
    assert reminders.plural_words(111) == "слов"


def test_reminder_text_has_count_and_html_bold():
    assert "<b>1 слово</b>" in reminders.reminder_text(1)
    assert "<b>5 слов</b>" in reminders.reminder_text(5)
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `.venv/bin/pytest tests/test_reminders.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'reminders'`.

- [ ] **Step 3: Create `reminders.py` with the two functions**

```python
from __future__ import annotations


def plural_words(n: int) -> str:
    """Russian plural of «слово»: 1→слово, 2-4→слова, else слов."""
    if 11 <= n % 100 <= 14:
        return "слов"
    last = n % 10
    if last == 1:
        return "слово"
    if 2 <= last <= 4:
        return "слова"
    return "слов"


def reminder_text(count: int) -> str:
    """HTML body of the daily reminder (sent with parse_mode='HTML')."""
    return (
        f"🔔 Сегодня на повторение: <b>{count} {plural_words(count)}</b>. "
        "Загляни в «🎴 Карточки», когда будет минутка 🙂"
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `.venv/bin/pytest tests/test_reminders.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add reminders.py tests/test_reminders.py
git commit --no-gpg-sign -m "feat(reminders): plural_words + reminder_text (HTML)"
```

---

### Task 3: Scheduling — `next_fire` + `seconds_until` (`reminders.py`)

The two pure timing functions. This is where the DST trap lives (Global Constraints).

**Files:**
- Modify: `reminders.py` (add import + two functions)
- Test: `tests/test_reminders.py`

**Interfaces:**
- Produces: `next_fire(now: datetime, hour: int, minute: int) -> datetime`, `seconds_until(now: datetime, target: datetime) -> float` — consumed by Task 5.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_reminders.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

MAD = ZoneInfo("Europe/Madrid")


def test_next_fire_today_when_target_ahead():
    now = datetime(2026, 6, 1, 9, 0, tzinfo=MAD)
    assert reminders.next_fire(now, 10, 0) == datetime(2026, 6, 1, 10, 0, tzinfo=MAD)


def test_next_fire_tomorrow_when_target_passed():
    now = datetime(2026, 6, 1, 11, 0, tzinfo=MAD)
    assert reminders.next_fire(now, 10, 0) == datetime(2026, 6, 2, 10, 0, tzinfo=MAD)


def test_seconds_until_absolute_across_spring_forward():
    # Madrid springs forward Sun 2026-03-29 (02:00 CET -> 03:00 CEST): a 23h day.
    now = datetime(2026, 3, 28, 10, 0, tzinfo=MAD)
    fire = reminders.next_fire(now, 10, 0)            # -> 2026-03-29 10:00 CEST
    assert fire == datetime(2026, 3, 29, 10, 0, tzinfo=MAD)
    assert reminders.seconds_until(now, fire) == 23 * 3600   # 82800, not 86400
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `.venv/bin/pytest tests/test_reminders.py -q`
Expected: FAIL — `next_fire`/`seconds_until` not defined (`AttributeError`).

- [ ] **Step 3: Add the import**

At the top of `reminders.py`, below `from __future__ import annotations`:

```python
from datetime import datetime, timedelta
```

- [ ] **Step 4: Add the two functions**

```python
def next_fire(now: datetime, hour: int, minute: int) -> datetime:
    """Next aware datetime at hour:minute in now's timezone: today if still
    ahead, else tomorrow. Built fresh for the calendar day (never
    `now + timedelta`) so the wall-clock construction resolves DST."""
    tz = now.tzinfo
    target = datetime(now.year, now.month, now.day, hour, minute, tzinfo=tz)
    if target <= now:
        d = now.date() + timedelta(days=1)
        target = datetime(d.year, d.month, d.day, hour, minute, tzinfo=tz)
    return target


def seconds_until(now: datetime, target: datetime) -> float:
    """Absolute elapsed seconds between two aware datetimes. Uses .timestamp()
    on purpose: subtracting two same-tzinfo datetimes is a WALL-CLOCK delta in
    CPython (no UTC conversion) — wrong by ±1h on a DST-transition day."""
    return target.timestamp() - now.timestamp()
```

- [ ] **Step 5: Run tests to confirm they pass**

Run: `.venv/bin/pytest tests/test_reminders.py -q`
Expected: PASS (now 5 tests in the file).

- [ ] **Step 6: Commit**

```bash
git add reminders.py tests/test_reminders.py
git commit --no-gpg-sign -m "feat(reminders): next_fire + seconds_until (DST-safe absolute delay)"
```

---

### Task 4: `send_daily_reminders` (`reminders.py`)

The async batch sender. Silent on 0 due; one user's failure does not abort the batch.

**Files:**
- Modify: `reminders.py` (add imports + function)
- Test: `tests/test_reminders.py`

**Interfaces:**
- Consumes: `reminder_text` (Task 2); `db.get_due_cards(conn, user_id, today)` (existing); `set[int]` user/exclude ids (Task 1).
- Produces: `async send_daily_reminders(bot, conn, user_ids, exclude_ids, today) -> None` — consumed by Task 5.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_reminders.py`:

```python
from datetime import date

import db
from aiogram.exceptions import TelegramForbiddenError


class _FakeBot:
    def __init__(self, fail_for=(), crash_for=()):
        self.sent = []
        self._fail_for = set(fail_for)      # raise an expected aiogram error
        self._crash_for = set(crash_for)    # raise an unexpected generic error

    async def send_message(self, chat_id, text, parse_mode=None):
        if chat_id in self._fail_for:
            raise TelegramForbiddenError(method=None, message="blocked")
        if chat_id in self._crash_for:
            raise RuntimeError("network blip")
        self.sent.append((chat_id, text, parse_mode))


def _seed_due(conn, user_id, spanish):
    db.add_card(conn, user_id=user_id, kind="word", spanish=spanish,
                russian="x", transcription="x", example_es=None,
                example_ru=None, enriched=True, today=date(2026, 1, 1))


async def test_send_only_due_nonexcluded_users(conn):
    _seed_due(conn, 111, "hola")        # due -> should get a message
    _seed_due(conn, 333, "sol")         # due but excluded
    # user 222 has no cards
    bot = _FakeBot()
    await reminders.send_daily_reminders(
        bot, conn, user_ids={111, 222, 333}, exclude_ids={333},
        today=date(2026, 6, 1))
    assert [s[0] for s in bot.sent] == [111]
    assert bot.sent[0][2] == "HTML"
    assert "<b>1 слово</b>" in bot.sent[0][1]


async def test_send_expected_failure_does_not_stop_others(conn):
    _seed_due(conn, 111, "uno")
    _seed_due(conn, 222, "dos")
    bot = _FakeBot(fail_for={111})        # TelegramForbiddenError -> specific catch
    await reminders.send_daily_reminders(
        bot, conn, user_ids={111, 222}, exclude_ids=set(),
        today=date(2026, 6, 1))
    assert [s[0] for s in bot.sent] == [222]


async def test_send_unexpected_error_does_not_stop_others(conn):
    _seed_due(conn, 111, "uno")
    _seed_due(conn, 222, "dos")
    bot = _FakeBot(crash_for={111})       # RuntimeError -> broad catch
    await reminders.send_daily_reminders(
        bot, conn, user_ids={111, 222}, exclude_ids=set(),
        today=date(2026, 6, 1))
    assert [s[0] for s in bot.sent] == [222]
```

(`conn` is the in-memory fixture from `tests/conftest.py`; `asyncio_mode = auto` runs the async tests with no marker.)

- [ ] **Step 2: Run them to confirm they fail**

Run: `.venv/bin/pytest tests/test_reminders.py -q`
Expected: FAIL — `send_daily_reminders` not defined.

- [ ] **Step 3: Add imports to `reminders.py`**

Extend the top imports:

```python
import logging
import sqlite3
from datetime import date, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import db
```

(Replace the existing `from datetime import datetime, timedelta` line with the `date,`-inclusive one above.)

- [ ] **Step 4: Add the function**

```python
async def send_daily_reminders(
    bot: Bot,
    conn: sqlite3.Connection,
    user_ids: set[int],
    exclude_ids: set[int],
    today: date,
) -> None:
    """Message each non-excluded user their due-count; silent on 0 due.
    ANY single send failure is logged and skipped so the rest of the batch
    still goes out — blocked/never-started users (expected) get a clean warning;
    anything else (network/server/retry-after/bug) gets a full traceback.
    `CancelledError` is `BaseException`, so it still propagates (clean shutdown)."""
    for uid in user_ids - exclude_ids:
        count = len(db.get_due_cards(conn, uid, today))
        if count <= 0:
            continue
        try:
            await bot.send_message(uid, reminder_text(count), parse_mode="HTML")
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            logging.warning("reminder: skip user %s (%s)", uid, exc)
        except Exception:  # noqa: BLE001 — one user must never abort the batch
            logging.exception("reminder: unexpected send error for user %s", uid)
```

- [ ] **Step 5: Run tests to confirm they pass**

Run: `.venv/bin/pytest tests/test_reminders.py -q`
Expected: PASS (now 8 tests in the file).

- [ ] **Step 6: Full suite + import check**

Run: `.venv/bin/pytest -q && .venv/bin/python -c "import bot"`
Expected: green (94 passed), import clean.

- [ ] **Step 7: Commit**

```bash
git add reminders.py tests/test_reminders.py
git commit --no-gpg-sign -m "feat(reminders): send_daily_reminders (silent on 0, fault-tolerant per user)"
```

---

### Task 5: `reminder_loop` + wiring into `bot.py`

The long-lived loop and its startup/shutdown. Not unit-tested (timers) — gated by import check and the Task 6 manual pass.

**Files:**
- Modify: `reminders.py` (add `asyncio`/`zoneinfo` imports + `reminder_loop`)
- Modify: `bot.py` (import + task lifecycle)

**Interfaces:**
- Consumes: `next_fire`, `seconds_until`, `send_daily_reminders` (Tasks 3–4); `Config.reminder_*` (Task 1).
- Produces: `async reminder_loop(bot, conn, cfg) -> None`; a background task started in `main()`.

- [ ] **Step 1: Add imports to `reminders.py`**

Add `import asyncio` and `from zoneinfo import ZoneInfo` to the existing imports — do NOT drop the aiogram/`db` lines added in Task 4. The complete import block becomes:

```python
from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import db
```

- [ ] **Step 2: Add `reminder_loop`** (at the end of `reminders.py`)

```python
async def reminder_loop(bot: Bot, conn: sqlite3.Connection, cfg) -> None:
    """Sleep until the next REMINDER_AT in REMINDER_TZ, send the batch, repeat
    daily. `today` is the server date (matches the training handlers — see spec
    Date basis). A failed fire is logged and swallowed so the loop survives."""
    tz = ZoneInfo(cfg.reminder_tz)
    while True:
        now = datetime.now(tz)
        target = next_fire(now, cfg.reminder_at.hour, cfg.reminder_at.minute)
        await asyncio.sleep(seconds_until(now, target))
        try:
            await send_daily_reminders(
                bot, conn, cfg.allowed_user_ids,
                cfg.reminder_exclude_ids, date.today(),
            )
        except Exception:  # noqa: BLE001 — loop must survive any per-fire error
            logging.exception("reminder: daily send failed")
```

- [ ] **Step 3: Wire it into `bot.py`**

Add `import reminders` to the imports. Replace the tail of `main()` (from `await bot.delete_webhook(...)` onward):

```python
    await bot.delete_webhook(drop_pending_updates=True)

    reminder_task = None
    if cfg.reminder_at is not None:
        reminder_task = asyncio.create_task(
            reminders.reminder_loop(bot, conn, cfg)
        )
    try:
        await dp.start_polling(bot)
    finally:
        if reminder_task is not None:
            reminder_task.cancel()
            await asyncio.gather(reminder_task, return_exceptions=True)
```

- [ ] **Step 4: Suite + import check**

Run: `.venv/bin/pytest -q && .venv/bin/python -c "import bot"`
Expected: green (94 passed — no new tests this task), import clean.

- [ ] **Step 5: Commit**

```bash
git add reminders.py bot.py
git commit --no-gpg-sign -m "feat(reminders): daily reminder_loop + bot.py startup/shutdown wiring"
```

---

### Task 6: Deploy, manual verification, doc reconciliation

The human-in-the-loop gate (substitutes for handler/loop unit tests) plus the deploy and the spec's required reversal of the "no push" decision. **Needs Victoria** for the desired send time, the exclude id, and the Telegram check.

**Files:** `AGENTS.md`, `docs/superpowers/specs/2026-06-02-spanish-bot-design.md` (the "no push" line), the vault tracker — reconciliation only.

- [ ] **Step 1: Confirm the suite is green**

Run: `.venv/bin/pytest -q`
Expected: 94 passed.

- [ ] **Step 2: Push and deploy** (per `docs/superpowers/deploy.md` update routine)

```bash
git push
ssh spanishbot@164.92.182.195 'cd ~/spanish-bot && git pull --ff-only && git log --oneline -1'
```

- [ ] **Step 3: Enable the feature on the server** (ask Victoria for the time + her exclude id)

The server `.env` has no `REMINDER_*` yet → feature is off. Append the three vars (use `printf`/`>>`, **not** a heredoc — heredocs corrupt files over SSH, see project notes). Example with a ~2-minutes-ahead time for the live test:

```bash
ssh spanishbot@164.92.182.195
# on the server, in ~/spanish-bot:
printf 'REMINDER_AT=%s\nREMINDER_TZ=Europe/Madrid\nREMINDER_EXCLUDE_IDS=%s\n' \
  "<HH:MM ~2 min ahead, Madrid>" "<Victoria's test id, optional>" >> .env
grep -c '^REMINDER_AT=' .env   # must be exactly 1
sudo systemctl restart spanish-bot
journalctl -u spanish-bot -n 20 --no-pager   # 'Start polling', no TelegramConflictError
```

- [ ] **Step 4: Manual checklist in Telegram**

**Prep for the positive case:** it needs a user with ≥1 due card at the fire minute. A newly added word is due the same day (`add_card` sets `due_at = today`), so if nobody is currently due, add one word from a test account shortly before the fire minute.

- at the set minute, a user with ≥1 due card receives «🔔 Сегодня на повторение: N слов…», bold renders (no literal `<b>`), N matches what «🎴 Карточки» then shows;
- a user with 0 due gets **no** message;
- the excluded id gets **no** message;
- `journalctl` shows a send happened (and any blocked-user warning is non-fatal).

- [ ] **Step 5: Set the real send time**

Edit `.env` on the server to the time Victoria wants (or comment `REMINDER_AT` out to disable), then `sudo systemctl restart spanish-bot` and re-check the journal.

**Avoid a double send the test day:** if the real time is still *ahead* today when you set it, the loop will also fire at it today — a second reminder the same day as the ~2-min test. Usually harmless. For exactly one/day starting tomorrow, set the real time only *after* it has already passed today, or leave `REMINDER_AT` commented until tomorrow.

- [ ] **Step 6: Reconcile docs (the "no push" reversal) — TWO separate git repos**

The app docs/code and the vault tracker live in **different** repos; commit each from its own root.

- **App repo** (everything under `app/`):
  - `AGENTS.md`: update the «Pull-режим, без пуш-напоминаний» key decision to note the one opt-out-able daily due-count reminder; bump the test count; add `reminders.py` to the structure list.
  - `docs/superpowers/specs/2026-06-02-spanish-bot-design.md`: amend the "no push reminders" statement to reference this feature.
  - From the `app/` root: `git add AGENTS.md docs/superpowers/specs/2026-06-02-spanish-bot-design.md && git commit --no-gpg-sign -m "docs: daily reminder shipped — reverse no-push decision" && git push`.
- **Vault repo** (the tracker note is in the vault root, a SEPARATE repo — the app commit will NOT include it):
  - `Projects/Spanish Bot/{spanish-bot} {plan} project overview – 2026-06-03.md`: add a shipped line.
  - From `/Users/vtrush/work/main vault`: `git add "Projects/Spanish Bot/{spanish-bot} {plan} project overview – 2026-06-03.md" && git commit --no-gpg-sign -m "Spanish Bot tracker: daily reminder shipped"` (stage **only that file** — the vault has unrelated uncommitted changes).

---

## Notes for the implementer

- **Why `date.today()` in the loop, not the local date?** Deliberate — the count must match what the training handlers show (they use `date.today()`), and a daytime Madrid fire is the same calendar day in UTC. See the spec's Date basis section and its known limitation (early-morning `REMINDER_AT` not supported).
- **Why two catch layers?** `send_daily_reminders` catches *per user*: a clean `warning` for the expected blocked/never-started cases (`TelegramForbiddenError`/`TelegramBadRequest`) and a broad `except Exception` (full traceback) for anything else — network/server/retry-after/bug — so one user never aborts the batch (this is the fix for review finding 1). `reminder_loop`'s outer `except Exception` is the last-resort backstop for an error *outside* the per-user loop (e.g. the `get_due_cards` read), so the long-lived loop reschedules instead of dying. `CancelledError` is `BaseException`, so it escapes both → clean shutdown/cancel.
- **Why no reference-free `create_task`?** A bare `create_task` result can be garbage-collected mid-flight (asyncio docs); `reminder_task` holds the reference, and the `finally` cancels + `gather`s it for a clean shutdown.
