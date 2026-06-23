# Sticky Add-Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After tapping «➕ Добавить слово» once, the user stays in add-mode and can add many words in a row, leaving cleanly via any menu button (or `/start`) in one tap — with each word's preview buttons acting only on that word.

**Architecture:** Pure aiogram FSM-handler edits across `states.py`, `handlers/add.py`, `handlers/menu.py`, `handlers/training.py`, `keyboards.py`. Stickiness = stop clearing the FSM state on save/skip. One-tap exit = let menu-button text fall through `add.router` to the router that owns it, and route every mode-entry through a shared `leave_modes()` that drops the active mode + pending previews **without** wiping incidental data (vocab voice id). Multiple un-confirmed previews are disambiguated by a per-preview token carried in the button `callback_data` and validated against a `pending` dict in FSM data. No schema change, no new dependency.

**Tech Stack:** Python 3.12 · aiogram 3.13.1 (long-polling, MemoryStorage FSM) · SQLite. Bot is live on a VPS under systemd.

## Global Constraints

- **Manual handler verification.** Handlers are not unit-tested in this project (`AGENTS.md`); pure logic lives in `services/`/`db`/pure modules. The handler edits below add no new pure logic and are gated by the existing suite staying green plus a manual pass at the end — that's why handler tasks have no "write a failing test" step. **Exception:** Task 5 changes the `save_card_keyboard` callback-data contract, which is a pure function the repo already unit-tests (`test_keyboards.py`); that one change is done test-first.
- **Regression gate:** `.venv/bin/pytest -q` must stay green after every task. Baseline is **80 passed**; Task 5 adds one keyboard test → **81** from then on. Also run `python -c "import bot"` to catch broken imports faster than a full launch.
- **Gender-neutral copy only** (one male user among the users): no gendered or first-person past-tense bot phrasing. All new strings below already comply.
- **Frequent commits:** one commit per task, small and self-contained. Commit with `--no-gpg-sign` (non-interactive commits on this mac otherwise fail GPG).
- **Do NOT restart the live bot until the final task.** Python does not hot-reload; restart is deliberate, with a single-poller-per-token caveat.
- **Router order (`bot.py`), do not change:** `menu → add → training`.
- **FSM data keys used here:** `pending` (dict `{str(seq): card}` of un-confirmed previews), `seq` (monotonic int, preview-token counter — **never reset** within a storage lifetime), plus the pre-existing `queue`/`retried` (training) and `vocab_voice_msg_id` (vocab voice cleanup). `leave_modes` must preserve `seq` and `vocab_voice_msg_id`.

---

### Task 1: `leave_modes` FSM helper (`states.py`)

The single primitive every mode-entry handler uses instead of `state.clear()`. It must exit any active mode and drop pending previews, but **preserve** `vocab_voice_msg_id` (so `menu._remove_card_voice` can still delete a previously-shown vocab voice — a broad `state.clear()` would orphan that message, finding 2) and **preserve** `seq` (so a preview token minted before the exit can never collide with one minted after — finding 1).

**Files:**
- Modify: `states.py` (add import + function)

**Interfaces:**
- Produces: `async def leave_modes(state: FSMContext) -> None` — consumed by Tasks 2, 3, 4.

- [ ] **Step 1: Add the import**

At the top of `states.py`, alongside the existing aiogram import:

```python
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
```

- [ ] **Step 2: Add the helper** (below the `Training` class)

```python
async def leave_modes(state: FSMContext) -> None:
    """Exit any add/training mode and drop un-confirmed add-previews.

    Unlike `state.clear()` this deliberately PRESERVES incidental FSM data:
    - `vocab_voice_msg_id` — so `menu._remove_card_voice` can still delete the
      last vocab voice message (clearing it would orphan that message in chat);
    - `seq` — the monotonic preview-token counter, so a preview created before
      this exit can never share a token with one minted afterwards.
    `set_state(None)` drops the mode (so free text stops matching add/training);
    `pending={}` makes every still-visible preview's buttons go inert.
    """
    await state.set_state(None)
    await state.update_data(pending={})
```

