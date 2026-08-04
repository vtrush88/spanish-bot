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


def _llm(client):
    return llm.LLM(client=client, models=("flash",))


def _resp(payload):
    return SimpleNamespace(text=json.dumps(payload))


def test_enrich_returns_clean_dict():
    client = MagicMock()
    client.models.generate_content.return_value = _resp(GOOD_ES_RESPONSE)
    result = enrichment.enrich(_llm(client), ES, "comida")
    assert result == GOOD_NEUTRAL
    assert client.models.generate_content.call_count == 1


def test_enrich_strips_extra_keys():
    client = MagicMock()
    client.models.generate_content.return_value = _resp(
        {**GOOD_ES_RESPONSE, "extra": "x"})
    assert enrichment.enrich(_llm(client), ES, "comida") == GOOD_NEUTRAL


def test_enrich_retries_once_then_succeeds():
    client = MagicMock()
    client.models.generate_content.side_effect = [
        SimpleNamespace(text="oops not json"), _resp(GOOD_ES_RESPONSE)]
    result = enrichment.enrich(_llm(client), ES, "comida")
    assert result["word"] == "comida"
    assert client.models.generate_content.call_count == 2


def test_enrich_retries_on_missing_key():
    incomplete = {k: v for k, v in GOOD_ES_RESPONSE.items() if k != "transcription"}
    client = MagicMock()
    client.models.generate_content.side_effect = [
        _resp(incomplete), _resp(GOOD_ES_RESPONSE)]
    assert enrichment.enrich(_llm(client), ES, "comida") == GOOD_NEUTRAL


def test_enrich_raises_after_two_bad_responses():
    client = MagicMock()
    client.models.generate_content.side_effect = [
        SimpleNamespace(text="oops"), SimpleNamespace(text="oops")]
    with pytest.raises(enrichment.EnrichmentError):
        enrichment.enrich(_llm(client), ES, "comida")


def test_enrich_propagates_quota_error():
    client = MagicMock()
    client.models.generate_content.side_effect = [
        errors.ClientError(429, {"message": "quota"})]
    with pytest.raises(llm.QuotaExceededError):
        enrichment.enrich(_llm(client), ES, "comida")


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
