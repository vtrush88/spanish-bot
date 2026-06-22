# Sticky Add-Mode — Design

**Date:** 2026-06-22
**Status:** approved (brainstorm) — pending implementation plan
**Components:** `handlers/add.py`, `handlers/menu.py`

## Goal

After tapping «➕ Добавить слово» once, the user stays in add-mode and can add
many words in a row, leaving only when they choose. Today the mode ends after a
single save, forcing a button tap before every new word.

## Motivation

The end user (mom) usually adds several words in one sitting. Re-tapping
«➕ Добавить слово» before each word is friction. The duplicate and preview paths
already keep the user in add-mode; this extends the same stickiness across the
save / skip steps and makes every menu button a clean one-tap exit.

## Current behavior

- `start_add` → state `AddCard.waiting_for_text`, prompt.
- `receive_text` (`AddCard.waiting_for_text, F.text`): menu-button guard → cancel +
  "нажми кнопку ещё раз"; enrich; duplicate → stay; else preview + voice +
  «Сохранить? [✅ Да] [❌ Нет]».
- `save_yes` / `save_no` callbacks → `state.clear()` → **exit add-mode**. This is
  why adding another word needs a fresh button tap.
- Router order (`bot.py`): `menu → add → training`. «📖 Мой словарь» (menu router)
  and «➕ Добавить слово» (add router, registered before `receive_text`) already
  switch in one tap. The three training buttons live in the *last* router, so
  `receive_text` intercepts them first → the "нажми кнопку ещё раз" double-tap.

## Desired behavior (UX)

1. Enter add-mode once; stay until the user leaves via the menu.
2. After ✅ Да: «Сохранено! ✅ Пиши следующее 🙂», stay in mode. The Да/Нет buttons
   are removed (the «Сохранить?» message is edited into this result).
3. After ❌ Нет: «Ок, пропускаю 🙂 Пиши следующее.», buttons removed, stay in mode.
4. Duplicate / enrichment error: stay in mode (already implemented).
5. Exit — any menu button leaves add-mode in **one tap**:
   - Training buttons (Карточки / Проверить себя / Аудирование) → switch to that mode.
   - «📖 Мой словарь» → show the list and leave add-mode (no mode active afterward).
   - «➕ Добавить слово» → re-enter add-mode (fresh prompt).

## Implementation

All changes in `handlers/add.py` unless noted.

1. **Stickiness.** Remove `state.clear()` from `save_yes` and `save_no`. The state
   stays `AddCard.waiting_for_text`, so the next text message routes back to
   `receive_text`.
2. **One-tap exit for training buttons.** Add `~F.text.in_(keyboards.MENU_BUTTONS)`
   to the decorators of `receive_text` and the catch-all `reject_non_text` — the
   same pattern already used by `check_translation` / `check_listen`. Training-button
   text then falls through add.router into training.router. Remove the now-dead
   menu-button guard block inside `receive_text`.
3. **«Мой словарь» exits (consistency).** `handlers/menu.py:show_vocab` gains a
   `state: FSMContext` parameter and calls `await state.clear()` before rendering.
   «Мой словарь» then leaves any active mode — add **or** training. This also fixes
   the latent training quirk where tapping «Мой словарь» mid-training left the user
   in the training state (so a following message was graded as an answer).
4. **Remove Да/Нет buttons + show result.** `save_yes` / `save_no` edit the
   «Сохранить?» message via `call.message.edit_text(...)` with no `reply_markup`
   (buttons disappear), wrapped in `try/except TelegramBadRequest` with a fallback to
   `call.message.answer(...)` (pattern from `menu.py:_remove_card_voice`).
5. **Read-once guard (stale button / double-tap).** `save_yes` / `save_no` read
   `card` from state, then immediately `await state.update_data(card=None)`. If
   `card` is `None` → `await call.answer("Эта карточка уже неактивна 🙂")` (toast)
   and return. Removing the buttons is the primary defense; read-once covers the
   rare double-callback race that loses the in-flight tap.
6. **Entry prompt.** `start_add` text sets the sticky expectation and names the exit.

## Wording

| Moment | Now | New |
|---|---|---|
| Entry (`start_add`) | «Напиши слово или фразу — на испанском или русском 🙂» | «Пиши слова по одному — я сохраню каждое 🙂 Когда закончишь, выбери что-нибудь в меню внизу.» |
| After ✅ Да | «Сохранено! ✅» | «Сохранено! ✅ Пиши следующее 🙂» |
| After ❌ Нет | «Ок, не сохраняю.» | «Ок, пропускаю 🙂 Пиши следующее.» |
| Stale Да | «Эта карточка уже неактивна 🙂» | unchanged |

All texts stay gender-neutral (one male user).

## Edge cases

- **Stale «✅ Да».** Buttons are removed on the first tap; read-once returns
  "уже неактивна" if a second callback still arrives.
- **Double-save race.** Two near-simultaneous taps could both read a non-`None`
  card before either clears it → at worst one duplicate card (deletable from
  «Мой словарь»). Accepted for a 3-user personal bot; not worth a storage lock.
- **Unfinished preview, then switch to training.** The pending `card` lingers in
  state data; training handlers ignore it; read-once prevents it being saved later.
- **Stateless free text** (after «Мой словарь» clears state): no handler matches →
  silently ignored, identical to the idle main-menu state today.

## Testing

Handlers are verified manually per project convention (`AGENTS.md`); there is no new
pure logic to unit-test. Run the existing suite (`pytest -q`, 80 green) to confirm no
regression, then a manual pass on the server:

- add two words back-to-back without re-tapping «➕ Добавить слово»;
- after a save, confirm the Да/Нет buttons are gone;
- exit via each menu button (3 training + «Мой словарь» + re-tap «Добавить слово») —
  each in one tap;
- tap a stale «✅ Да» from an earlier card → "уже неактивна".

## Out of scope

- Counting / announcing how many words were added in a session.
- A dedicated «Готово» button or a typed exit word (both rejected in favor of
  menu-exit).
- Any change to flashcards grading or the listening/translation checks themselves.