- [ ] **Step 3: Run the regression suite + import check**

Run: `.venv/bin/pytest -q && python -c "import bot"`
Expected: `80 passed`, import clean.

- [ ] **Step 4: Commit**

```bash
git add states.py
git commit --no-gpg-sign -m "feat(fsm): add leave_modes() — exit mode, drop previews, keep incidental data"
```

---

### Task 2: Training entry uses `leave_modes` (`handlers/training.py`)

Spec item 7. Each training-entry handler calls `await leave_modes(state)` at the very top, **before** the `if not due:` check. Fixes: (a) the `not due` branch returns without `set_state`, so without this the user stays in `AddCard.waiting_for_text` and the next word silently re-enters add; (b) it drops any pending add-preview so an earlier «✅ Да» can't save after the switch. The `update_data(queue=…, retried=[])` right after still works (these handlers always rebuild the queue), and `leave_modes` preserves `vocab_voice_msg_id`/`seq`.

**Files:**
- Modify: `handlers/training.py` — imports, `start_flashcards` (~46-56), `start_translate` (~118-128), `start_listen` (~212-222)

**Interfaces:**
- Consumes: `leave_modes` from `states` (Task 1).
- Produces: after any training-entry tap, no `AddCard` state and no `pending` previews remain.

- [ ] **Step 1: Import `leave_modes`**

Update the existing import in `training.py`:

```python
from states import Training, leave_modes
```

- [ ] **Step 2: Add `leave_modes` to `start_flashcards`**

```python
@router.message(F.text == keyboards.BTN_FLASHCARDS)
async def start_flashcards(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    await leave_modes(state)  # leave any prior mode + drop pending add-previews
    due = db.get_due_cards(conn, message.from_user.id, date.today())
    if not due:
        await message.answer(EMPTY)
        return
    await state.set_state(Training.flashcards)
    await state.update_data(queue=[r["id"] for r in due], retried=[])
    await _show_next_flashcard(message, state, conn)
```

- [ ] **Step 3: Add `leave_modes` to `start_translate`**

```python
@router.message(F.text == keyboards.BTN_TRANSLATE)
async def start_translate(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    await leave_modes(state)  # leave any prior mode + drop pending add-previews
    due = db.get_due_cards(conn, message.from_user.id, date.today())
    if not due:
        await message.answer(EMPTY)
        return
    await state.set_state(Training.translate)
    await state.update_data(queue=[r["id"] for r in due], retried=[])
    await _ask_next_translation(message, state, conn)
```

- [ ] **Step 4: Add `leave_modes` to `start_listen`**

```python
@router.message(F.text == keyboards.BTN_LISTEN)
async def start_listen(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    await leave_modes(state)  # leave any prior mode + drop pending add-previews
    due = db.get_due_cards(conn, message.from_user.id, date.today())
    if not due:
        await message.answer(EMPTY)
        return
    await state.set_state(Training.listen)
    await state.update_data(queue=[r["id"] for r in due], retried=[])
    await _ask_next_listen(message, state, conn)
```

- [ ] **Step 5: Run the regression suite + import check**

Run: `.venv/bin/pytest -q && python -c "import bot"`
Expected: `80 passed`, import clean.

- [ ] **Step 6: Commit**

```bash
git add handlers/training.py
git commit --no-gpg-sign -m "fix(training): leave_modes on entry so add-mode exits in one tap"
```

---

### Task 3: «Мой словарь» and `/start` leave modes (`handlers/menu.py`)

Spec item 3 + the review's open question. `show_vocab` gains a `state` param and calls `leave_modes` so «📖 Мой словарь» exits any mode (also fixes the latent training quirk where it left the user mid-training). `cmd_start` does the same so `/start` is a real reset. `FSMContext` is already imported; `leave_modes` is new.

**Files:**
- Modify: `handlers/menu.py` — import, `cmd_start` (~27-29), `show_vocab` (~48-51)

**Interfaces:**
- Consumes: `leave_modes` from `states` (Task 1).
- Produces: after «Мой словарь» or `/start`, no mode is active (stateless free text afterwards is silently ignored — matches idle main-menu today).

