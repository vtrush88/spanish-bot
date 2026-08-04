# Language Profiles (English Bot) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Обобщить бота до языковых профилей (`BOT_LANG` в `.env`), чтобы задеплоить второй, английский бот тем же кодом — не меняя поведение живого испанского бота ни на байт.

**Architecture:** Новый модуль `languages.py` держит per-language профиль (голос, промпты, схемы Gemini, key map, UI-строки); сервисы и хендлеры получают профиль через aiogram-DI (`dp["profile"]`). Колонки БД переименовываются на нейтральные с идемпотентной поколоночной автомиграцией в `init_db`. Деплой-артефакты (systemd-юнит, бэкап-скрипт) параметризуются под два инстанса.

**Tech Stack:** Python 3.12 · aiogram 3.13.1 · SQLite (stdlib) · google-genai 2.8.0 · edge-tts 7.2.8 · pytest + pytest-asyncio.

**Спека:** `docs/superpowers/specs/2026-08-04-english-bot-language-profiles-design.md` (ревью раунд 1 пройден 2026-08-04).

## Global Constraints

- **Инвариант мамы:** es-профиль байт-в-байт равен сегодняшним литералам — все UI-строки, оба SYSTEM-промпта, обе схемы Gemini, user-шаблон grading. Литералы в Task 1 скопированы из текущего кода дословно — НЕ редактировать, НЕ «улучшать», НЕ менять пробелы/эмодзи.
- **Ключи внутри приложения — только нейтральные:** колонки `word`, `translation`, `example`, `example_translation`; ключи сервисов те же + `correct` (grading). Старые имена (`spanish`, `russian`, `example_es`, `example_ru`, `correct_spanish`) после Task 5 не должны встречаться нигде, кроме `languages.py` (es-схемы/промпты/key map) и тестов миграции/профилей.
- **Миграция БД:** DDL в python-sqlite3 автокоммитится — транзакцией переименования не оборачивать; гард строго поколоночный (идемпотентный, крэш-безопасный).
- **Зависимости не трогаем:** `google-genai==2.8.0` (пин из-за pydantic-конфликта с aiogram 3.13.1), ничего нового в requirements.txt.
- **Тексты бота — гендер-нейтральные** (и в новых en-промптах: «Пол ученика неизвестен…» сохраняется).
- Работаем в этом репо на ветке `language-profiles`, БЕЗ git-worktree (репо вложено в Obsidian-vault, worktree положить некуда). Создать в начале: `git checkout -b language-profiles`.
- После каждой задачи: `.venv/bin/pytest -q` зелёный И `.venv/bin/python -c "import bot"` без ошибок.
- Коммиты БЕЗ подписи (глобальный `gpgsign=false`, репо не lidofinance; не добавлять `-S`). Разрешение Victoria на коммиты этого плана получено батчем при запуске исполнения (правило 2026-08-04); permission-хук всё равно может спрашивать — это нормально.

---

### Task 1: Модуль языковых профилей `languages.py`

**Files:**
- Create: `languages.py`
- Test: `tests/test_languages.py`

**Interfaces:**
- Produces: `LanguageProfile` (frozen dataclass) с полями
  `code: str`, `tts_voice: str`, `enrichment_system: str`,
  `enrichment_schema: dict`, `grading_system: str`, `grading_schema: dict`,
  `grading_user_template: str` (форматируется `.format(prompt_ru=…, expected=…, answer=…)`),
  `llm_key_map: dict[str, str]` (ключ ответа модели → нейтральный ключ; отсутствующие в словаре ключи проходят как есть),
  `greeting: str`, `add_intro: str`, `translate_question: str` (шаблон с `{}`);
  `PROFILES: dict[str, LanguageProfile]` с ключами `"es"` и `"en"`.
- Consumes: ничего (лист-модуль без зависимостей от проекта).

- [ ] **Step 1: Написать падающий тест**

`tests/test_languages.py` (файл целиком):

