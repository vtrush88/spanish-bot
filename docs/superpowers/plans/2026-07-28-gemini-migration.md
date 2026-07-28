# Gemini Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести LLM-вызовы бота (обогащение карточек, проверка переводов) с платного Claude API на бесплатный тир Google Gemini, с фолбэком между моделями и мягкой деградацией при исчерпании дневного лимита.

**Architecture:** Новый тонкий слой `services/llm.py` (клиент + список моделей + один вызов со структурированным JSON-ответом + `QuotaExceededError`); `enrichment`/`grading` сохраняют свои сигнатуры данных и ретрай-логику, но зовут `llm.generate_json` вместо Anthropic tool-use. Хендлеры получают зависимость под нейтральным именем `llm` и добавляют обработку квоты. Спека: `docs/superpowers/specs/2026-07-28-gemini-migration-design.md`.

**Tech Stack:** Python 3.12, `google-genai==2.8.0` (заменяет `anthropic==0.39.0`; снимает пин `httpx==0.27.2` — google-genai требует httpx≥0.28.1), aiogram 3.13.1, pytest.

**Почему именно google-genai 2.8.0, не новее:** aiogram 3.13.1 требует `pydantic<2.10`, а google-genai начиная с ~2.9 требует `pydantic>=2.12.5` — конфликт, `pip install` падает с ResolutionImpossible. 2.8.0 — самая свежая версия, совместимая по pydantic (проверено `pip install --dry-run` 2026-07-28); весь используемый API (`GenerateContentConfig` с `system_instruction`/`response_mime_type`/`response_schema`/`thinking_config`, `errors.ClientError(code, response_json)`, `.code`, 4xx→ClientError/5xx→ServerError) сверен с тегом v2.8.0. Не поднимать версию без апгрейда aiogram.

## Global Constraints

- Формат данных сервисов не меняется: `enrich → {kind, spanish, russian, transcription, example_es, example_ru}`, `grade → {verdict, correct_spanish, note}`; enum-ы `kind: word|phrase`, `verdict: correct|typo|wrong`.
- Промпты `SYSTEM` обоих сервисов переносятся дословно (пиренейская лексика, правила транскрипции, гендер-нейтральные note).
- Все новые тексты бота — гендер-нейтральные (без «написала», «умница» и прошедшего времени от 1-го лица бота).
- Хендлеры, `db.py`, SRS, TTS, клавиатуры — без изменений, кроме переименования параметра `anthropic → llm` и двух новых `except QuotaExceededError`.
- После каждой задачи: `.venv/bin/pytest -q` зелёный + `.venv/bin/python -c "import bot"` без ошибок (обе команды повторяются в шагах задач).
- Коммиты подписываются YubiKey — **Victoria тапает ключ на каждом коммите**; не запускать `git commit` не предупредив её.
- Прод на VPS не трогаем до раздела «Деплой». Локально бот между Задачами 1 и 5 не запускать (в venv уже будет httpx≥0.28, несовместимый с anthropic 0.39 — на тесты не влияет, они на моках).
- **Исполнять в текущем рабочем каталоге с существующим `.venv` — БЕЗ git worktree / свежего venv.** Пакет `anthropic` остаётся установленным (хоть и убран из requirements) до Задачи 5 — только благодаря этому `import bot` проходит на коммитах Задач 1–4. В свежем окружении промежуточные коммиты не импортируются — осознанный компромисс однопользовательского репо.

---

### Task 1: Зависимости + `services/llm.py` (клиент, фолбэк, квота)

**Files:**
- Modify: `requirements.txt`
- Create: `services/llm.py`
- Test: `tests/test_llm.py`
- Commit also: `docs/superpowers/specs/2026-07-28-gemini-migration-design.md`, `docs/superpowers/plans/2026-07-28-gemini-migration.md`

**Interfaces:**
- Produces: `llm.LLM(client, models: tuple[str, ...])` (frozen dataclass); `llm.QuotaExceededError(Exception)`; `llm.generate_json(llm_obj, *, system: str, schema: dict, text: str) -> dict | None` — dict при валидном JSON-объекте, `None` при мусоре (ретрай — забота вызывающего), `QuotaExceededError` когда 429 на всех моделях, прочие `google.genai.errors.APIError` пробрасываются.