- [ ] **Step 1: Import `leave_modes`**

Add to `menu.py` imports:

```python
from states import leave_modes
```

- [ ] **Step 2: Reset state in `cmd_start`**

```python
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await leave_modes(state)  # /start is a clean reset
    await message.answer(GREETING, reply_markup=keyboards.main_menu())
```

- [ ] **Step 3: Reset state in `show_vocab`**

```python
@router.message(F.text == keyboards.BTN_VOCAB)
async def show_vocab(
    message: Message, state: FSMContext, conn: sqlite3.Connection
) -> None:
    await leave_modes(state)  # «Мой словарь» leaves any active mode (add or training)
    text, kb = _render_page(conn, message.from_user.id, 0)
    await message.answer(text, reply_markup=kb)
```

- [ ] **Step 4: Run the regression suite + import check**

Run: `.venv/bin/pytest -q && python -c "import bot"`
Expected: `80 passed`, import clean.

- [ ] **Step 5: Commit**

```bash
git add handlers/menu.py
git commit --no-gpg-sign -m "fix(menu): «Мой словарь» and /start leave any active mode"
```

---

### Task 4: Add-mode entry + routing (`handlers/add.py`)

Spec items 2 and 6. Three coupled edits:
- `start_add`: `leave_modes(state)` before `set_state` (a re-tap on top of an unfinished preview drops the old previews so their «✅ Да» goes inert), plus the new sticky prompt.
- `receive_text`: exclude menu-button text via `~F.text.in_(keyboards.MENU_BUTTONS)`, and delete the now-dead in-body menu-button guard block (the one answering "Окей, отменяю добавление 🙂 Нажми кнопку ещё раз.").
- `reject_non_text`: same filter, so a menu-button tap isn't caught by the non-text catch-all and instead falls through to the router that owns it.

(The preview-creation tail of `receive_text` is rewritten in Task 5 — leave it untouched here.)

**Files:**
- Modify: `handlers/add.py` — import, `start_add` (~24-27), `receive_text` decorator + guard (~30-39), `reject_non_text` decorator (~115)

**Interfaces:**
- Consumes: `leave_modes` (Task 1), `keyboards.MENU_BUTTONS` (existing).
- Produces: `start_add` leaves a clean FSM (no pending, state `AddCard.waiting_for_text`); menu-button text no longer matches any `add.py` handler.

- [ ] **Step 1: Import `leave_modes`**

```python
from states import AddCard, leave_modes
```

- [ ] **Step 2: Rewrite `start_add` (leave_modes + new prompt)**

```python
@router.message(F.text == keyboards.BTN_ADD)
async def start_add(message: Message, state: FSMContext) -> None:
    await leave_modes(state)  # drop stale previews so their «✅ Да» goes inert
    await state.set_state(AddCard.waiting_for_text)
    await message.answer(
        "Пиши слова или фразы — по одному, на испанском или русском 🙂 "
        "Я сохраню каждое. Когда закончишь, выбери что-нибудь в меню внизу."
    )
```

- [ ] **Step 3: Add the menu-button filter to `receive_text` and delete the dead guard block**

Change the decorator to include `~F.text.in_(keyboards.MENU_BUTTONS)` and remove the `if text in keyboards.MENU_BUTTONS:` block. Resulting head:

```python
@router.message(AddCard.waiting_for_text, F.text, ~F.text.in_(keyboards.MENU_BUTTONS))
async def receive_text(
    message: Message, state: FSMContext, conn: sqlite3.Connection,
    anthropic: Anthropic,
) -> None:
    text = message.text.strip()
    try:
        # to_thread: the sync Anthropic call must not block the event loop
        card = await asyncio.to_thread(enrichment.enrich, anthropic, text)
    except enrichment.EnrichmentError:
```

(The enrichment-error branch, duplicate branch, and preview tail are untouched in this task.)

- [ ] **Step 4: Add the menu-button filter to `reject_non_text`**

```python
@router.message(AddCard.waiting_for_text, ~F.text.in_(keyboards.MENU_BUTTONS))
async def reject_non_text(message: Message) -> None:
    await message.answer("Я понимаю пока только текст 🙂 Напиши слово или фразу.")
```

