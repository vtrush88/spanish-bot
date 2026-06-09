from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.fsm.storage.memory import MemoryStorage
from anthropic import Anthropic

import config
import db
from handlers import add, menu, training

DB_PATH = "spanish_bot.db"


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cfg = config.load()

    conn = db.connect(DB_PATH)
    db.init_db(conn)
    anthropic_client = Anthropic(api_key=cfg.anthropic_api_key)

    bot = Bot(token=cfg.telegram_token)
    dp = Dispatcher(storage=MemoryStorage())

    # Inject shared deps into every handler via the data dict.
    dp["conn"] = conn
    dp["anthropic"] = anthropic_client

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