- [ ] **Step 1: Обновить requirements.txt и поставить зависимости**

Новое содержимое `requirements.txt` целиком (убраны `anthropic` и пин `httpx`, добавлен `google-genai`):

```
aiogram==3.13.1
google-genai==2.8.0  # НЕ поднимать без апгрейда aiogram: >=2.9 требует pydantic>=2.12, aiogram 3.13 — <2.10
edge-tts==7.2.8
python-dotenv==1.0.1
pytest==8.3.3
pytest-asyncio==0.24.0
```

Run: `cd "/Users/vtrush/work/main vault/Projects/Spanish Bot/app" && .venv/bin/pip install -r requirements.txt`
Expected: успешная установка `google-genai==2.8.0`, апгрейд `httpx` до ≥0.28.1, pydantic остаётся 2.9.x. Пакет `anthropic` НЕ удалять из venv до Задачи 5 (см. Global Constraints).

- [ ] **Step 2: Написать падающие тесты**

Создать `tests/test_llm.py`:

```python
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.genai import errors

from services import llm


GOOD = {"kind": "word", "spanish": "comida"}
SCHEMA = {"type": "OBJECT", "properties": {"kind": {"type": "STRING"}},
          "required": ["kind"]}


def _llm(client, models=("flash", "flash-lite")):
    return llm.LLM(client=client, models=models)


def _quota_error():
    return errors.ClientError(
        429, {"message": "Too Many Requests", "status": "RESOURCE_EXHAUSTED"})


def test_returns_dict_from_first_model():
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(
        text=json.dumps(GOOD))
    result = llm.generate_json(_llm(client), system="s", schema=SCHEMA, text="hola")
    assert result == GOOD
    assert client.models.generate_content.call_count == 1
    assert client.models.generate_content.call_args.kwargs["model"] == "flash"


def test_garbage_text_returns_none():
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text="not json")
    assert llm.generate_json(_llm(client), system="s", schema=SCHEMA,
                             text="hola") is None


def test_none_text_returns_none():
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text=None)
    assert llm.generate_json(_llm(client), system="s", schema=SCHEMA,
                             text="hola") is None


def test_json_array_returns_none():
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text="[1, 2]")
    assert llm.generate_json(_llm(client), system="s", schema=SCHEMA,
                             text="hola") is None


def test_429_falls_back_to_second_model():
    client = MagicMock()
    client.models.generate_content.side_effect = [
        _quota_error(), SimpleNamespace(text=json.dumps(GOOD))]
    result = llm.generate_json(_llm(client), system="s", schema=SCHEMA, text="hola")
    assert result == GOOD
    assert client.models.generate_content.call_count == 2
    assert client.models.generate_content.call_args.kwargs["model"] == "flash-lite"


def test_429_on_all_models_raises_quota_error():
    client = MagicMock()
    client.models.generate_content.side_effect = [_quota_error(), _quota_error()]
    with pytest.raises(llm.QuotaExceededError):
        llm.generate_json(_llm(client), system="s", schema=SCHEMA, text="hola")


def test_429_without_fallback_raises_quota_error():
    client = MagicMock()
    client.models.generate_content.side_effect = [_quota_error()]
    with pytest.raises(llm.QuotaExceededError):
        llm.generate_json(_llm(client, models=("flash",)), system="s",
                          schema=SCHEMA, text="hola")


def test_non_429_client_error_propagates():
    client = MagicMock()
    client.models.generate_content.side_effect = [
        errors.ClientError(403, {"message": "forbidden"})]
    with pytest.raises(errors.APIError):
        llm.generate_json(_llm(client), system="s", schema=SCHEMA, text="hola")


def test_5xx_returns_none_like_garbage():
    # Перегрузка бесплатного тира (503 UNAVAILABLE — частый случай):
    # трактуем как мусорный ответ, ретраит вызывающий сервис.
    client = MagicMock()
    client.models.generate_content.side_effect = [
        errors.ServerError(503, {"message": "overloaded"})]
    assert llm.generate_json(_llm(client), system="s", schema=SCHEMA,
                             text="hola") is None
```

- [ ] **Step 3: Убедиться, что тесты падают**

