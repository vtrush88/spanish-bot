# Sticky Add-Mode — Design

**Date:** 2026-06-22
**Status:** shipped 2026-06-23 — implemented per
`docs/superpowers/plans/2026-06-22-sticky-add-mode.md`, deployed to VPS and
verified live (manual Telegram pass)
**Components:** `states.py`, `handlers/add.py`, `handlers/menu.py`,
`handlers/training.py`, `keyboards.py`

## Goal

After tapping «➕ Добавить слово» once, the user stays in add-mode and can add
many words in a row, leaving only when they choose — via any menu button or
`/start`, in one tap. Each word's preview buttons act only on that word. Today
the mode ends after a single save, forcing a button tap before every new word.

## Motivation

The end user (mom) usually adds several words in one sitting. Re-tapping
«➕ Добавить слово» before each word is friction. The duplicate and preview paths
already keep the user in add-mode; this extends the same stickiness across the
save / skip steps and makes every menu button (and `/start`) a clean one-tap exit.

## Current behavior

- `start_add` → state `AddCard.waiting_for_text`, prompt.
- `receive_text` (`AddCard.waiting_for_text, F.text`): menu-button guard → cancel +
  "нажми кнопку ещё раз"; enrich; duplicate → stay; else preview + voice +
  «Сохранить? [✅ Да] [❌ Нет]». The preview card is held in FSM data under a
  single `card` key (a new preview overwrites the old one).
- `save_yes` / `save_no` callbacks → `state.clear()` → **exit add-mode**. This is
  why adding another word needs a fresh button tap.
- Router order (`bot.py`): `menu → add → training`. «📖 Мой словарь» (menu router)
  and «➕ Добавить слово» (add router, registered before `receive_text`) already
  switch in one tap. The three training buttons live in the *last* router, so
  `receive_text` intercepts them first → the "нажми кнопку ещё раз" double-tap.

## Desired behavior (UX)

1. Enter add-mode once; stay until the user leaves via the menu or `/start`.
2. After ✅ Да: «Сохранено! ✅ Пиши следующее 🙂», stay in mode. The Да/Нет buttons
   are removed (the «Сохранить?» message is edited into this result).
3. After ❌ Нет: «Ок, пропускаю 🙂 Пиши следующее.», buttons removed, stay in mode.
4. Each preview is **independently saveable**. If several previews are open
   un-confirmed at once (e.g. the user sent two words without tapping), every
   preview's «✅ Да» / «❌ Нет» acts only on its own word.
5. Duplicate / enrichment error: stay in mode (already implemented).
6. Exit — any menu button or `/start` leaves add-mode in **one tap**:
   - Training buttons (Карточки / Проверить себя / Аудирование) → switch to that mode.
   - «📖 Мой словарь» → show the list and leave add-mode (no mode active afterward).
   - «➕ Добавить слово» → re-enter add-mode (fresh prompt, stale previews dropped).
   - `/start` → main menu, mode left (a real reset).

## Design

### Core mechanism: `leave_modes()` instead of `state.clear()`

Every mode-entry handler routes through one shared helper in `states.py`:

```python
async def leave_modes(state: FSMContext) -> None:
    await state.set_state(None)
    await state.update_data(pending={})
```

`set_state(None)` drops the active mode (free text stops matching add/training);
`pending={}` makes every still-visible preview's buttons inert. Unlike a broad
`state.clear()` it **deliberately preserves two incidental FSM keys**:

- `vocab_voice_msg_id` — so `menu._remove_card_voice` can still delete the last
  vocab voice message; a `state.clear()` here would orphan that voice bubble in
  chat (review finding 2).
- `seq` — the monotonic preview-token counter (below); preserving it guarantees a
  token minted before an exit can never collide with one minted afterward
  (review finding 1).

### Per-preview save tokens

Multiple un-confirmed previews are disambiguated by a per-preview token:

- A monotonic `seq` int lives in FSM data and is **never reset** within a storage
  lifetime (only on bot restart, when `pending` is empty too — MemoryStorage).
- Each preview stores its card under `pending[str(seq)]` (a dict in FSM data) and
  bakes `seq` into the button `callback_data`: `save:yes:{seq}` / `save:no:{seq}`.