```python
"""Профили языков. Главный тест — регрессия мамы: es-профиль байт-в-байт
равен литералам, которые жили в services/enrichment.py, services/grading.py,
handlers/menu.py, handlers/add.py, handlers/training.py, services/tts.py
до обобщения. Эталоны скопированы сюда дословно — НЕ переформатировать."""
from __future__ import annotations

import languages
from languages import PROFILES

ES_ENRICHMENT_SYSTEM = (
    "Ты помогаешь русскоязычному новичку учить испанский язык Испании "
    "(европейский, кастильский — НЕ латиноамериканский вариант). "
    "На вход даётся слово или фраза на испанском ИЛИ на русском. "
    "Определи язык. Верни испанский вариант (spanish) в варианте Испании — "
    "используй пиренейскую лексику (coche, ordenador, móvil, zumo, vale, "
    "vosotros и т.п.), НЕ латиноамериканскую (carro, computadora, celular, jugo). "
    "Дай русский перевод (russian). "
    "transcription — произношение ТОЛЬКО русскими буквами, с ударением "
    "(ударную гласную пиши заглавной). Передавай звуки ЕДИНООБРАЗНО: "
    "ll и y → «й» (calle→кАйе, llave→йАвэ, pollo→пОйо, paella→паЭйя, lluvia→йУвиа); "
    "ñ → «нь» (España→эспАнья, año→Аньо); "
    "j, и g перед e/i → «х» (jamón→хамОн, gente→хЭнте); "
    "h не читается (hola→Ола); "
    "c и z перед e/i → «с» без межзубного (cerveza→сервЭса, gracias→грАсиас). "
    "Добавь короткий "
    "пример-предложение на испанском Испании (example_es) с переводом (example_ru). "
    "Поле kind = 'word' для одного слова, 'phrase' для фразы/предложения. "
    "Всё кратко и для начинающего."
)

ES_ENRICHMENT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "kind": {"type": "STRING", "enum": ["word", "phrase"]},
        "spanish": {"type": "STRING"},
        "russian": {"type": "STRING"},
        "transcription": {"type": "STRING"},
        "example_es": {"type": "STRING"},
        "example_ru": {"type": "STRING"},
    },
    "required": ["kind", "spanish", "russian", "transcription",
                 "example_es", "example_ru"],
}

ES_GRADING_SYSTEM = (
    "Ты мягко проверяешь, как русскоязычный новичок перевёл слово/фразу на "
    "испанский. Тебе дают: русский запрос, ожидаемый испанский перевод и ответ "
    "ученика. Оцени verdict: 'correct' (всё верно), 'typo' (правильно по сути, "
    "но мелкая опечатка или пропущенный акцент), 'wrong' (неверно). В "
    "correct_spanish дай правильное написание. В note — короткая ДОБАВЛЯЮЩАЯ "
    "подсказка по-русски: для 'typo'/'wrong' — что именно не так (например "
    "«пропущен акцент», «лишняя буква», «это слово значит …»); для 'correct' — "
    "короткое ободрение или крошечный факт. НЕ дублируй вердикт: слова «верно», "
    "«правильно», «почти» ученик уже видит отдельно, в note их не повторяй. "
    "Пол ученика неизвестен — без гендерных форм в его адрес "
    "(не «написала», «умница»)."
)

ES_GRADING_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "verdict": {"type": "STRING", "enum": ["correct", "typo", "wrong"]},
        "correct_spanish": {"type": "STRING"},
        "note": {"type": "STRING"},
    },
    "required": ["verdict", "correct_spanish", "note"],
}

ES_GRADING_USER_TEMPLATE = (
    "Русский запрос: {prompt_ru}\n"
    "Ожидаемый испанский: {expected}\n"
    "Ответ ученика: {answer}"
)

ES_GREETING = (
    "¡Hola! 🌞 Я помогу учить испанский.\n\n"
    "• «➕ Добавить слово» — пришли слово или фразу, я переведу, озвучу и "
    "запомню.\n"
    "• «🎴 Карточки», «✍️ Проверить себя», «🎧 Аудирование» — тренировки.\n"
    "• «📖 Мой словарь» — все добавленные слова."
)

ES_ADD_INTRO = (
    "Пиши слова или фразы — по одному, на испанском или русском 🙂 "
    "Я сохраню каждое. Когда закончишь, выбери что-нибудь в меню внизу."
)


def test_es_profile_is_byte_identical_to_legacy_literals():
    es = PROFILES["es"]
    assert es.code == "es"
    assert es.tts_voice == "es-ES-XimenaNeural"
    assert es.enrichment_system == ES_ENRICHMENT_SYSTEM
    assert es.enrichment_schema == ES_ENRICHMENT_SCHEMA
    assert es.grading_system == ES_GRADING_SYSTEM
    assert es.grading_schema == ES_GRADING_SCHEMA
    assert es.grading_user_template == ES_GRADING_USER_TEMPLATE
    assert es.greeting == ES_GREETING
    assert es.add_intro == ES_ADD_INTRO
    assert es.translate_question == "Как по-испански: «{}»?"


def test_es_key_map_translates_legacy_llm_keys():
    m = PROFILES["es"].llm_key_map
    assert m == {
        "spanish": "word",
        "russian": "translation",
        "example_es": "example",
        "example_ru": "example_translation",
        "correct_spanish": "correct",
    }


def test_en_profile_basics():
    en = PROFILES["en"]
    assert en.code == "en"
    assert en.tts_voice == "en-US-EmmaNeural"
    assert en.llm_key_map == {}  # ключи en-схем уже нейтральные
    assert "IPA" in en.enrichment_system
    assert "американ" in en.enrichment_system.lower()
    assert "русскими буквами" in en.enrichment_system  # запрет упомянут явно
    assert set(en.enrichment_schema["properties"]) == {
        "kind", "word", "translation", "transcription",
        "example", "example_translation",
    }
    assert set(en.grading_schema["properties"]) == {"verdict", "correct", "note"}
    assert en.translate_question == "Как по-английски: «{}»?"
    assert "Ожидаемый английский" in en.grading_user_template


def test_profiles_are_complete_and_wellformed():
    assert set(PROFILES) == {"es", "en"}
    for profile in PROFILES.values():
        for field in ("code", "tts_voice", "enrichment_system", "grading_system",
                      "grading_user_template", "greeting", "add_intro",
                      "translate_question"):
            assert getattr(profile, field), f"{profile.code}.{field} пуст"
        assert "{}" in profile.translate_question
        for placeholder in ("{prompt_ru}", "{expected}", "{answer}"):
            assert placeholder in profile.grading_user_template
        assert profile.enrichment_schema["required"] == list(
            profile.enrichment_schema["properties"])
        assert profile.grading_schema["required"] == list(
            profile.grading_schema["properties"])
        # note: гендер-нейтральность требуется в обоих grading-промптах
        assert "Пол ученика неизвестен" in profile.grading_system
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv/bin/pytest tests/test_languages.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'languages'`

- [ ] **Step 3: Написать `languages.py`**

Файл целиком. es-литералы — те же, что в тесте (копировать из текущих
`services/enrichment.py`, `services/grading.py`, `handlers/menu.py`,
`handlers/add.py`, дословно):