Run: `.venv/bin/pytest tests/test_llm.py -v`
Expected: FAIL/ERROR с `ModuleNotFoundError: No module named 'services.llm'` (или ImportError).

- [ ] **Step 4: Реализовать `services/llm.py`**

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from google.genai import errors, types


class QuotaExceededError(Exception):
    """429 (дневной лимит бесплатного тира) на всех настроенных моделях."""


@dataclass(frozen=True)
class LLM:
    client: Any                # genai.Client; Any — чтобы тесты подставляли мок
    models: tuple[str, ...]    # (основная, [фолбэк]) — из config


def generate_json(llm: LLM, *, system: str, schema: dict, text: str) -> dict | None:
    """Один вызов Gemini со структурированным JSON-ответом.

    Возвращает dict (валидный JSON-объект) или None (мусор ЛИБО 5xx-перегрузка —
    ретраит вызывающий, как раньше с tool_use; google-genai, в отличие от
    anthropic SDK, сам НЕ ретраит). 429 → пробуем следующую модель из списка
    (у каждой свой дневной лимит); 429 на всех → QuotaExceededError.
    Прочие 4xx пробрасываются как есть.
    """
    last_quota_error: errors.APIError | None = None
    for model in llm.models:
        try:
            response = llm.client.models.generate_content(
                model=model,
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_schema=schema,
                    # Ответы простые; thinking только замедлял бы и жёг лимит.
                    # NB: параметр валиден для моделей 2.5 (обе дефолтные);
                    # экзотика в GEMINI_MODEL может его не принять (400).
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
        except errors.APIError as e:
            if e.code == 429:
                last_quota_error = e
                continue
            if e.code >= 500:
                # Перегрузка бесплатного тира — как мусорный ответ: сервис
                # сделает второй заход, потом отдаст свою обычную ошибку.
                return None
            raise
        try:
            data = json.loads(response.text)
        except (TypeError, ValueError):
            return None
        return data if isinstance(data, dict) else None
    raise QuotaExceededError("дневной лимит запросов исчерпан") from last_quota_error
```

- [ ] **Step 5: Прогнать тесты модуля, затем весь набор**

Run: `.venv/bin/pytest tests/test_llm.py -v && .venv/bin/pytest -q && .venv/bin/python -c "import bot"`
Expected: test_llm PASS; весь набор зелёный (существующие сервисы ещё на anthropic-моках — они не трогались); import bot без ошибок.

- [ ] **Step 6: Commit (Victoria тапает YubiKey)**

```bash
git add requirements.txt services/llm.py tests/test_llm.py \
  docs/superpowers/specs/2026-07-28-gemini-migration-design.md \
  docs/superpowers/plans/2026-07-28-gemini-migration.md
git commit -m "Gemini migration: services/llm.py (fallback models, quota error) + deps"
```

---

### Task 2: `services/enrichment.py` на Gemini

**Files:**
- Modify: `services/enrichment.py`
- Test: `tests/test_enrichment.py` (переписать моки)

**Interfaces:**
- Consumes: `llm.LLM`, `llm.generate_json(llm_obj, *, system, schema, text)`, `llm.QuotaExceededError` из Task 1.
- Produces: `enrichment.enrich(llm_obj: llm.LLM, text: str) -> dict` — тот же результат-словарь и `EnrichmentError`, что раньше; `QuotaExceededError` пробрасывается наружу без перехвата. Константа `MODEL` удаляется.

- [ ] **Step 1: Переписать тесты под новый интерфейс**

Новое содержимое `tests/test_enrichment.py` целиком:

```python
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.genai import errors

from services import enrichment, llm


GOOD = {
    "kind": "word",
    "spanish": "comida",
    "russian": "еда",
    "transcription": "комИда",
    "example_es": "La comida está lista.",
    "example_ru": "Еда готова.",
}


def _llm(client):
    return llm.LLM(client=client, models=("flash",))


def _resp(payload):
    return SimpleNamespace(text=json.dumps(payload))


def test_enrich_returns_clean_dict():
    client = MagicMock()
    client.models.generate_content.return_value = _resp(GOOD)
    result = enrichment.enrich(_llm(client), "comida")
    assert result == GOOD
    assert client.models.generate_content.call_count == 1


def test_enrich_strips_extra_keys():
    client = MagicMock()
    client.models.generate_content.return_value = _resp({**GOOD, "extra": "x"})
    assert enrichment.enrich(_llm(client), "comida") == GOOD


def test_enrich_retries_once_then_succeeds():
    client = MagicMock()
    client.models.generate_content.side_effect = [
        SimpleNamespace(text="oops not json"), _resp(GOOD)]
    result = enrichment.enrich(_llm(client), "comida")
    assert result["spanish"] == "comida"
    assert client.models.generate_content.call_count == 2


def test_enrich_retries_on_missing_key():
    incomplete = {k: v for k, v in GOOD.items() if k != "transcription"}
    client = MagicMock()
    client.models.generate_content.side_effect = [_resp(incomplete), _resp(GOOD)]
    assert enrichment.enrich(_llm(client), "comida") == GOOD


def test_enrich_raises_after_two_bad_responses():
    client = MagicMock()
    client.models.generate_content.side_effect = [
        SimpleNamespace(text="oops"), SimpleNamespace(text="oops")]
    with pytest.raises(enrichment.EnrichmentError):
        enrichment.enrich(_llm(client), "comida")


def test_enrich_propagates_quota_error():
    client = MagicMock()
    client.models.generate_content.side_effect = [
        errors.ClientError(429, {"message": "quota"})]
    with pytest.raises(llm.QuotaExceededError):
        enrichment.enrich(_llm(client), "comida")
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/pytest tests/test_enrichment.py -v`
Expected: FAIL/ERROR — старый `enrich` обращается к `llm_obj.messages`, а frozen-датакласс `LLM` такого атрибута не имеет → `AttributeError: 'LLM' object has no attribute 'messages'` в большинстве тестов. Это ожидаемо; не чинить тесты — чинить реализацию (Step 3).

- [ ] **Step 3: Переписать `services/enrichment.py`**

Новое содержимое целиком. Строка `SYSTEM` — **дословно та же, что сейчас в файле** (здесь сокращена меткой `<SYSTEM без изменений>`; при реализации скопировать существующую):

```python
from __future__ import annotations

from services import llm as llm_service

REQUIRED_KEYS = (
    "kind", "spanish", "russian", "transcription", "example_es", "example_ru",
)

SYSTEM = <SYSTEM без изменений — скопировать текущую константу дословно>

# OpenAPI-подмножество схем Gemini (типы ЗАГЛАВНЫМИ) — та же схема,
# что была в TOOL["input_schema"], без anthropic-обёртки.
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "kind": {"type": "STRING", "enum": ["word", "phrase"]},
        "spanish": {"type": "STRING"},
        "russian": {"type": "STRING"},
        "transcription": {"type": "STRING"},
        "example_es": {"type": "STRING"},
        "example_ru": {"type": "STRING"},
    },
    "required": list(REQUIRED_KEYS),
}


