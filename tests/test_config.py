import pytest

import config


def test_load_parses_env(monkeypatch):
    # Neutralize load_dotenv so a real local .env can't leak into the test.
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok123")
    monkeypatch.setenv("GEMINI_API_KEY", "key456")
    monkeypatch.setenv("ALLOWED_USER_IDS", "111, 222 ,333")
    cfg = config.load()
    assert cfg.telegram_token == "tok123"
    assert cfg.gemini_api_key == "key456"
    assert cfg.allowed_user_ids == {111, 222, 333}


def test_missing_required_raises(monkeypatch):
    # Neutralize load_dotenv so a real local .env can't repopulate the var.
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    import pytest
    with pytest.raises(ValueError, match="TELEGRAM_TOKEN"):
        config.load()


def test_load_defaults_db_path(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    monkeypatch.delenv("DB_PATH", raising=False)
    cfg = config.load()
    assert cfg.db_path == "spanish_bot.db"


def test_load_reads_db_path(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    monkeypatch.setenv("DB_PATH", "/var/lib/spanish-bot/spanish_bot.db")
    cfg = config.load()
    assert cfg.db_path == "/var/lib/spanish-bot/spanish_bot.db"


def test_gemini_model_defaults(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_FALLBACK_MODEL", raising=False)
    cfg = config.load()
    assert cfg.gemini_model == "gemini-3.5-flash"
    assert cfg.gemini_fallback_model == "gemini-3.5-flash-lite"


def test_gemini_model_overrides(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.0-flash")
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "")
    cfg = config.load()
    assert cfg.gemini_model == "gemini-3.0-flash"
    assert cfg.gemini_fallback_model == ""


def test_empty_gemini_model_falls_back_to_default(monkeypatch):
    # Пустая GEMINI_MODEL= в .env не должна дать models=("",)
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    monkeypatch.setenv("GEMINI_MODEL", "")
    cfg = config.load()
    assert cfg.gemini_model == "gemini-3.5-flash"


def test_bot_lang_defaults_to_es(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    monkeypatch.delenv("BOT_LANG", raising=False)
    cfg = config.load()
    assert cfg.bot_lang == "es"


def test_bot_lang_en_is_picked_up(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    monkeypatch.setenv("BOT_LANG", "en")
    cfg = config.load()
    assert cfg.bot_lang == "en"


def test_bot_lang_unknown_raises(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    monkeypatch.setenv("BOT_LANG", "de")
    with pytest.raises(ValueError, match="BOT_LANG"):
        config.load()


def test_bot_lang_empty_string_falls_back_to_es(monkeypatch):
    # Пустая BOT_LANG= в .env не должна ронять старт.
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    monkeypatch.setenv("BOT_LANG", "")
    cfg = config.load()
    assert cfg.bot_lang == "es"