```python
"""Языковые профили: всё языкозависимое в одном месте.

Профиль выбирается конфигом (BOT_LANG) и внедряется через dp["profile"].
es-литералы обязаны быть байт-в-байт равны тем, что жили в сервисах и
хендлерах до обобщения (инвариант маминого бота) — их фиксирует
tests/test_languages.py. Не редактировать без сознательного решения
поменять поведение живого испанского бота.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageProfile:
    code: str
    tts_voice: str
    enrichment_system: str
    enrichment_schema: dict
    grading_system: str
    grading_schema: dict
    # .format(prompt_ru=…, expected=…, answer=…)
    grading_user_template: str
    # ключ ответа модели -> нейтральный ключ приложения; прочие ключи as-is
    llm_key_map: dict
    greeting: str
    add_intro: str
    translate_question: str  # шаблон с {}


ES = LanguageProfile(
    code="es",
    tts_voice="es-ES-XimenaNeural",
    enrichment_system=(
        "Ты помогаешь русскоязычному новичку учить испанский язык Испании "
        "(европейский, кастильский — НЕ латиноамериканский вариант). "
        "На вход даётся слово или фраза на испанском ИЛИ на русском. "
        "Определи язык. Верни испанский вариант (spanish) в варианте Испании — "
        "используй пиренейскую лексику (coche, ordenador, móvil, zumo, vale, "
        "vosotros и т.п.), НЕ латиноамериканскую (carro, computadora, celular, jugo). "
        "Дай русский перевод (russian). "
        "transcription — произношение ТОЛЬКО русскими буквами, с ударением "
        "(ударную гласную пиши заглавной). Передавай звуки ЕДИНООБРАЗНО: "
        "ll и y → «й» (calle→кАйе, llave→йАвэ, pollo→пОйо, paella→паЭйя, lluvia→йУвиа); "
        "ñ → «нь» (España→эспАнья, año→Аньо); "
        "j, и g перед e/i → «х» (jamón→хамОн, gente→хЭнте); "
        "h не читается (hola→Ола); "
        "c и z перед e/i → «с» без межзубного (cerveza→сервЭса, gracias→грАсиас). "
        "Добавь короткий "
        "пример-предложение на испанском Испании (example_es) с переводом (example_ru). "
        "Поле kind = 'word' для одного слова, 'phrase' для фразы/предложения. "
        "Всё кратко и для начинающего."
    ),
    enrichment_schema={
        "type": "OBJECT",
        "properties": {
            "kind": {"type": "STRING", "enum": ["word", "phrase"]},
            "spanish": {"type": "STRING"},
            "russian": {"type": "STRING"},
            "transcription": {"type": "STRING"},
            "example_es": {"type": "STRING"},
            "example_ru": {"type": "STRING"},
        },
        "required": ["kind", "spanish", "russian", "transcription",
                     "example_es", "example_ru"],
    },
    grading_system=(
        "Ты мягко проверяешь, как русскоязычный новичок перевёл слово/фразу на "
        "испанский. Тебе дают: русский запрос, ожидаемый испанский перевод и ответ "
        "ученика. Оцени verdict: 'correct' (всё верно), 'typo' (правильно по сути, "
        "но мелкая опечатка или пропущенный акцент), 'wrong' (неверно). В "
        "correct_spanish дай правильное написание. В note — короткая ДОБАВЛЯЮЩАЯ "
        "подсказка по-русски: для 'typo'/'wrong' — что именно не так (например "
        "«пропущен акцент», «лишняя буква», «это слово значит …»); для 'correct' — "
        "короткое ободрение или крошечный факт. НЕ дублируй вердикт: слова «верно», "
        "«правильно», «почти» ученик уже видит отдельно, в note их не повторяй. "
        "Пол ученика неизвестен — без гендерных форм в его адрес "
        "(не «написала», «умница»)."
    ),
    grading_schema={
        "type": "OBJECT",
        "properties": {
            "verdict": {"type": "STRING", "enum": ["correct", "typo", "wrong"]},
            "correct_spanish": {"type": "STRING"},
            "note": {"type": "STRING"},
        },
        "required": ["verdict", "correct_spanish", "note"],
    },
    grading_user_template=(
        "Русский запрос: {prompt_ru}\n"
        "Ожидаемый испанский: {expected}\n"
        "Ответ ученика: {answer}"
    ),
    llm_key_map={
        "spanish": "word",
        "russian": "translation",
        "example_es": "example",
        "example_ru": "example_translation",
        "correct_spanish": "correct",
    },
    greeting=(
        "¡Hola! 🌞 Я помогу учить испанский.\n\n"
        "• «➕ Добавить слово» — пришли слово или фразу, я переведу, озвучу и "
        "запомню.\n"
        "• «🎴 Карточки», «✍️ Проверить себя», «🎧 Аудирование» — тренировки.\n"
        "• «📖 Мой словарь» — все добавленные слова."
    ),
    add_intro=(
        "Пиши слова или фразы — по одному, на испанском или русском 🙂 "
        "Я сохраню каждое. Когда закончишь, выбери что-нибудь в меню внизу."
    ),
    translate_question="Как по-испански: «{}»?",
)

EN = LanguageProfile(
    code="en",
    tts_voice="en-US-EmmaNeural",
    enrichment_system=(
        "Ты помогаешь русскоязычному ученику среднего уровня (B1-B2) учить "
        "американский английский. На вход даётся слово или фраза на английском "
        "ИЛИ на русском. Определи язык. Верни английский вариант (word) в "
        "американском варианте — американская лексика и спеллинг (apartment, "
        "elevator, color, fall, cookie), НЕ британские (flat, lift, colour, "
        "autumn, biscuit). Дай русский перевод (translation). "
        "transcription — транскрипция IPA в слэшах, вариант General American, "
        "со знаком ударения ˈ для многосложных слов: thought → /θɔːt/, "
        "apartment → /əˈpɑːrtmənt/, comfortable → /ˈkʌmftərbəl/. "
        "НЕ русскими буквами и НЕ британское произношение. "
        "Добавь пример-предложение на английском (example) уровнем чуть выше "
        "среднего (B2+): живые разговорные конструкции, фразовые глаголы, "
        "естественные коллокации — и его русский перевод (example_translation). "
        "Перевод и пояснения — простые, по-русски. "
        "Поле kind = 'word' для одного слова, 'phrase' для фразы/предложения. "
        "Всё кратко."
    ),
    enrichment_schema={
        "type": "OBJECT",
        "properties": {
            "kind": {"type": "STRING", "enum": ["word", "phrase"]},
            "word": {"type": "STRING"},
            "translation": {"type": "STRING"},
            "transcription": {"type": "STRING"},
            "example": {"type": "STRING"},
            "example_translation": {"type": "STRING"},
        },
        "required": ["kind", "word", "translation", "transcription",
                     "example", "example_translation"],
    },
    grading_system=(
        "Ты мягко проверяешь, как русскоязычный ученик перевёл слово/фразу на "
        "английский. Тебе дают: русский запрос, ожидаемый английский перевод и "
        "ответ ученика. Оцени verdict: 'correct' (всё верно), 'typo' (правильно "
        "по сути, но мелкая опечатка — пропущенный апостроф, удвоенная или "
        "пропущенная буква, неверное окончание), 'wrong' (неверно). В correct "
        "дай правильное написание. В note — короткая ДОБАВЛЯЮЩАЯ подсказка "
        "по-русски: для 'typo'/'wrong' — что именно не так (например «пропущен "
        "апостроф», «лишняя буква», «это слово значит …»); для 'correct' — "
        "короткое ободрение или крошечный факт. НЕ дублируй вердикт: слова "
        "«верно», «правильно», «почти» ученик уже видит отдельно, в note их не "
        "повторяй. Пол ученика неизвестен — без гендерных форм в его адрес "
        "(не «написала», «умница»)."
    ),
    grading_schema={
        "type": "OBJECT",
        "properties": {
            "verdict": {"type": "STRING", "enum": ["correct", "typo", "wrong"]},
            "correct": {"type": "STRING"},
            "note": {"type": "STRING"},
        },
        "required": ["verdict", "correct", "note"],
    },
    grading_user_template=(
        "Русский запрос: {prompt_ru}\n"
        "Ожидаемый английский: {expected}\n"
        "Ответ ученика: {answer}"
    ),
    llm_key_map={},
    greeting=(
        "Hi! 🌞 Я помогу учить английский.\n\n"
        "• «➕ Добавить слово» — пришли слово или фразу, я переведу, озвучу и "
        "запомню.\n"
        "• «🎴 Карточки», «✍️ Проверить себя», «🎧 Аудирование» — тренировки.\n"
        "• «📖 Мой словарь» — все добавленные слова."
    ),
    add_intro=(
        "Пиши слова или фразы — по одному, на английском или русском 🙂 "
        "Я сохраню каждое. Когда закончишь, выбери что-нибудь в меню внизу."
    ),
    translate_question="Как по-английски: «{}»?",
)

PROFILES: dict[str, LanguageProfile] = {"es": ES, "en": EN}
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/pytest tests/test_languages.py -q` → PASS; затем `.venv/bin/pytest -q` → все зелёные (существующие тесты не затронуты).

