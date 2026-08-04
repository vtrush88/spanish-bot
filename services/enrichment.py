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