- `save_yes` / `save_no` parse `seq` and `pending.pop(str(seq), None)`. The pop is
  the whole guard: a missing key (stale button, double-tap, or a preview dropped
  by `leave_modes`) → «Эта карточка уже неактивна 🙂» and return; a present key →
  that exact card, now consumed (read-once). Other previews' entries survive, so
  they stay independently saveable.

This replaces the spec's earlier single-`card` model and its `card=None` read-once
guard — those only supported one live preview at a time.

## Implementation

Mapped task-by-task in the plan; summary of the edits:

1. **`leave_modes` helper (`states.py`).** As above — the single primitive every
   mode-entry handler calls instead of `state.clear()`.
2. **Stickiness.** `save_yes` / `save_no` never touch the FSM **state**, so it
   stays `AddCard.waiting_for_text` and the next text message routes back to
   `receive_text`.
3. **One-tap exit for training buttons.** Add `~F.text.in_(keyboards.MENU_BUTTONS)`
   to the decorators of `receive_text` and the catch-all `reject_non_text` — the
   same pattern already used by `check_translation` / `check_listen`. Training-button
   text then falls through add.router into training.router. Remove the now-dead
   menu-button guard block inside `receive_text`. Each training-entry handler
   (`start_flashcards` / `start_translate` / `start_listen`) calls `leave_modes`
   at the **top**, before the `if not due:` check — otherwise the `not due` branch
   returns without `set_state`, leaving the user in `AddCard.waiting_for_text` so
   the next word silently re-enters add. `leave_modes` also drops any pending
   preview, so an earlier «✅ Да» can't save after the switch.
4. **«Мой словарь» and `/start` exit.** `handlers/menu.py:show_vocab` and
   `cmd_start` gain a `state: FSMContext` parameter and call `leave_modes` before
   rendering. «Мой словарь» then leaves any active mode (add **or** training — also
   fixes the latent quirk where tapping it mid-training kept the user in the
   training state); `/start` becomes a real reset.
5. **Remove Да/Нет buttons + show result.** `save_yes` / `save_no` replace the
   «Сохранить?» message via `_finish_preview` — `call.message.edit_text(text)` with
   no `reply_markup` (buttons disappear), wrapped in `try/except TelegramBadRequest`
   with a fallback to `call.message.answer(text)` (pattern from
   `menu.py:_remove_card_voice`).
6. **Re-dedup before add.** `save_yes` re-checks `db.card_exists` before
   `db.add_card`. Preview-time dedup only compares against **saved** rows, so two
   un-confirmed previews of the same word (or the same word added elsewhere
   meanwhile) would otherwise both pass and create a duplicate. On a hit → finish
   the preview with «уже есть в твоём словаре».
7. **Entry prompt + clean entry.** `start_add` calls `leave_modes` **before**
   `set_state(AddCard.waiting_for_text)`, then shows the sticky prompt. Re-tapping
   «➕ Добавить слово» on top of an unfinished preview thus drops the old previews
   so their still-live «✅ Да» goes inert.
8. **Token-carrying keyboard.** `keyboards.save_card_keyboard(seq)` bakes `seq`
   into `save:yes:{seq}` / `save:no:{seq}`. This is a pure function the repo
   already unit-tests, so it's the one change done test-first (+1 test).
9. **Legacy callback handler.** After deploy, messages already in chat carry the
   old tokenless `save:yes` / `save:no` callback data, which no longer matches the
   `startswith("save:yes:")` filters. A `save_legacy` handler
   (`F.data.in_({"save:yes", "save:no"})`) answers «уже неактивна» so such a tap
   doesn't spin silently until timeout.

### Why `save_yes`/`save_no` stay global callbacks (no state filter)

Correctness comes from the `pending` token (pop validates + consumes) plus
`leave_modes` dropping `pending` on every mode exit. A state filter on the
callback would leave a stale button silently doing nothing and interacts awkwardly
with the button-removal — and would not cover the mode-switch case, since the
card is non-`None` at that point. Dropping `pending` in `leave_modes` is what
makes the cross-mode and re-entry cases safe.

## Wording