- [ ] **Step 5: Commit**

```bash
git add languages.py tests/test_languages.py
git commit -m "feat: language profiles module (es byte-identical, en with IPA/American)"
```

---

### Task 2: Нейтральные колонки БД + автомиграция

**Files:**
- Modify: `db.py`
- Test: `tests/test_db_migration.py` (новый), `tests/test_db_basic.py`, `tests/test_db_review.py`, `tests/test_backup_script.py` (только `_seed_db`)

**Interfaces:**
- Produces: `add_card(conn, *, user_id, kind, word, translation, transcription, example, example_translation, enriched, today) -> int`;
  `update_enrichment(conn, card_id, *, translation, transcription, example, example_translation)`;
  `card_exists(conn, user_id, word) -> bool`; строки карточек с колонками
  `word`, `translation`, `example`, `example_translation` (остальные без изменений).
- Consumes: ничего из Task 1.

- [ ] **Step 1: Написать падающие тесты миграции**

`tests/test_db_migration.py` (файл целиком):

```python
"""Автомиграция испаноязычных имён колонок на нейтральные.

Гард поколоночный: DDL в python-sqlite3 автокоммитится, транзакцией четыре
RENAME не обернуть — поэтому каждая колонка проверяется и переименовывается
отдельно, а упавшая на середине миграция дозавершается следующим запуском."""
from datetime import date

import db

OLD_SCHEMA = """
CREATE TABLE cards (
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

NEW_COLUMNS = {"word", "translation", "example", "example_translation"}
OLD_COLUMNS = {"spanish", "russian", "example_es", "example_ru"}


def _columns(conn):
    return {row[1] for row in conn.execute("PRAGMA table_info(cards)")}


def _make_old_db(path):
    conn = db.connect(str(path))
    conn.executescript(OLD_SCHEMA)
    conn.execute(
        "INSERT INTO cards (user_id, kind, spanish, russian, transcription,"
        " example_es, example_ru, created_at, due_at, interval_days, reps,"
        " lapses) VALUES (1, 'word', 'mesa', 'стол', 'мЭса',"
        " 'La mesa es grande.', 'Стол большой.', '2026-06-01', '2026-08-01',"
        " 7, 3, 1)")
    conn.commit()
    return conn


def test_migrates_old_schema_and_keeps_data(tmp_path):
    conn = _make_old_db(tmp_path / "old.db")
    db.init_db(conn)
    cols = _columns(conn)
    assert NEW_COLUMNS <= cols
    assert not (OLD_COLUMNS & cols)
    row = conn.execute("SELECT * FROM cards").fetchone()
    assert row["word"] == "mesa"
    assert row["translation"] == "стол"
    assert row["example"] == "La mesa es grande."
    assert row["example_translation"] == "Стол большой."
    # SRS-поля пережили миграцию
    assert (row["interval_days"], row["reps"], row["lapses"]) == (7, 3, 1)
    assert row["due_at"] == "2026-08-01"


def test_migration_is_idempotent(tmp_path):
    conn = _make_old_db(tmp_path / "old.db")
    db.init_db(conn)
    db.init_db(conn)  # повторный запуск — no-op, не падает
    assert NEW_COLUMNS <= _columns(conn)


def test_partial_migration_completes_on_next_start(tmp_path):
    # «крэш на середине»: первая колонка уже переименована, остальные нет
    conn = _make_old_db(tmp_path / "old.db")
    conn.execute("ALTER TABLE cards RENAME COLUMN spanish TO word")
    db.init_db(conn)
    cols = _columns(conn)
    assert NEW_COLUMNS <= cols
    assert not (OLD_COLUMNS & cols)
    row = conn.execute("SELECT * FROM cards").fetchone()
    assert row["word"] == "mesa" and row["translation"] == "стол"


def test_fresh_db_gets_new_names(tmp_path):
    conn = db.connect(str(tmp_path / "fresh.db"))
    db.init_db(conn)
    cols = _columns(conn)
    assert NEW_COLUMNS <= cols
    assert not (OLD_COLUMNS & cols)


def test_add_and_read_roundtrip_with_new_names(tmp_path):
    conn = db.connect(str(tmp_path / "fresh.db"))
    db.init_db(conn)
    card_id = db.add_card(
        conn, user_id=1, kind="word", word="mesa", translation="стол",
        transcription="мЭса", example="La mesa.", example_translation="Стол.",
        enriched=True, today=date(2026, 8, 4))
    row = db.get_card(conn, card_id)
    assert row["word"] == "mesa"
    assert db.card_exists(conn, 1, "MESA")  # регистронезависимость сохранена
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/pytest tests/test_db_migration.py -q`
Expected: FAIL — в `init_db` нет миграции (старые колонки остаются) и `add_card` не принимает `word=`.

