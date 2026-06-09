from __future__ import annotations

MODEL = "claude-haiku-4-5-20251001"
REQUIRED_KEYS = ("verdict", "correct_spanish", "note")

SYSTEM = (
    "Ты мягко проверяешь, как русскоязычный новичок перевёл слово/фразу на "
    "испанский. Тебе дают: русский запрос, ожидаемый испанский перевод и ответ "
    "ученика. Оцени verdict: 'correct' (всё верно), 'typo' (правильно по сути, "
    "но мелкая опечатка/регистр/акцент), 'wrong' (неверно). В correct_spanish "
    "дай правильное написание. В note — короткое доброе пояснение по-русски."
)

TOOL = {
    "name": "save_grade",
    "description": "Сохранить оценку перевода.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string",
                        "enum": ["correct", "typo", "wrong"]},
            "correct_spanish": {"type": "string"},
            "note": {"type": "string"},
        },
        "required": list(REQUIRED_KEYS),
    },
}


class GradingError(Exception):
    pass


def _extract(response) -> dict | None:
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "save_grade":
            data = block.input
            if all(k in data and data[k] for k in REQUIRED_KEYS):
                return {k: data[k] for k in REQUIRED_KEYS}
    return None


def grade(client, *, prompt_ru: str, expected_es: str, answer: str) -> dict:
    user = (
        f"Русский запрос: {prompt_ru}\n"
        f"Ожидаемый испанский: {expected_es}\n"
        f"Ответ ученика: {answer}"
    )
    last_error = None
    for _ in range(2):
        response = client.messages.create(
            model=MODEL,
            max_tokens=256,
            system=[{"type": "text", "text": SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "save_grade"},
            messages=[{"role": "user", "content": user}],
        )
        result = _extract(response)
        if result is not None:
            return result
        last_error = "Claude вернул ответ без валидного tool_use save_grade"
    raise GradingError(last_error or "grading failed")
