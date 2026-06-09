from __future__ import annotations

MODEL = "claude-haiku-4-5-20251001"

REQUIRED_KEYS = (
    "kind", "spanish", "russian", "transcription", "example_es", "example_ru",
)

SYSTEM = (
    "Ты помогаешь русскоязычному новичку учить испанский язык Испании "
    "(европейский, кастильский — НЕ латиноамериканский вариант). "
    "На вход даётся слово или фраза на испанском ИЛИ на русском. "
    "Определи язык. Верни испанский вариант (spanish) в варианте Испании — "
    "используй пиренейскую лексику (coche, ordenador, móvil, zumo, vale, "
    "vosotros и т.п.), НЕ латиноамериканскую (carro, computadora, celular, jugo). "
    "Дай русский перевод (russian); произношение русскими буквами с ударением "
    "(transcription) — пиши ПРОСТО и читаемо для новичка: звук c/z перед e/i "
    "передавай как «с» (без межзубного), напр. 'cerveza' → 'сервЭса', "
    "'gracias' → 'грАсиас', 'comida' → 'комИда'. Добавь короткий "
    "пример-предложение на испанском Испании (example_es) с переводом (example_ru). "
    "Поле kind = 'word' для одного слова, 'phrase' для фразы/предложения. "
    "Всё кратко и для начинающего."
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