- [ ] **Step 3: Обновить `db.py`**

3a. `SCHEMA` — новые имена колонок (строки 11-15 текущего файла):

```sql
    word           TEXT NOT NULL,
    translation    TEXT,
    transcription  TEXT,
    example        TEXT,
    example_translation TEXT,
```

3b. Миграция перед `executescript` (новый код над `init_db`):

```python
_COLUMN_RENAMES = (
    ("spanish", "word"),
    ("russian", "translation"),
    ("example_es", "example"),
    ("example_ru", "example_translation"),
)


def _migrate_column_names(conn: sqlite3.Connection) -> None:
    """Разовое переименование испаноязычных колонок (деплой 2026-08).

    Поколоночный гард, НЕ транзакция: DDL в python-sqlite3 автокоммитится,
    поэтому атомарности всё равно нет — зато каждая проверка идемпотентна,
    и прерванная миграция дозавершается при следующем старте.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(cards)")}
    if not cols:
        return  # свежая база: таблицы ещё нет, создастся сразу с новыми именами
    for old, new in _COLUMN_RENAMES:
        if old in cols:
            conn.execute(f"ALTER TABLE cards RENAME COLUMN {old} TO {new}")


def init_db(conn: sqlite3.Connection) -> None:
    _migrate_column_names(conn)
    conn.executescript(SCHEMA)
    conn.commit()
```

3c. Переименовать поля в остальных функциях `db.py` (kwargs и SQL):
- `add_card`: параметры `word`, `translation`, `example`, `example_translation`; список колонок в INSERT соответственно.
- `update_enrichment`: параметры `translation`, `transcription`, `example`, `example_translation`; SET-список соответственно.
- `card_exists(conn, user_id, word)`: `target = word.strip().lower()`, `SELECT word FROM cards …`, сравнение `r["word"]`. Докстринг: заменить «Spanish word» на «target-language word».

- [ ] **Step 4: Обновить существующие тесты под новые имена**

- `tests/test_db_basic.py`, `tests/test_db_review.py`: заменить kwargs
  `spanish=`→`word=`, `russian=`→`translation=`, `example_es=`→`example=`,
  `example_ru=`→`example_translation=`; чтения `row["spanish"]`→`row["word"]`
  и т.п. Логика и значения тестов не меняются.
- `tests/test_backup_script.py`, функция `_seed_db`: те же замены kwargs.

- [ ] **Step 5: Прогнать всё**

Run: `.venv/bin/pytest -q`
Expected: PASS (упадут только если где-то остались старые kwargs — `grep -rn "spanish=" tests/` должен быть пуст).

- [ ] **Step 6: Commit**

```bash
git add db.py tests/test_db_migration.py tests/test_db_basic.py tests/test_db_review.py tests/test_backup_script.py
git commit -m "feat: neutral card columns (word/translation/example/*) + idempotent per-column auto-migration"
```

---

### Task 3: Сервисы enrichment/grading — профиль вместо вшитого испанского

**Files:**
- Modify: `services/enrichment.py`, `services/grading.py`
- Test: `tests/test_enrichment.py`, `tests/test_grading.py`

**Interfaces:**
- Consumes: `languages.LanguageProfile`, `languages.PROFILES` (Task 1); `llm_service.generate_json` (без изменений).
- Produces: `enrich(llm, profile, text) -> dict` с ключами
  `("kind", "word", "translation", "transcription", "example", "example_translation")`;
  `grade(llm, profile, *, prompt_ru, expected, answer) -> dict` с ключами
  `("verdict", "correct", "note")`; `answers_match` — без изменений;
  исключения `EnrichmentError`/`GradingError` — без изменений.

- [ ] **Step 1: Обновить тесты enrichment (падающие)**

В `tests/test_enrichment.py`:

```python
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.genai import errors

from languages import PROFILES
from services import enrichment, llm

ES = PROFILES["es"]
EN = PROFILES["en"]

# ответ МОДЕЛИ на es-профиле — старые ключи (их требует es-схема)
GOOD_ES_RESPONSE = {
    "kind": "word",
    "spanish": "comida",
    "russian": "еда",
    "transcription": "комИда",
    "example_es": "La comida está lista.",
    "example_ru": "Еда готова.",
}

# что enrich обязан вернуть приложению — нейтральные ключи
GOOD_NEUTRAL = {
    "kind": "word",
    "word": "comida",
    "translation": "еда",
    "transcription": "комИда",
    "example": "La comida está lista.",
    "example_translation": "Еда готова.",
}
```

Все вызовы `enrichment.enrich(_llm(client), "comida")` →
`enrichment.enrich(_llm(client), ES, "comida")`; ожидания `== GOOD` →
`== GOOD_NEUTRAL`; `result["spanish"]` → `result["word"]`;
`incomplete` строится из `GOOD_ES_RESPONSE`. Плюс два новых теста:

```python
def test_enrich_sends_profile_prompt_and_schema():
    client = MagicMock()
    client.models.generate_content.return_value = _resp(GOOD_ES_RESPONSE)
    enrichment.enrich(_llm(client), ES, "comida")
    cfg = client.models.generate_content.call_args.kwargs["config"]
    assert cfg.system_instruction == ES.enrichment_system
    assert cfg.response_schema == ES.enrichment_schema


def test_enrich_en_profile_accepts_neutral_response_keys():
    client = MagicMock()
    client.models.generate_content.return_value = _resp(GOOD_NEUTRAL)
    assert enrichment.enrich(_llm(client), EN, "food") == GOOD_NEUTRAL
```

- [ ] **Step 2: Убедиться, что падают** — `.venv/bin/pytest tests/test_enrichment.py -q` → FAIL (старая сигнатура).

- [ ] **Step 3: Переписать `services/enrichment.py`**

Файл целиком (SYSTEM/SCHEMA уезжают в профиль):

```python
from __future__ import annotations

from languages import LanguageProfile
from services import llm as llm_service

REQUIRED_KEYS = (
    "kind", "word", "translation", "transcription", "example",
    "example_translation",
)


class EnrichmentError(Exception):
    pass


def enrich(llm: llm_service.LLM, profile: LanguageProfile, text: str) -> dict:
    last_error = None
    for _ in range(2):
        data = llm_service.generate_json(
            llm, system=profile.enrichment_system,
            schema=profile.enrichment_schema, text=text, max_output_tokens=512)
        if data is not None:
            mapped = {profile.llm_key_map.get(k, k): v for k, v in data.items()}
            if all(k in mapped and mapped[k] for k in REQUIRED_KEYS):
                return {k: mapped[k] for k in REQUIRED_KEYS}
        last_error = "модель вернула ответ без валидной JSON-карточки"
    raise EnrichmentError(last_error or "enrichment failed")
```

