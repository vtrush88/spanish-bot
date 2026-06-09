# Spanish Bot

Персональный телеграм-тренажёр испанского. Полное описание для агентов — в
[AGENTS.md](AGENTS.md); дизайн — в `docs/superpowers/specs/`.

## Запуск локально

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. Скопировать `.env.example` → `.env`, заполнить:
   - `TELEGRAM_TOKEN` — от @BotFather
   - `ANTHROPIC_API_KEY` — ключ Anthropic
   - `ALLOWED_USER_IDS` — Telegram user_id (через запятую)
4. `python bot.py`

## Тесты

`pytest -q`

## Деплой

Управляемый хост (Railway / Fly.io): задеплоить процесс `python bot.py`,
проставить переменные окружения, том для `spanish_bot.db`.
