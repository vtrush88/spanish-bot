# Lang Trainer Bot

Personal vocabulary-trainer Telegram bot (Russian UI). One codebase, deployable
per language: Spanish (`@SimpleSpanishBot`) and American English
(`@EnglishUpgradeBot`). Full agent-facing overview — in [AGENTS.md](AGENTS.md)
(in Russian); design specs — in `docs/superpowers/specs/`.

## Run locally

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. Copy `.env.example` → `.env` and fill in:
   - `TELEGRAM_TOKEN` — from @BotFather
   - `GEMINI_API_KEY` — Gemini API key (Google AI Studio, free tier)
   - `ALLOWED_USER_IDS` — Telegram user ids (comma-separated)
   - `BOT_LANG` — optional bot language: `es` (Spanish, default) or `en` (English)
4. `python bot.py`

## Tests

`pytest -q`

## Deploy

VPS (DigitalOcean) + systemd. Step-by-step run-book:
[`docs/superpowers/deploy.md`](docs/superpowers/deploy.md) (in Russian). Design:
`docs/superpowers/specs/2026-06-15-spanish-bot-deploy-design.md`.
