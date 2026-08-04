# Spanish Bot

Персональный телеграм-тренажёр испанского. Полное описание для агентов — в
[AGENTS.md](AGENTS.md); дизайн — в `docs/superpowers/specs/`.

## Запуск локально

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. Скопировать `.env.example` → `.env`, заполнить:
   - `TELEGRAM_TOKEN` — от @BotFather
   - `GEMINI_API_KEY` — ключ Gemini (Google AI Studio, бесплатно)
   - `ALLOWED_USER_IDS` — Telegram user_id (через запятую)
   - `BOT_LANG` — язык бота: `es` (испанский, дефолт) или `en` (английский)
4. `python bot.py`

## Тесты

`pytest -q`

## Деплой

VPS (DigitalOcean) + systemd. Пошаговый ран-бук:
[`docs/superpowers/deploy.md`](docs/superpowers/deploy.md). Дизайн:
`docs/superpowers/specs/2026-06-15-spanish-bot-deploy-design.md`.