class EnrichmentError(Exception):
    pass


def enrich(llm: llm_service.LLM, text: str) -> dict:
    last_error = None
    for _ in range(2):
        data = llm_service.generate_json(llm, system=SYSTEM, schema=SCHEMA,
                                         text=text)
        if data is not None and all(k in data and data[k] for k in REQUIRED_KEYS):
            return {k: data[k] for k in REQUIRED_KEYS}
        last_error = "модель вернула ответ без валидной JSON-карточки"
    raise EnrichmentError(last_error or "enrichment failed")
```

Удаляются: `MODEL`, `TOOL`, `_extract`, упоминания Claude/anthropic.

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/pytest tests/test_enrichment.py -v && .venv/bin/pytest -q && .venv/bin/python -c "import bot"`
Expected: всё зелёное, import bot без ошибок (хендлеры в тестах не выполняются, только импортируются — сигнатура `enrich` для них поменяется в Task 5).

- [ ] **Step 5: Commit (Victoria тапает YubiKey)**

```bash
git add services/enrichment.py tests/test_enrichment.py
git commit -m "Gemini migration: enrichment via structured JSON output"
```

---

### Task 3: `services/grading.py` на Gemini

**Files:**
- Modify: `services/grading.py`
- Test: `tests/test_grading.py` (моки LLM-части; тесты `answers_match` не трогать)

