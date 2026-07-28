from __future__ import annotations

from services import llm as llm_service

REQUIRED_KEYS = ("verdict", "correct_spanish", "note")
VALID_VERDICTS = ("correct", "typo", "wrong")

SYSTEM = (
    "Ты мягко проверяешь, как русскоязычный новичок перевёл слово/фразу на "
    "испанский. Тебе дают: русский запрос, ожидаемый испанский перевод и ответ "
    "ученика. Оцени verdict: 'correct' (всё верно), 'typo' (правильно по сути, "
    "но мелкая опечатка или пропущенный акцент), 'wrong' (неверно). В "
    "correct_spanish дай правильное написание. В note — короткая ДОБАВЛЯЮЩАЯ "
    "подсказка по-русски: для 'typo'/'wrong' — что именно не так (например "
    "«пропущен акцент», «лишняя буква», «это слово значит …»); для 'correct' — "
    "короткое ободрение или крошечный факт. НЕ дублируй вердикт: слова «верно», "
    "«правильно», «почти» ученик уже видит отдельно, в note их не повторяй. "
    "Пол ученика неизвестен — без гендерных форм в его адрес "
    "(не «написала», «умница»)."
)

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "verdict": {"type": "STRING", "enum": list(VALID_VERDICTS)},
        "correct_spanish": {"type": "STRING"},
        "note": {"type": "STRING"},
    },
    "required": list(REQUIRED_KEYS),
}


class GradingError(Exception):
    pass


def answers_match(answer: str, expected: str) -> bool:
    """True if answer equals expected ignoring case and surrounding space.

    Case is folded (so a phone auto-capitalising the first letter — «Mesa» for
    «mesa» — is not treated as a mistake), but accents are preserved
    («mama» ≠ «mamá») so a missing accent still gets corrective feedback.
    """
    return answer.strip().lower() == expected.strip().lower()


def grade(llm: llm_service.LLM, *, prompt_ru: str, expected_es: str,
          answer: str) -> dict:
    user = (
        f"Русский запрос: {prompt_ru}\n"
        f"Ожидаемый испанский: {expected_es}\n"
        f"Ответ ученика: {answer}"
    )
    last_error = None
    for _ in range(2):
        data = llm_service.generate_json(llm, system=SYSTEM, schema=SCHEMA,
                                         text=user)
        if (data is not None
                and all(k in data and data[k] for k in REQUIRED_KEYS)
                and data["verdict"] in VALID_VERDICTS):
            return {k: data[k] for k in REQUIRED_KEYS}
        last_error = "модель вернула ответ без валидной JSON-оценки"
    raise GradingError(last_error or "grading failed")