| Moment | Now | New |
|---|---|---|
| Entry (`start_add`) | «Напиши слово или фразу — на испанском или русском 🙂» | «Пиши слова или фразы — по одному, на испанском или русском 🙂 Я сохраню каждое. Когда закончишь, выбери что-нибудь в меню внизу.» |
| After ✅ Да | «Сохранено! ✅» | «Сохранено! ✅ Пиши следующее 🙂» |
| After ❌ Нет | «Ок, не сохраняю.» | «Ок, пропускаю 🙂 Пиши следующее.» |
| Already saved (re-dedup at save) | — | «"{слово}" уже есть в твоём словаре 🙂» |
| Stale / inert «✅ Да» | «Эта карточка уже неактивна 🙂» | unchanged |

All texts stay gender-neutral (one male user).

## Edge cases

- **Independent previews.** Send word A (preview+buttons), then word B without
  tapping → A's «✅ Да» saves A, B's «✅ Да» saves B. Each token scopes to its own
  card via the `pending` dict.
- **Same word twice, un-confirmed.** Two previews of one word, both «✅ Да»: the
  first saves it; the second hits the re-dedup → «уже есть в твоём словаре» (no
  duplicate).
- **Double-tap / stale «✅ Да».** Buttons are removed on the first tap; if a second
  callback still arrives, `pending.pop` misses → «уже неактивна».
- **Simultaneous double-save race.** Two near-simultaneous taps could both read a
  non-empty `pending` and pass `card_exists` before either commits → at worst one
  duplicate card (deletable from «Мой словарь»). Accepted for a ~3-user personal
  bot; not worth a storage lock.
- **Unfinished preview, then switch to training / `/start` / «Мой словарь».**
  `leave_modes` at the entry of each drops `pending`, so the earlier preview's
  «✅ Да» reads a missing token → «уже неактивна».
- **Re-tap «➕ Добавить слово» over an unfinished preview.** `leave_modes` in
  `start_add` drops the old previews → those buttons become inert.
- **Pre-deploy tokenless buttons.** A «✅ Да» on a message sent before this ships
  carries old `save:yes` data → the `save_legacy` handler answers «уже неактивна»
  (no silent spinner).
- **Vocab voice cleanup preserved (finding 2).** `leave_modes` keeps
  `vocab_voice_msg_id`, so opening cards in «Мой словарь» still removes the
  previous card's voice bubble — no pile-up of orphaned voice messages.
- **Stateless free text** (after «Мой словарь» / `/start` leave the mode): no
  handler matches → silently ignored, identical to the idle main-menu state today.

## Testing

Handlers are verified manually per project convention (`AGENTS.md`). The one new
pure-logic change — `save_card_keyboard(seq)` carrying the token into
`callback_data` — is unit-tested (test-first), taking the suite from **80 → 81**.
Run the suite (`.venv/bin/pytest -q`, expect 81 green) + `python -c "import bot"`
after each task, then a manual pass on the server:

Stickiness & wording:
- add two words back-to-back without re-tapping «➕ Добавить слово»;
- after a save: buttons gone, «Сохранено! ✅ Пиши следующее 🙂»;
- after a skip: buttons gone, «Ок, пропускаю 🙂 Пиши следующее.».

One-tap exits:
- exit via each menu button (3 training + «Мой словарь» + re-tap «Добавить слово»)
  — each in one tap;
- `/start` while in add-mode or mid-training → main menu, and a following word is
  NOT treated as input;
- training button while in add-mode **with no due cards** → see `EMPTY`, then send
  a word → it must NOT be added (add-mode was left).

Per-preview tokens & dedup:
- send A then B without tapping → tap A's «✅ Да» (saves A), tap B's «✅ Да» (saves B);
- send the same word twice un-confirmed, tap «✅ Да» on both → first saves, second
  → «уже есть в твоём словаре» (no duplicate);
- tap the same «✅ Да» twice → second → «уже неактивна»;
- start a preview, switch to a training button, scroll up and tap the old «✅ Да»
  → «уже неактивна»;
- start a preview, re-tap «➕ Добавить слово», then tap the old preview's «✅ Да»
  → «уже неактивна»;
- (post-deploy) tap a «✅ Да» on a message sent **before** this deploy → «уже неактивна».

Vocab voice cleanup (finding 2 regression guard):
- «Мой словарь» → open a card (voice plays) → tap a reply-menu button → return →
  open another card → the previous card's voice message is removed (no pile-up).

## Out of scope

- Counting / announcing how many words were added in a session.
- A dedicated «Готово» button or a typed exit word (both rejected in favor of
  menu-exit).
- Any change to flashcards grading or the listening/translation checks themselves.