**Interfaces:**
- Consumes: `llm.LLM`, `llm.generate_json`, `llm.QuotaExceededError` из Task 1.
- Produces: `grading.grade(llm_obj: llm.LLM, *, prompt_ru, expected_es, answer) -> dict` — тот же словарь и `GradingError`; `QuotaExceededError` пробрасывается. `grading.answers_match` — без изменений. Константа `MODEL` удаляется.

- [ ] **Step 1: Переписать LLM-тесты в `tests/test_grading.py`**

Заменить `_resp`, `test_grade_returns_verdict`, `test_grade_raises_on_bad_response`; добавить квоту. Параметризованный `test_answers_match_ignores_case_keeps_accents` оставить как есть. Новая верхняя часть файла:

```python
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.genai import errors

from services import grading, llm


def _llm(client):
    return llm.LLM(client=client, models=("flash",))


def _resp(payload):
    return SimpleNamespace(text=json.dumps(payload))


def test_grade_returns_verdict():
    client = MagicMock()
    client.models.generate_content.return_value = _resp(
        {"verdict": "typo", "correct_spanish": "comida",
         "note": "маленькая опечатка"}
    )
    result = grading.grade(_llm(client), prompt_ru="еда",
                           expected_es="comida", answer="komida")
    assert result["verdict"] == "typo"
    assert result["correct_spanish"] == "comida"


def test_grade_raises_on_bad_response():
    client = MagicMock()
    client.models.generate_content.side_effect = [
        SimpleNamespace(text="x"), SimpleNamespace(text="x")]
    with pytest.raises(grading.GradingError):
        grading.grade(_llm(client), prompt_ru="еда",
                      expected_es="comida", answer="komida")


def test_grade_rejects_unknown_verdict():
    client = MagicMock()
    client.models.generate_content.side_effect = [
        _resp({"verdict": "maybe", "correct_spanish": "comida", "note": "?"}),
        _resp({"verdict": "maybe", "correct_spanish": "comida", "note": "?"})]
    with pytest.raises(grading.GradingError):
        grading.grade(_llm(client), prompt_ru="еда",
                      expected_es="comida", answer="komida")


def test_grade_propagates_quota_error():
    client = MagicMock()
    client.models.generate_content.side_effect = [
        errors.ClientError(429, {"message": "quota"})]
    with pytest.raises(llm.QuotaExceededError):
        grading.grade(_llm(client), prompt_ru="еда",
                      expected_es="comida", answer="komida")
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/pytest tests/test_grading.py -v`
Expected: FAIL на новых/переписанных тестах; `answers_match`-тесты зелёные.

- [ ] **Step 3: Переписать `services/grading.py`**

Новое содержимое (SYSTEM — дословно текущий; `answers_match` — без изменений, скопировать вместе с docstring):

```python
from __future__ import annotations

from services import llm as llm_service

REQUIRED_KEYS = ("verdict", "correct_spanish", "note")
VALID_VERDICTS = ("correct", "typo", "wrong")

SYSTEM = <SYSTEM без изменений — скопировать текущую константу дословно>

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "verdict": {"type": "STRING", "enum": list(VALID_VERDICTS)},
        "correct_spanish": {"type": "STRING"},
        "note": {"type": "STRING"},
    },
    "required": list(REQUIRED_KEYS),
}


class GradingError(Exception):
    pass


def answers_match(answer: str, expected: str) -> bool:
    <без изменений — скопировать текущую функцию с docstring>


def grade(llm: llm_service.LLM, *, prompt_ru: str, expected_es: str,
          answer: str) -> dict:
    user = (
        f"Русский запрос: {prompt_ru}\n"
        f"Ожидаемый испанский: {expected_es}\n"
        f"Ответ ученика: {answer}"
    )
    last_error = None
    for _ in range(2):
        data = llm_service.generate_json(llm, system=SYSTEM, schema=SCHEMA,
                                         text=user)
        if (data is not None
                and all(k in data and data[k] for k in REQUIRED_KEYS)
                and data["verdict"] in VALID_VERDICTS):
            return {k: data[k] for k in REQUIRED_KEYS}
        last_error = "модель вернула ответ без валидной JSON-оценки"
    raise GradingError(last_error or "grading failed")
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/pytest tests/test_grading.py -v && .venv/bin/pytest -q && .venv/bin/python -c "import bot"`
Expected: всё зелёное, import bot без ошибок.

