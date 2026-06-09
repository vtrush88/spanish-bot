from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services import enrichment


def _resp(input_dict):
    block = SimpleNamespace(type="tool_use", name="save_card", input=input_dict)
    return SimpleNamespace(content=[block])


GOOD = {
    "kind": "word",
    "spanish": "comida",
    "russian": "еда",
    "transcription": "комИда",
    "example_es": "La comida está lista.",
    "example_ru": "Еда готова.",
}


def test_enrich_returns_clean_dict():
    client = MagicMock()
    client.messages.create.return_value = _resp(GOOD)
    result = enrichment.enrich(client, "comida")
    assert result == GOOD
    assert client.messages.create.call_count == 1


def test_enrich_retries_once_then_succeeds():
    client = MagicMock()
    bad = SimpleNamespace(content=[SimpleNamespace(type="text", text="oops")])
    client.messages.create.side_effect = [bad, _resp(GOOD)]
    result = enrichment.enrich(client, "comida")
    assert result["spanish"] == "comida"
    assert client.messages.create.call_count == 2


def test_enrich_raises_after_two_bad_responses():
    client = MagicMock()
    bad = SimpleNamespace(content=[SimpleNamespace(type="text", text="oops")])
    client.messages.create.side_effect = [bad, bad]
    with pytest.raises(enrichment.EnrichmentError):
        enrichment.enrich(client, "comida")
