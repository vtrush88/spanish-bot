from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    telegram_token: str
    anthropic_api_key: str
    allowed_user_ids: set[int]


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
        anthropic_api_key=_require("ANTHROPIC_API_KEY"),
        allowed_user_ids=ids,
    )