- [ ] **Step 5: Commit (Victoria тапает YubiKey)**

```bash
git add services/grading.py tests/test_grading.py
git commit -m "Gemini migration: grading via structured JSON output"
```

---

### Task 4: `config.py` — новые env-переменные

**Files:**
- Modify: `config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config` с полями `gemini_api_key: str`, `gemini_model: str` (default `gemini-2.5-flash`), `gemini_fallback_model: str` (default `gemini-2.5-flash-lite`, `""` = фолбэк отключён). Поле `anthropic_api_key` удаляется. Остальные поля без изменений.

- [ ] **Step 1: Обновить тесты**

В `tests/test_config.py`: во всех тестах `ANTHROPIC_API_KEY` → `GEMINI_API_KEY`; в `test_load_parses_env` проверка `cfg.anthropic_api_key` → `cfg.gemini_api_key`; добавить в конец файла:

```python
def test_gemini_model_defaults(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_FALLBACK_MODEL", raising=False)
    cfg = config.load()
    assert cfg.gemini_model == "gemini-2.5-flash"
    assert cfg.gemini_fallback_model == "gemini-2.5-flash-lite"


def test_gemini_model_overrides(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.0-flash")
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "")
    cfg = config.load()
    assert cfg.gemini_model == "gemini-3.0-flash"
    assert cfg.gemini_fallback_model == ""


def test_empty_gemini_model_falls_back_to_default(monkeypatch):
    # Пустая GEMINI_MODEL= в .env не должна дать models=("",)
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    monkeypatch.setenv("GEMINI_MODEL", "")
    cfg = config.load()
    assert cfg.gemini_model == "gemini-2.5-flash"
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL (`Missing required env var: ANTHROPIC_API_KEY` / AttributeError).

- [ ] **Step 3: Обновить `config.py`**

```python
@dataclass(frozen=True)
class Config:
    telegram_token: str
    gemini_api_key: str
    gemini_model: str
    gemini_fallback_model: str  # "" = фолбэк отключён
    allowed_user_ids: set[int]
    db_path: str
```

и в `load()`:

```python
    return Config(
        telegram_token=_require("TELEGRAM_TOKEN"),
        gemini_api_key=_require("GEMINI_API_KEY"),
        # `or`: пустая строка в .env не должна дать models=("",)
        gemini_model=os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash",
        gemini_fallback_model=os.environ.get(
            "GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite"),
        allowed_user_ids=ids,
        db_path=os.environ.get("DB_PATH", "spanish_bot.db"),
    )
```

- [ ] **Step 4: Обновить `.env.example`**

Новое содержимое целиком:

```
TELEGRAM_TOKEN=put-bot-token-here
GEMINI_API_KEY=put-gemini-key-here
# GEMINI_MODEL=gemini-2.5-flash
# GEMINI_FALLBACK_MODEL=gemini-2.5-flash-lite
ALLOWED_USER_IDS=123456789
DB_PATH=spanish_bot.db
```

- [ ] **Step 5: Прогнать тесты**

Run: `.venv/bin/pytest tests/test_config.py -v && .venv/bin/pytest -q && .venv/bin/python -c "import bot"`
Expected: всё зелёное, import bot без ошибок (bot.py обращается к `cfg.anthropic_api_key` только внутри `main()`, которая при импорте не выполняется).

- [ ] **Step 6: Commit (Victoria тапает YubiKey)**

```bash
git add config.py tests/test_config.py .env.example
git commit -m "Gemini migration: config env vars (GEMINI_API_KEY, models)"
```

---

### Task 5: `bot.py` + хендлеры — внедрение `llm`, деградация при квоте

**Files:**
- Modify: `bot.py`
- Modify: `handlers/add.py`
- Modify: `handlers/training.py`

**Interfaces:**
- Consumes: `Config.gemini_*` из Task 4; `llm.LLM`, `llm.QuotaExceededError` из Task 1; новые сигнатуры `enrich(llm, text)` / `grade(llm, ...)` из Tasks 2–3.
- Produces: DI-ключ `dp["llm"]` (объект `llm.LLM`); хендлеры принимают параметр `llm` (aiogram матчит по имени). Импортов `anthropic` в кодовой базе не остаётся.

- [ ] **Step 1: Обновить `bot.py`**

Заменить `from anthropic import Anthropic` на:

```python
from google import genai

