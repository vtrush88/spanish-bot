"""Языковые профили: всё языкозависимое в одном месте.

Профиль выбирается конфигом (BOT_LANG) и внедряется через dp["profile"].
es-литералы обязаны быть байт-в-байт равны тем, что жили в сервисах и
хендлерах до обобщения (инвариант маминого бота) — их фиксирует
tests/test_languages.py. Не редактировать без сознательного решения
поменять поведение живого испанского бота.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageProfile:
    code: str
    tts_voice: str
    enrichment_system: str
    enrichment_schema: dict
    grading_system: str
    grading_schema: dict
    # .format(prompt_ru=…, expected=…, answer=…)
    grading_user_template: str
    # ключ ответа модели -> нейтральный ключ приложения; прочие ключи as-is
    llm_key_map: dict
    greeting: str
    add_intro: str
    translate_question: str  # шаблон с {}


ES = LanguageProfile(
    code="es",
    tts_voice="es-ES-XimenaNeural",
    enrichment_system=(
        "Ты помогаешь русскоязычному новичку учить испанский язык Испании "
        "(европейский, кастильский — НЕ латиноамериканский вариант). "
        "На вход даётся слово или фраза на испанском ИЛИ на русском. "
        "Определи язык. Верни испанский вариант (spanish) в варианте Испании — "
        "используй пиренейскую лексику (coche, ordenador, móvil, zumo, vale, "
        "vosotros и т.п.), НЕ латиноамериканскую (carro, computadora, celular, jugo). "
        "Дай русский перевод (russian). "
        "transcription — произношение ТОЛЬКО русскими буквами, с ударением "
        "(ударную гласную пиши заглавной). Передавай звуки ЕДИНООБРАЗНО: "
        "ll и y → «й» (calle→кАйе, llave→йАвэ, pollo→пОйо, paella→паЭйя, lluvia→йУвиа); "
        "ñ → «нь» (España→эспАнья, año→Аньо); "
        "j, и g перед e/i → «х» (jamón→хамОн, gente→хЭнте); "
        "h не читается (hola→Ола); "
        "c и z перед e/i → «с» без межзубного (cerveza→сервЭса, gracias→грАсиас). "
        "Добавь короткий "
        "пример-предложение на испанском Испании (example_es) с переводом (example_ru). "
        "Поле kind = 'word' для одного слова, 'phrase' для фразы/предложения. "
        "Всё кратко и для начинающего."
    ),
    enrichment_schema={
        "type": "OBJECT",
        "properties": {
            "kind": {"type": "STRING", "enum": ["word", "phrase"]},
            "spanish": {"type": "STRING"},
            "russian": {"type": "STRING"},
            "transcription": {"type": "STRING"},
            "example_es": {"type": "STRING"},
            "example_ru": {"type": "STRING"},
        },
        "required": ["kind", "spanish", "russian", "transcription",
                     "example_es", "example_ru"],
    },
    grading_system=(
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
    ),
    grading_schema={
        "type": "OBJECT",
        "properties": {
            "verdict": {"type": "STRING", "enum": ["correct", "typo", "wrong"]},
            "correct_spanish": {"type": "STRING"},
            "note": {"type": "STRING"},
        },
        "required": ["verdict", "correct_spanish", "note"],
    },
    grading_user_template=(
        "Русский запрос: {prompt_ru}\n"
        "Ожидаемый испанский: {expected}\n"
        "Ответ ученика: {answer}"
    ),
    llm_key_map={
        "spanish": "word",
        "russian": "translation",
        "example_es": "example",
        "example_ru": "example_translation",
        "correct_spanish": "correct",
    },
    greeting=(
        "¡Hola! 🌞 Я помогу учить испанский.\n\n"
        "• «➕ Добавить слово» — пришли слово или фразу, я переведу, озвучу и "
        "запомню.\n"
        "• «🎴 Карточки», «✍️ Проверить себя», «🎧 Аудирование» — тренировки.\n"
        "• «📖 Мой словарь» — все добавленные слова."
    ),
    add_intro=(
        "Пиши слова или фразы — по одному, на испанском или русском 🙂 "
        "Я сохраню каждое. Когда закончишь, выбери что-нибудь в меню внизу."
    ),
    translate_question="Как по-испански: «{}»?",
)

EN = LanguageProfile(
    code="en",
    tts_voice="en-US-EmmaNeural",
    enrichment_system=(
        "Ты помогаешь русскоязычному ученику среднего уровня (B1-B2) учить "
        "американский английский. На вход даётся слово или фраза на английском "
        "ИЛИ на русском. Определи язык. Верни английский вариант (word) в "
        "американском варианте — американская лексика и спеллинг (apartment, "
        "elevator, color, fall, cookie), НЕ британские (flat, lift, colour, "
        "autumn, biscuit). Дай русский перевод (translation). "
        "transcription — транскрипция IPA в слэшах, вариант General American, "
        "со знаком ударения ˈ для многосложных слов: thought → /θɔːt/, "
        "apartment → /əˈpɑːrtmənt/, comfortable → /ˈkʌmftərbəl/. "
        "НЕ русскими буквами и НЕ британское произношение. "
        "Добавь пример-предложение на английском (example) уровнем чуть выше "
        "среднего (B2+): живые разговорные конструкции, фразовые глаголы, "
        "естественные коллокации — и его русский перевод (example_translation). "
        "Перевод и пояснения — простые, по-русски. "
        "Поле kind = 'word' для одного слова, 'phrase' для фразы/предложения. "
        "Всё кратко."
    ),
    enrichment_schema={
        "type": "OBJECT",
        "properties": {
            "kind": {"type": "STRING", "enum": ["word", "phrase"]},
            "word": {"type": "STRING"},
            "translation": {"type": "STRING"},
            "transcription": {"type": "STRING"},
            "example": {"type": "STRING"},
            "example_translation": {"type": "STRING"},
        },
        "required": ["kind", "word", "translation", "transcription",
                     "example", "example_translation"],
    },
    grading_system=(
        "Ты мягко проверяешь, как русскоязычный ученик перевёл слово/фразу на "
        "английский. Тебе дают: русский запрос, ожидаемый английский перевод и "
        "ответ ученика. Оцени verdict: 'correct' (всё верно), 'typo' (правильно "
        "по сути, но мелкая опечатка — пропущенный апостроф, удвоенная или "
        "пропущенная буква, неверное окончание), 'wrong' (неверно). В correct "
        "дай правильное написание. В note — короткая ДОБАВЛЯЮЩАЯ подсказка "
        "по-русски: для 'typo'/'wrong' — что именно не так (например «пропущен "
        "апостроф», «лишняя буква», «это слово значит …»); для 'correct' — "
        "короткое ободрение или крошечный факт. НЕ дублируй вердикт: слова "
        "«верно», «правильно», «почти» ученик уже видит отдельно, в note их не "
        "повторяй. Пол ученика неизвестен — без гендерных форм в его адрес "
        "(не «написала», «умница»)."
    ),
    grading_schema={
        "type": "OBJECT",
        "properties": {
            "verdict": {"type": "STRING", "enum": ["correct", "typo", "wrong"]},
            "correct": {"type": "STRING"},
            "note": {"type": "STRING"},
        },
        "required": ["verdict", "correct", "note"],
    },
    grading_user_template=(
        "Русский запрос: {prompt_ru}\n"
        "Ожидаемый английский: {expected}\n"
        "Ответ ученика: {answer}"
    ),
    llm_key_map={},
    greeting=(
        "Hi! 🌞 Я помогу учить английский.\n\n"
        "• «➕ Добавить слово» — пришли слово или фразу, я переведу, озвучу и "
        "запомню.\n"
        "• «🎴 Карточки», «✍️ Проверить себя», «🎧 Аудирование» — тренировки.\n"
        "• «📖 Мой словарь» — все добавленные слова."
    ),
    add_intro=(
        "Пиши слова или фразы — по одному, на английском или русском 🙂 "
        "Я сохраню каждое. Когда закончишь, выбери что-нибудь в меню внизу."
    ),
    translate_question="Как по-английски: «{}»?",
)

PROFILES: dict[str, LanguageProfile] = {"es": ES, "en": EN}
