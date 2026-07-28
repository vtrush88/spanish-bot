from __future__ import annotations

from services import llm as llm_service

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
                                         text=text, max_output_tokens=512)
        if data is not None and all(k in data and data[k] for k in REQUIRED_KEYS):
            return {k: data[k] for k in REQUIRED_KEYS}
        last_error = "модель вернула ответ без валидной JSON-карточки"
    raise EnrichmentError(last_error or "enrichment failed")