from services import llm as llm_service
```

Внутри `main()` заменить создание клиента и DI (строки с `anthropic_client` и `dp["anthropic"]`):

```python
    gemini_client = genai.Client(api_key=cfg.gemini_api_key)
    models = (cfg.gemini_model,)
    if cfg.gemini_fallback_model:
        models += (cfg.gemini_fallback_model,)
```

```python
    dp["conn"] = conn
    dp["llm"] = llm_service.LLM(client=gemini_client, models=models)
```

- [ ] **Step 2: Обновить `handlers/add.py`**

Убрать `from anthropic import Anthropic`; добавить `from services.llm import LLM, QuotaExceededError`. Сигнатура `receive_text`: параметр `anthropic: Anthropic` → `llm: LLM`. Вызов и обработка ошибок:

```python
    text = message.text.strip()
    try:
        # to_thread: синхронный вызов Gemini не должен блокировать event loop
        card = await asyncio.to_thread(enrichment.enrich, llm, text)
    except QuotaExceededError:
        # 429 на обеих моделях: дневной лимит ИЛИ минутный всплеск —
        # не обещаем «завтра», предлагаем и «позже».
        await message.answer(
            "Лимит бесплатных ИИ-запросов пока исчерпан 😕 "
            "Попробуй позже или завтра."
        )
        return
    except enrichment.EnrichmentError:
        # Stay in waiting_for_text; next message retries. Save-as-is +
        # later re-enrichment is deferred (see out-of-MVP improvements).
        await message.answer(
            "Не получилось обработать сейчас 😕 Попробуй ещё раз через минутку "
            "или пришли другое слово."
        )
        return
```

- [ ] **Step 3: Обновить `handlers/training.py`**

Добавить `from services.llm import QuotaExceededError`. В `check_translation`: параметр `anthropic` → `llm`. Комментарий над веткой `answers_match` (сейчас «…no need to bother Claude») заменить на «…no need to call the model». Блок try/except:

```python
        try:
            # to_thread: синхронный вызов Gemini не должен блокировать event loop
            verdict = await asyncio.to_thread(
                grading.grade,
                llm, prompt_ru=card["russian"],
                expected_es=card["spanish"], answer=message.text.strip(),
            )
            ok = verdict["verdict"] in ("correct", "typo")
            if verdict["verdict"] == "correct":
                await message.answer("✅ Верно!")
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
        except QuotaExceededError:
            # Лимит бесплатного тира: точное сравнение уже не совпало
            # (answers_match выше), считаем как «не вспомнила» без ИИ-комментария.
            ok = False
            await message.answer(
                f"❌ Правильно: {card['spanish']}\n"
                "(умная проверка сегодня недоступна — лимит бесплатных запросов; "
                "сравни свой ответ с правильным)"
            )
        except grading.GradingError:
            # Fall back to a forgiving exact-match check if the model returns junk.
            ok = message.text.strip().lower() == card["spanish"].lower()
            await message.answer("✅ Верно!" if ok
                                 else f"❌ Правильно: {card['spanish']}")
