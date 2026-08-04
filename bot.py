from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.fsm.storage.memory import MemoryStorage
from google import genai
from google.genai import types as genai_types

import config
import db
import languages
from handlers import add, menu, training
from services import llm as llm_service

async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cfg = config.load()

    conn = db.connect(cfg.db_path)
    db.init_db(conn)
    gemini_client = genai.Client(
        api_key=cfg.gemini_api_key,
        # ms; hung request must not park a to_thread worker forever
        http_options=genai_types.HttpOptions(timeout=30_000),
    )
    models = (cfg.gemini_model,)
    if cfg.gemini_fallback_model:
        models += (cfg.gemini_fallback_model,)

    bot = Bot(token=cfg.telegram_token)
    dp = Dispatcher(storage=MemoryStorage())

    # Inject shared deps into every handler via the data dict.
    dp["conn"] = conn
    dp["llm"] = llm_service.LLM(client=gemini_client, models=models)
    dp["profile"] = languages.PROFILES[cfg.bot_lang]

    # Access control: ignore anyone not in the allow-list.
    dp.message.filter(F.from_user.id.in_(cfg.allowed_user_ids))
    dp.callback_query.filter(F.from_user.id.in_(cfg.allowed_user_ids))

    dp.include_router(menu.router)
    dp.include_router(add.router)
    dp.include_router(training.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
