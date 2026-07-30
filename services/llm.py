from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from google.genai import errors, types


class QuotaExceededError(Exception):
    """429 (дневной лимит бесплатного тира) на всех настроенных моделях."""


@dataclass(frozen=True)
class LLM:
    client: Any                # genai.Client; Any — чтобы тесты подставляли мок
    models: tuple[str, ...]    # (основная, [фолбэк]) — из config


def generate_json(llm: LLM, *, system: str, schema: dict, text: str,
                   max_output_tokens: int = 512) -> dict | None:
    """Один вызов Gemini со структурированным JSON-ответом.

    Возвращает dict (валидный JSON-объект) или None (мусор — ретраит
    вызывающий, как раньше с tool_use; google-genai, в отличие от anthropic
    SDK, сам НЕ ретрает). Недоступность модели — 429, 5xx И транспортный сбой
    httpx (обрыв/таймаут) — переключает на следующую модель списка (наступлено
    2026-07-30: flash может отдавать 503 «high demand» часами, фолбэк обязан
    срабатывать и на это). Все модели недоступны: был хоть один не-429 →
    None (сервисный ретрай, потом «попробуй ещё раз»); чисто 429 →
    QuotaExceededError. Прочие 4xx пробрасываются как есть.
    `max_output_tokens` ограничивает длину ответа (сервисы задают явно).
    """
    last_quota_error: errors.APIError | None = None
    saw_transient_error = False
    for model in llm.models:
        try:
            response = llm.client.models.generate_content(
                model=model,
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_schema=schema,
                    max_output_tokens=max_output_tokens,
                    # thinking НЕ отключаем: thinkingBudget=0 → 400 на моделях 3.5+
                    # (проверено 2026-07-30); дефолт моделей сам почти не думает
                    # на структурном выводе, кап max_output_tokens страхует.
                ),
            )
        except errors.APIError as e:
            if e.code == 429:
                last_quota_error = e
                continue
            if e.code >= 500:
                # Перегрузка модели — пробуем следующую из списка.
                saw_transient_error = True
                continue
            raise
        except httpx.HTTPError:
            # Транспортный сбой (обрыв, таймаут) — пробуем следующую модель.
            saw_transient_error = True
            continue
        try:
            data = json.loads(response.text)
        except (TypeError, ValueError):
            return None
        return data if isinstance(data, dict) else None
    if saw_transient_error:
        # Хоть одна модель легла не по квоте: это «попробуй позже»,
        # а не «лимит исчерпан» — отдаём None, сервис ретраит/деградирует.
        return None
    raise QuotaExceededError("дневной лимит запросов исчерпан") from last_quota_error
