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
