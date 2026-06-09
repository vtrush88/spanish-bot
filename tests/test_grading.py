from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services import grading


def _resp(input_dict):
    block = SimpleNamespace(type="tool_use", name="save_grade", input=input_dict)
    return SimpleNamespace(content=[block])


def test_grade_returns_verdict():
    client = MagicMock()
    client.messages.create.return_value = _resp(
        {"verdict": "typo", "correct_spanish": "comida",
         "note": "маленькая опечатка"}
    )
    result = grading.grade(client, prompt_ru="еда",
                           expected_es="comida", answer="komida")
    assert result["verdict"] == "typo"
    assert result["correct_spanish"] == "comida"


def test_grade_raises_on_bad_response():
    client = MagicMock()
    bad = SimpleNamespace(content=[SimpleNamespace(type="text", text="x")])
    client.messages.create.side_effect = [bad, bad]
    with pytest.raises(grading.GradingError):
        grading.grade(client, prompt_ru="еда",
                      expected_es="comida", answer="komida")
