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
