from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    telegram_token: str
    gemini_api_key: str
    gemini_model: str
    gemini_fallback_model: str
    allowed_user_ids: set[int]
    db_path: str


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Missing required env var: {name}")
    return value


def load() -> Config:
    load_dotenv()
    raw_ids = _require("ALLOWED_USER_IDS")
    ids = {int(part.strip()) for part in raw_ids.split(",") if part.strip()}
    return Config(
        telegram_token=_require("TELEGRAM_TOKEN"),
        gemini_api_key=_require("GEMINI_API_KEY"),
        # `or`: пустая строка в .env не должна дать models=("",)
        gemini_model=os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash",
        gemini_fallback_model=os.environ.get(
            "GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite"),
        allowed_user_ids=ids,
        db_path=os.environ.get("DB_PATH", "spanish_bot.db"),
    )