(Non-text messages still match — `F.text` is `None`, `None in MENU_BUTTONS` is `False`, so `~…` is `True`. A menu-button text now falls through to its owning router.)

- [ ] **Step 5: Run the regression suite + import check**

Run: `.venv/bin/pytest -q && python -c "import bot"`
Expected: `80 passed`, import clean.

- [ ] **Step 6: Commit**

```bash
git add handlers/add.py
git commit --no-gpg-sign -m "feat(add): sticky entry prompt + one-tap menu exit (filter menu buttons)"
```

---

### Task 5: Per-preview save tokens + sticky save/skip (`handlers/add.py`, `keyboards.py`)

Spec items 1, 4, 5 + the wording table + finding 1 fix. This makes each preview's buttons act only on that preview (Victoria's choice: every preview independently saveable), and keeps the user in add-mode after each save/skip.

Design — the **token contract**:
- `receive_text`'s preview tail mints a monotonic `seq` (FSM data, never reset), stores the card under `pending[str(seq)]`, and builds the keyboard with that `seq` baked into the button `callback_data` (`save:yes:{seq}` / `save:no:{seq}`).
- `save_yes` / `save_no` parse `seq` from `callback_data` and `pending.pop(str(seq), None)`. The pop is the whole guard: a missing key (stale button, double-tap, or a preview dropped by `leave_modes`) → answer "уже неактивна" and return; a present key → that exact card, and it's now consumed (read-once). Other previews' entries stay, so they remain independently saveable.
- Neither handler touches the FSM **state**, so it stays `AddCard.waiting_for_text` → next word routes straight back to `receive_text` (stickiness).
- The tapped «Сохранить?» message is replaced in place via `edit_text` (drops the inline keyboard) with a `TelegramBadRequest` fallback to a fresh message — factored into `_finish_preview`. `TelegramBadRequest` is already imported in `add.py`.
- Wording: «Сохранено! ✅ Пиши следующее 🙂» / «Ок, пропускаю 🙂 Пиши следующее.»

**Files:**
- Modify: `tests/test_keyboards.py` (add one test)
- Modify: `keyboards.py` — `save_card_keyboard` (~45-49)
- Modify: `handlers/add.py` — `receive_text` preview tail (~61-64), `save_yes` (~88-105), `save_no` (~108-112); add `_finish_preview` and a legacy callback handler

**Interfaces:**
- Consumes: `card` dict (built by `enrichment.enrich`), `db.add_card` and `db.card_exists` (unchanged signatures).
- Produces: FSM data `pending: dict[str, card]` and `seq: int`; callback_data format `save:yes:{seq}` / `save:no:{seq}`.

- [ ] **Step 1: Add a failing test for the keyboard's token contract**

In `tests/test_keyboards.py`:

```python
def test_save_card_keyboard_carries_seq():
    kb = keyboards.save_card_keyboard(7)
    datas = {b.callback_data for row in kb.inline_keyboard for b in row}
    assert datas == {"save:yes:7", "save:no:7"}
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/pytest tests/test_keyboards.py::test_save_card_keyboard_carries_seq -q`
Expected: FAIL — `save_card_keyboard()` currently takes no argument (`TypeError`).

- [ ] **Step 3: Add a `seq` parameter to `save_card_keyboard`**

```python
def save_card_keyboard(seq: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да", callback_data=f"save:yes:{seq}"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"save:no:{seq}"),
    ]])
```

- [ ] **Step 4: Run the test to confirm it passes**

Run: `.venv/bin/pytest tests/test_keyboards.py::test_save_card_keyboard_carries_seq -q`
Expected: PASS.

- [ ] **Step 5: Rewrite the preview tail of `receive_text`**

Replace the current `await state.update_data(card=card)` … `save_card_keyboard()` tail (the success path, after the duplicate check) with:

