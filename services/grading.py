from __future__ import annotations

from languages import LanguageProfile
from services import llm as llm_service

REQUIRED_KEYS = ("verdict", "correct", "note")
VALID_VERDICTS = ("correct", "typo", "wrong")


class GradingError(Exception):
    pass


def answers_match(answer: str, expected: str) -> bool:
    """True if answer equals expected ignoring case and surrounding space.

    Case is folded (so a phone auto-capitalising the first letter — «Mesa» for
    «mesa» — is not treated as a mistake), but accents are preserved
    («mama» ≠ «mamá») so a missing accent still gets corrective feedback.
    """
    return answer.strip().lower() == expected.strip().lower()


def grade(llm: llm_service.LLM, profile: LanguageProfile, *, prompt_ru: str,
          expected: str, answer: str) -> dict:
    user = profile.grading_user_template.format(
        prompt_ru=prompt_ru, expected=expected, answer=answer)
    last_error = None
    for _ in range(2):
        data = llm_service.generate_json(
            llm, system=profile.grading_system, schema=profile.grading_schema,
            text=user, max_output_tokens=256)
        if data is not None:
            mapped = {profile.llm_key_map.get(k, k): v for k, v in data.items()}
            if (all(k in mapped and mapped[k] for k in REQUIRED_KEYS)
                    and mapped["verdict"] in VALID_VERDICTS):
                return {k: mapped[k] for k in REQUIRED_KEYS}
        last_error = "модель вернула ответ без валидной JSON-оценки"
    raise GradingError(last_error or "grading failed")