- [ ] **Step 4: То же для grading**

`tests/test_grading.py`: вызовы → `grading.grade(_llm(client), ES, prompt_ru=…, expected=…, answer=…)`; ответ модели в моках — с ключом `correct_spanish` (es-схема), ожидания — с ключом `correct`; `answers_match`-тесты не трогать. Добавить тест, что user-сообщение собрано из шаблона профиля:

```python
def test_grade_builds_user_message_from_profile_template():
    client = MagicMock()
    client.models.generate_content.return_value = _resp(
        {"verdict": "correct", "correct_spanish": "mesa", "note": "ок"})
    grading.grade(_llm(client), ES, prompt_ru="стол", expected="mesa",
                  answer="mesa")
    sent = client.models.generate_content.call_args.kwargs["contents"]
    assert sent == "Русский запрос: стол\nОжидаемый испанский: mesa\nОтвет ученика: mesa"
```

`services/grading.py` — новая версия значимой части (SYSTEM/SCHEMA удаляются,
`answers_match` не трогать):

```python
from __future__ import annotations

from languages import LanguageProfile
from services import llm as llm_service

REQUIRED_KEYS = ("verdict", "correct", "note")
VALID_VERDICTS = ("correct", "typo", "wrong")


class GradingError(Exception):
    pass


def grade(llm: llm_service.LLM, profile: LanguageProfile, *, prompt_ru: str,
          expected: str, answer: str) -> dict:
    user = profile.grading_user_template.format(
        prompt_ru=prompt_ru, expected=expected, answer=answer)
    last_error = None
    for _ in range(2):
        data = llm_service.generate_json(
            llm, system=profile.grading_system, schema=profile.grading_schema,
            text=user, max_output_tokens=256)
        if data is not None:
            mapped = {profile.llm_key_map.get(k, k): v for k, v in data.items()}
            if (all(k in mapped and mapped[k] for k in REQUIRED_KEYS)
                    and mapped["verdict"] in VALID_VERDICTS):
                return {k: mapped[k] for k in REQUIRED_KEYS}
        last_error = "модель вернула ответ без валидной JSON-оценки"
    raise GradingError(last_error or "grading failed")
```

- [ ] **Step 5: Прогнать всё** — `.venv/bin/pytest -q` → PASS. Примечание: `handlers/add.py` и `handlers/training.py` в этот момент ещё зовут сервисы по старым сигнатурам — это чинится в Task 5; тесты хендлеров мокают сервисы целиком, поэтому остаются зелёными, а `import bot` не выполняет вызовов.

- [ ] **Step 6: Commit**

```bash
git add services/enrichment.py services/grading.py tests/test_enrichment.py tests/test_grading.py
git commit -m "feat: enrichment/grading take a language profile; neutral response keys"
```

---

### Task 4: tts/voice/formatting — голос из профиля, нейтральные ключи

**Files:**
- Modify: `services/tts.py`, `voice.py`, `formatting.py`
- Test: `tests/test_tts.py`, `tests/test_formatting.py`

**Interfaces:**
- Consumes: строки карточек с нейтральными колонками (Task 2).
- Produces: `tts.synthesize(text, voice, out_path) -> str`;
  `voice.send_card_voice(message, conn, card, voice) -> Message | None`;
  `formatting.card_preview/answer_reveal/word_list_line` читают
  `card["word"]`, `card["translation"]`, `card["example"]`, `card["example_translation"]`.

- [ ] **Step 1: Обновить тесты (падающие)**

- `tests/test_tts.py`: вызовы `tts.synthesize(text, path)` →
  `tts.synthesize(text, "es-ES-XimenaNeural", path)`; проверка, что
  `edge_tts.Communicate` вызван с переданным голосом (в мок-тесте:
  `Communicate.assert_called_once_with(text, "es-ES-XimenaNeural")`).
- `tests/test_formatting.py`: словари карточек и ожидания — на нейтральные
  ключи (`spanish`→`word`, `russian`→`translation`, `example_es`→`example`,
  `example_ru`→`example_translation`). Тексты-эталоны (лейблы «произношение:»,
  «пример:» и т.д.) НЕ меняются.

- [ ] **Step 2: Убедиться, что падают** — `.venv/bin/pytest tests/test_tts.py tests/test_formatting.py -q` → FAIL.

- [ ] **Step 3: Реализация**

- `services/tts.py`: удалить константу `VOICE`; сигнатура
  `async def synthesize(text: str, voice: str, out_path: str) -> str`;
  `edge_tts.Communicate(text, voice)`. Докстринг: «Сгенерировать озвучку (mp3)
  голосом voice. Возвращает путь.»
- `voice.py`: сигнатура `send_card_voice(message, conn, card, voice)`;
  внутри `tts.synthesize(card["word"], voice, tmp)`.
- `formatting.py`: ключи `card['word']`, `card['translation']`,
  `card['example']`, `card['example_translation']` в `card_preview`;
  `card['translation']` в `answer_reveal`; `card['word']`/`card['translation']`
  в `word_list_line`. Докстринг `card_preview`: «The Spanish word is bold» →
  «The target-language word is bold».

- [ ] **Step 4: Прогнать всё** — `.venv/bin/pytest -q` → PASS (вызовы в хендлерах чинятся в Task 5; их тесты мокают эти модули).

- [ ] **Step 5: Commit**

```bash
git add services/tts.py voice.py formatting.py tests/test_tts.py tests/test_formatting.py
git commit -m "feat: voice param for tts, neutral card keys in formatting/voice"
```

---

### Task 5: Проводка — config, bot.py, хендлеры

**Files:**
- Modify: `config.py`, `bot.py`, `handlers/menu.py`, `handlers/add.py`, `handlers/training.py`
- Test: `tests/test_config.py`, `tests/test_handlers_quota.py`

