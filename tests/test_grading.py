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


@pytest.mark.parametrize(
    "answer, expected, match",
    [
        ("Mesa", "mesa", True),     # the bug: phone auto-capitalised first letter
        ("MESA", "mesa", True),     # all caps
        ("  mesa ", "mesa", True),  # surrounding whitespace
        ("mesa", "mesa", True),     # exact
        ("Ñoño", "ñoño", True),     # case-folding on accented capitals
        ("Buenos días", "buenos días", True),  # phrase, only case differs
        ("mama", "mamá", False),    # accents preserved — a real spelling slip
        ("silla", "mesa", False),   # genuinely different word
    ],
)
def test_answers_match_ignores_case_keeps_accents(answer, expected, match):
    assert grading.answers_match(answer, expected) is match