```

- [ ] **Step 4: Проверить, что anthropic не остался, импорты живы, тесты зелёные**

Run:
```bash
grep -rni "anthropic\|claude" --include="*.py" --exclude-dir=.venv . && echo "FOUND — убрать" || echo "clean"
.venv/bin/python -c "import bot"
.venv/bin/pytest -q
```
Expected: `clean`; импорт без ошибок; весь набор зелёный. Опционально: `.venv/bin/pip uninstall -y anthropic`.

- [ ] **Step 5: Commit (Victoria тапает YubiKey)**

```bash
git add bot.py handlers/add.py handlers/training.py
git commit -m "Gemini migration: wire llm dependency, quota degradation in handlers"
```

---

### Task 6: Документация (AGENTS.md)

**Files:**
- Modify: `AGENTS.md`

**Interfaces:** нет кода; фиксирует новую фактуру для будущих агентов.

- [ ] **Step 1: Обновить `AGENTS.md`**

Точечные правки:

1. Все упоминания Claude по файлу → Gemini (проверить `grep -n -i claude AGENTS.md`; на момент написания плана — строки ~14, 48–50, 113, 135, 147, 169, 176: описание проекта, структура services, грабли про to_thread, ключевые решения про промпты, бэклог про STT).
2. Раздел «Стек»: `**anthropic 0.39** (claude-haiku-4-5-20251001)` → `**google-genai 2.14** (gemini-2.5-flash, фолбэк gemini-2.5-flash-lite — бесплатный тир)`; убрать упоминание пина httpx, если встречается в стеке.
3. Раздел «Структура»: `config.py` — env-список → `TELEGRAM_TOKEN, GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODEL, ALLOWED_USER_IDS`; строки про `services/enrichment.py` и `services/grading.py` — «Claude tool-use» → «Gemini structured JSON (через services/llm.py)»; добавить строку `services/llm.py   клиент Gemini + фолбэк моделей + QuotaExceededError`.
4. «Рантайм-грабли»: удалить пункт про пин `httpx 0.27.2`; пункт про `asyncio.to_thread` — «Anthropic-клиент» → «Gemini-клиент»; добавить два пункта: «**Бесплатный тир Gemini: 250 зап./день (flash) + 1000 (flash-lite), лимиты раздельные.** При 429 код сам фолбэчит на вторую модель; когда исчерпаны обе — QuotaExceededError и мягкая деградация (слово не добавляется / проверка без ИИ-комментария); 5xx-перегрузка трактуется как мусорный ответ (ретрай сервиса, потом обычная ошибка). Модели меняются в .env без деплоя.» и «**google-genai запинен 2.8.0** — новее требует pydantic≥2.12, конфликт с aiogram 3.13 (<2.10); не поднимать без апгрейда aiogram. В `generate_json` захардкожен `thinking_budget=0` — валиден для моделей 2.5; экзотическая GEMINI_MODEL может не принять параметр (400), тогда править services/llm.py.»
5. «Как запускать»: `ANTHROPIC_API_KEY (sk-ant-...)` → `GEMINI_API_KEY (Google AI Studio, бесплатно)`.
6. «Статус и бэклог»: добавить строку в «Готово»: «Мигрирован с Claude API на бесплатный тир Gemini (2026-07-28, спека docs/superpowers/specs/2026-07-28-gemini-migration-design.md)».

- [ ] **Step 2: Commit (Victoria тапает YubiKey)**

```bash
git add AGENTS.md
git commit -m "Gemini migration: update AGENTS.md (stack, env, quota gotchas)"
```

---

## Деплой (вручную, вместе с Victoria — вне субагентских задач)

1. Victoria: завести бесплатный ключ на https://aistudio.google.com/ (Google-аккаунт, карта не нужна).
2. Локально: убедиться, что локальный бот не запущен; финальный `pytest -q` зелёный; `git push`.
3. На VPS (ssh): `git pull`; `.venv/bin/pip install -r requirements.txt`; в `.env` добавить `GEMINI_API_KEY=...` (строку `ANTHROPIC_API_KEY` пока оставить — откат); `systemctl restart spanish-bot`.
4. Журнал: `journalctl -u spanish-bot -f` — ждать `Start polling`, убедиться в отсутствии `TelegramConflictError`.
5. Живая проверка в Telegram (Victoria): добавить контрольные слова (llave, cerveza, año, coche, vale) — проверить лексику Испании и транскрипцию (йАвэ, сервЭса, Аньо…); проверка перевода с намеренной опечаткой (typo-вердикт и нейтральная note); карточки и аудирование.
6. Если качество ок — через несколько дней удалить `ANTHROPIC_API_KEY` из `.env` на VPS.
7. Откат: `git revert` кодовых коммитов миграции (спеку/план можно не реверчивать — Task 1 коммитит их вместе с кодом, при revert конфликтов по докам не будет, они просто вернутся; при желании восстановить `git checkout`), затем `pip install -r requirements.txt` (httpx понизится обратно до 0.27.2; осиротевший google-genai будет ругаться конфликтом — `pip uninstall -y google-genai`) и рестарт юнита.