**Interfaces:**
- Consumes: `languages.PROFILES` (Task 1), сервисы (Task 3), `voice`/`tts`/`formatting` (Task 4), db (Task 2).
- Produces: `Config.bot_lang: str`; `dp["profile"]`; хендлеры с параметром `profile: LanguageProfile` (aiogram DI по имени).

- [ ] **Step 1: Тесты config (падающие)**

В `tests/test_config.py`, в стиле существующих тестов файла (тот же способ
подготовки env — посмотреть на месте и переиспользовать фикстуру/хелпер):

```python
def test_bot_lang_defaults_to_es(...):
    # env без BOT_LANG
    assert config.load().bot_lang == "es"


def test_bot_lang_en_is_picked_up(...):
    # BOT_LANG=en
    assert config.load().bot_lang == "en"


def test_bot_lang_unknown_raises(...):
    # BOT_LANG=de
    with pytest.raises(ValueError, match="BOT_LANG"):
        config.load()


def test_bot_lang_empty_string_falls_back_to_es(...):
    # BOT_LANG=  (пустая строка в .env не должна ронять старт)
    assert config.load().bot_lang == "es"
```

- [ ] **Step 2: Убедиться, что падают** — `.venv/bin/pytest tests/test_config.py -q` → FAIL (`bot_lang` нет).

- [ ] **Step 3: config.py**

```python
import languages  # вверху файла

# в dataclass Config:
    bot_lang: str

# в load(), перед return:
    bot_lang = os.environ.get("BOT_LANG") or "es"
    if bot_lang not in languages.PROFILES:
        raise ValueError(
            f"Unknown BOT_LANG: {bot_lang!r} (known: {sorted(languages.PROFILES)})")
# и bot_lang=bot_lang в конструкторе Config.
```

- [ ] **Step 4: bot.py**

```python
import languages  # к импортам

# после dp["llm"] = ...:
    dp["profile"] = languages.PROFILES[cfg.bot_lang]
```

- [ ] **Step 5: Хендлеры**

`handlers/menu.py`:
- удалить константу `GREETING`;
- `from languages import LanguageProfile` (для аннотаций);
- `cmd_start(message, state, profile: LanguageProfile)` → `message.answer(profile.greeting, reply_markup=keyboards.main_menu())`;
- `show_card(call, state, conn, profile: LanguageProfile)` → `voice.send_card_voice(call.message, conn, card, profile.tts_voice)`.

`handlers/add.py`:
- `start_add(message, state, profile: LanguageProfile)` → `message.answer(profile.add_intro)`;
- `receive_text(message, state, conn, llm, profile: LanguageProfile)`:
  `asyncio.to_thread(enrichment.enrich, llm, profile, text)`;
  `card["spanish"]` → `card["word"]` (дедуп-проверка и сообщение «уже есть»);
  `_send_voice(message, card["word"], profile.tts_voice)`;
- `_send_voice(message, word: str, voice: str)`: `tts.synthesize(word, voice, tmp)`, имя tmp-файла из `hash(word)`;
- `save_yes`: `db.card_exists(conn, call.from_user.id, card["word"])`;
  `db.add_card(conn, user_id=…, kind=card["kind"], word=card["word"], translation=card["translation"], transcription=card["transcription"], example=card["example"], example_translation=card["example_translation"], enriched=True, today=date.today())`.

`handlers/training.py` — во всех местах:
- helpers получают профиль параметром: `_show_next_flashcard(message, state, conn, profile)`, `_ask_next_translation(message, state, conn, profile)`, `_ask_next_listen(message, state, conn, profile)`; все вызовы обновить;
- хендлеры получают `profile: LanguageProfile` через DI: `start_flashcards`, `reveal`, `grade_flashcard`, `start_translate`, `check_translation`, `start_listen`, `check_listen`;
- `card["spanish"]` → `card["word"]`, `card["russian"]` → `card["translation"]` (все вхождения: показ карточки, вопросы, ответы, сверки);
- вопрос перевода: `await message.answer(profile.translate_question.format(card["translation"]))`;
- вызов grade: `grading.grade, llm, profile, prompt_ru=card["translation"], expected=card["word"], answer=message.text.strip()`;
- `verdict["correct_spanish"]` → `verdict["correct"]` (оба места: typo и wrong);
- `voice.send_card_voice(message, conn, card, profile.tts_voice)` (flashcards и listen).

`tests/test_handlers_quota.py`:
- `from languages import PROFILES`; в оба вызова хендлеров добавить последний позиционный аргумент `PROFILES["es"]`:
  `await add.receive_text(message, state, conn, MagicMock(), PROFILES["es"])`,
  `await training.check_translation(message, state, conn, MagicMock(), PROFILES["es"])`;
- словарь карточки: `{"id": 1, "word": "mesa", "translation": "стол", "interval_days": 1}`;
- ожидаемые тексты не меняются.

- [ ] **Step 6: Прогнать всё + смоук**

Run: `.venv/bin/pytest -q` → PASS; `.venv/bin/python -c "import bot"` → без ошибок.
Grep-гейт: `grep -rn "correct_spanish\|card\[.spanish.\]\|card\[.russian.\]\|example_es\|example_ru" --include="*.py" . | grep -v ".venv" | grep -v languages.py | grep -v tests/test_languages.py | grep -v tests/test_db_migration.py | grep -v tests/test_enrichment.py | grep -v tests/test_grading.py` → пусто.

- [ ] **Step 7: Commit**

```bash
git add config.py bot.py handlers/menu.py handlers/add.py handlers/training.py tests/test_config.py tests/test_handlers_quota.py
git commit -m "feat: BOT_LANG config + profile DI through bot and handlers"
```

---

### Task 6: Деплой-артефакты и доки

**Files:**
- Modify: `scripts/backup-db.sh`, `.env.example`, `README.md`, `AGENTS.md`, `docs/superpowers/deploy.md`
- Create: `english-bot.service`
- Test: `tests/test_backup_script.py`

**Interfaces:**
- Consumes: нейтральные kwargs `_seed_db` (Task 2).
- Produces: бэкап-скрипт с префиксом из имени БД; systemd-юнит второго бота; задокументированный деплой.

- [ ] **Step 1: Падающие тесты бэкапа**

Добавить в `tests/test_backup_script.py`:

```python
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
```

