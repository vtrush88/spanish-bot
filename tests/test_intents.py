import pytest

from intents import is_giveup


@pytest.mark.parametrize("text", [
    "не помню", "Не помню", "  не помню  ", "не знаю", "незнаю",
    "непомню", "я не помню это слово", "ой, не знаю(", "не понимаю",
    "хз", "забыла", "пропустить",
])
def test_giveup_detected(text):
    assert is_giveup(text) is True


@pytest.mark.parametrize("text", [
    "comida", "agua", "casa", "помню точно", "знаю — agua", "",
])
def test_real_answers_not_giveup(text):
    assert is_giveup(text) is False