```python
    data = await state.get_data()
    seq = data.get("seq", 0) + 1            # monotonic; never reset (token uniqueness)
    pending = data.get("pending", {})
    pending[str(seq)] = card
    await state.update_data(pending=pending, seq=seq)
    await message.answer(formatting.card_preview(card), parse_mode="HTML")
    await _send_voice(message, card["spanish"])
    await message.answer("Сохранить?",
                         reply_markup=keyboards.save_card_keyboard(seq))
```

- [ ] **Step 6: Add the `_finish_preview` helper** (above `save_yes`)

```python
async def _finish_preview(call: CallbackQuery, text: str) -> None:
    """Replace the «Сохранить?» prompt with the result, dropping the buttons.

    edit_text omits reply_markup, so the inline keyboard disappears. Falls back
    to a fresh message if the original is too old to edit (pattern from
    menu.py:_remove_card_voice).
    """
    try:
        await call.message.edit_text(text)
    except TelegramBadRequest:
        await call.message.answer(text)
```

- [ ] **Step 7: Rewrite `save_yes` (token validation + re-dedup before add)**

The `pending.pop` validates the token and consumes it (read-once). The extra
`db.card_exists` re-check matters because dedup at preview time only compares
against **saved** rows — two unsaved previews of the same word (or the same word
added elsewhere meanwhile) would otherwise both pass and create a duplicate.

```python
@router.callback_query(F.data.startswith("save:yes:"))
async def save_yes(
    call: CallbackQuery, state: FSMContext, conn: sqlite3.Connection
) -> None:
    data = await state.get_data()
    pending = data.get("pending", {})
    card = pending.pop(call.data.split(":")[2], None)
    if card is None:
        await call.answer("Эта карточка уже неактивна 🙂")
        return
    await state.update_data(pending=pending)  # consumed: read-once + per-preview scope
    if db.card_exists(conn, call.from_user.id, card["spanish"]):
        # Already saved (e.g. a second unsaved preview of the same word, or added
        # since this preview was created) — don't duplicate.
        await _finish_preview(call, f"«{card['spanish']}» уже есть в твоём словаре 🙂")
        await call.answer()
        return
    db.add_card(
        conn, user_id=call.from_user.id, kind=card["kind"],
        spanish=card["spanish"], russian=card["russian"],
        transcription=card["transcription"], example_es=card["example_es"],
        example_ru=card["example_ru"], enriched=True, today=date.today(),
    )
    await _finish_preview(call, "Сохранено! ✅ Пиши следующее 🙂")
    await call.answer()
```

- [ ] **Step 8: Rewrite `save_no`**

```python
@router.callback_query(F.data.startswith("save:no:"))
async def save_no(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    pending = data.get("pending", {})
    card = pending.pop(call.data.split(":")[2], None)
    if card is None:
        await call.answer("Эта карточка уже неактивна 🙂")
        return
    await state.update_data(pending=pending)
    await _finish_preview(call, "Ок, пропускаю 🙂 Пиши следующее.")
    await call.answer()
```

- [ ] **Step 9: Add a legacy handler for pre-deploy tokenless buttons** (below `save_no`)

After deploy, messages already in chat still carry the old `save:yes` / `save:no`
callback data (no token), which no longer matches the `startswith("save:yes:")`
filters. Without this, tapping such a button spins silently until it times out.

```python
@router.callback_query(F.data.in_({"save:yes", "save:no"}))
async def save_legacy(call: CallbackQuery) -> None:
    # Tokenless buttons from messages sent before this deploy — answer gracefully.
    await call.answer("Эта карточка уже неактивна 🙂")
```

- [ ] **Step 10: Run the regression suite + import check**

Run: `.venv/bin/pytest -q && python -c "import bot"`
Expected: `81 passed` (80 + the new keyboard test), import clean.

- [ ] **Step 11: Commit**

```bash
git add handlers/add.py keyboards.py tests/test_keyboards.py
git commit --no-gpg-sign -m "feat(add): per-preview save tokens + sticky save/skip with button removal"
```

---

### Task 6: Restart the live bot and run the manual verification pass

Per `AGENTS.md` and the spec's Testing section — the human-in-the-loop gate that substitutes for handler unit tests. Ask Victoria to drive Telegram; already-sent messages keep their OLD buttons/texts, so test on freshly sent ones.