- [ ] **Step 2: Убедиться, что падают** — `.venv/bin/pytest tests/test_backup_script.py -q` → FAIL (бэкап называется `spanish_bot-*` независимо от источника).

- [ ] **Step 3: Параметризовать `scripts/backup-db.sh`**

Заменить строку `DEST=…` и glob ротации:

```bash
# Префикс бэкапа = имя файла БД: spanish_bot.db -> spanish_bot-YYYY-MM-DD.db,
# english_bot.db -> english_bot-YYYY-MM-DD.db. Два бота могут делить одну
# папку бэкапов: ротация каждого считает только свои файлы.
PREFIX="$(basename "$DB_PATH" .db)"
DEST="$BACKUP_DIR/${PREFIX}-$(date +%Y-%m-%d).db"
```

и

```bash
ls -1 "$BACKUP_DIR/${PREFIX}"-*.db | sort -r | awk 'NR>7' | while read -r f; do
    rm -f "$f"
done
```

- [ ] **Step 4: `english-bot.service`** (новый файл в корне репо, рядом со `spanish-bot.service`):

```ini
[Unit]
Description=English Bot (Telegram, long-polling)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=spanishbot
WorkingDirectory=/home/spanishbot/english-bot
# .env читается самим кодом (config.load() -> load_dotenv()) из WorkingDirectory.
ExecStart=/home/spanishbot/english-bot/.venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 5: Доки**

- `.env.example`: после `GEMINI_FALLBACK_MODEL` добавить строку
  `# BOT_LANG=es` с комментарием `# язык бота: es (испанский, дефолт) | en (английский)`.
- `README.md`: упомянуть `BOT_LANG` в списке env-переменных (если список есть; иначе одно предложение в разделе настройки).
- `AGENTS.md`:
  - Стек: добавить `languages.py (профили es/en)`;
  - Структура: строка `languages.py     языковые профили: голос, промпты, схемы Gemini, UI-строки; выбор через BOT_LANG`;
  - config.py-строка структуры: добавить `BOT_LANG`;
  - Грабли: новый пункт «Колонки cards переименованы на нейтральные (word/translation/example/example_translation, 2026-08-04) с поколоночной автомиграцией в init_db — DDL в python-sqlite3 автокоммитится, поэтому гард на каждую колонку, транзакции нет. Старые имена живут только в es-профиле languages.py (промпты/схема) и тестах миграции.»;
  - Ключевые решения: пункт «Два бота — один код: язык через BOT_LANG (es — мамин, en — Victoria+друзья, American English + IPA, голос en-US-EmmaNeural). es-профиль байт-в-байт равен старым литералам — фиксируется tests/test_languages.py; НЕ менять es-строки без осознанного решения.»;
  - Обе фразы «101 тест» заменить на актуальное число из финального прогона `pytest -q`.
- `docs/superpowers/deploy.md`: новый раздел в конце:

```markdown
## Второй бот на том же сервере (английский, 2026-08)

Тот же код, другой язык: отдельный клон, `.env` с `BOT_LANG=en`, свой юнит.
Секреты: новый токен от BotFather + ключ Gemini из ОТДЕЛЬНОГО Google-проекта
(лимиты бесплатного тира — по проекту; мамин бот и английский не делятся).

```bash
# на сервере (под spanishbot)
cd ~ && git clone git@github.com:<USER>/spanish-bot.git english-bot
cd english-bot
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt

# .env: с мака, приёмом «grep | ssh» (см. «Новый секрет в .env» выше),
# затем на сервере дописать не-секретные строки:
printf 'BOT_LANG=en\nDB_PATH=/home/spanishbot/english-bot/english_bot.db\n' >> ~/english-bot/.env
chmod 600 ~/english-bot/.env

# юнит (под root)
cp /home/spanishbot/english-bot/english-bot.service /etc/systemd/system/
systemd-analyze verify /etc/systemd/system/english-bot.service
systemctl daemon-reload && systemctl enable --now english-bot
journalctl -u english-bot -n 20     # Start polling, без TelegramConflictError

# sudoers (под root): расширить /etc/sudoers.d/spanishbot-service
#   ... /usr/bin/systemctl restart spanish-bot, /usr/bin/systemctl status spanish-bot,
#   /usr/bin/systemctl restart english-bot, /usr/bin/systemctl status english-bot
# и проверить: visudo -c

# бэкап (под spanishbot): вторая строка crontab
35 3 * * * /home/spanishbot/english-bot/scripts/backup-db.sh /home/spanishbot/english-bot/english_bot.db /home/spanishbot/backups >> /home/spanishbot/backup.log 2>&1
```

Мамин бот при этом обновляется обычной «Рутиной обновлений», НО перед
рестартом с миграцией колонок (2026-08) — разовый бэкап:
`~/spanish-bot/scripts/backup-db.sh ~/spanish-bot/spanish_bot.db ~/backups`.
```

- [ ] **Step 6: Прогнать всё** — `.venv/bin/pytest -q` → PASS; вписать реальное число тестов в AGENTS.md.

- [ ] **Step 7: Commit**

```bash
git add scripts/backup-db.sh english-bot.service .env.example README.md AGENTS.md docs/superpowers/deploy.md tests/test_backup_script.py
git commit -m "feat: per-db backup prefix, english-bot unit, BOT_LANG docs"
```

---

## Деплой (вручную, с Victoria — НЕ задача субагента)

1. Merge `language-profiles` → `main`, push (пуш — команда Victoria через `!`).
2. Victoria: токен нового бота у BotFather; ключ Gemini в отдельном Google-проекте; обе строки кладёт в локальный `.env` английского профиля (или временный файл) — перенос на сервер приёмом «grep | ssh» из deploy.md.
3. Мамин бот: разовый бэкап → `git pull` → `sudo systemctl restart spanish-bot` → журнал: `Start polling`; живая проверка «Мой словарь» (старые слова на месте — миграция прошла).
4. Английский бот: раздел «Второй бот на том же сервере» из deploy.md шаг за шагом.
5. Живой тест английского: добавить слово (IPA в превью, голос Emma), перевод с опечаткой (typo-вердикт), аудирование. Контрольные слова IPA: thought, comfortable, schedule, water, can't.
6. Vault: обновить `Projects/Spanish Bot/AGENTS.md` (второй бот) — отдельным vault-коммитом.