**Files:** none (verification only).

- [ ] **Step 1: Confirm the suite is green one last time**

Run: `.venv/bin/pytest -q`
Expected: `81 passed`.

- [ ] **Step 2: Restart the bot (single poller per token)**

Kill the old instance first, then start fresh and confirm `Start polling` with no `TelegramConflictError`. macOS local: process is `Python bot.py` (capital P):

```bash
pkill -f "MacOS/Python bot.py"
source .venv/bin/activate && python bot.py
```

VPS: it's a systemd unit — `sudo systemctl restart spanish-bot && journalctl -u spanish-bot -n 20 -f` (see `docs/superpowers/deploy.md`). Never run a second poller against the same token.

- [ ] **Step 3: Manual checklist in Telegram** (each must pass)

Stickiness & wording:
- add two words back-to-back without re-tapping «➕ Добавить слово»;
- after a save: buttons gone, message reads «Сохранено! ✅ Пиши следующее 🙂»;
- after a skip: buttons gone, message reads «Ок, пропускаю 🙂 Пиши следующее.».

One-tap exits:
- exit via each menu button (🎴 Карточки / ✍️ Проверить себя / 🎧 Аудирование / 📖 Мой словарь / re-tap ➕ Добавить слово) — each in one tap;
- `/start` while in add-mode or mid-training → main menu, and a following word is NOT treated as input (mode left);
- training button while in add-mode **with no due cards** → see `EMPTY`, then send a word → it must NOT be added (add-mode was left).

Per-preview tokens & dedup:
- send word A (preview+buttons), then send word B **without** tapping → tap A's «✅ Да» → saves A; tap B's «✅ Да» → saves B (both work independently);
- send the same word twice without saving (two previews), then tap «✅ Да» on both → first saves it, second → «уже есть в твоём словаре» (no duplicate card);
- tap the same «✅ Да» twice → second tap → "уже неактивна" (no duplicate);
- start a preview, switch to a training button, scroll up and tap the old «✅ Да» → "уже неактивна";
- start a preview, re-tap «➕ Добавить слово», then tap the old preview's «✅ Да» → "уже неактивна";
- (post-deploy) tap a «✅ Да» on a message sent **before** this deploy → "уже неактивна" (handled by the legacy handler, no silent spinner).

Vocab voice cleanup (finding 2 regression guard):
- open «📖 Мой словарь» → open a card (voice plays) → tap a reply-menu button → return to «Мой словарь» → open another card → the previous card's voice message is removed as before (no pile-up of orphaned voice bubbles).

- [ ] **Step 4: Update project docs if behavior notes changed**

If anything diverged from the spec during implementation, reconcile the spec and `AGENTS.md` (per "правь спеку согласованно"). Otherwise note in `Projects/Spanish Bot/` tracker that sticky add-mode shipped.

---

## Notes for the implementer

- **Why no state filter on `save_yes`/`save_no`?** They stay global callbacks; correctness comes from the `pending`-dict token (pop validates + consumes) plus `leave_modes` dropping `pending` on every mode exit. State-filtering the callback would leave a stale button silently doing nothing and interacts awkwardly with the button-removal in Task 5.
- **Why `seq` is never reset.** If `leave_modes` reset `seq` to 0, a button minted before the exit (`save:yes:1`) could later collide with a freshly minted `save:yes:1` and save the wrong card. Monotonic `seq` for the whole storage lifetime guarantees token uniqueness; it only resets on bot restart, at which point `pending` is empty too (MemoryStorage), so pre-restart buttons read as inert.
- **Double-save race.** Step 7's `db.card_exists` re-check closes the *sequential* same-word duplicate path (two previews of one word, saved one after the other). A truly *simultaneous* double-tap can still slip through — both handlers read their own `get_data()` copy and `card_exists` before either commits → at worst one duplicate card, deletable from «Мой словарь». Accepted for a ~3-user personal bot; not worth a storage lock.
- **`pending` growth** is bounded by un-confirmed previews in one add session and is wiped by any `leave_modes`. No cleanup needed.
