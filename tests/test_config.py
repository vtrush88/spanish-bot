import config


def test_load_parses_env(monkeypatch):
    # Neutralize load_dotenv so a real local .env can't leak into the test.
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok123")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key456")
    monkeypatch.setenv("ALLOWED_USER_IDS", "111, 222 ,333")
    cfg = config.load()
    assert cfg.telegram_token == "tok123"
    assert cfg.anthropic_api_key == "key456"
    assert cfg.allowed_user_ids == {111, 222, 333}


def test_missing_required_raises(monkeypatch):
    # Neutralize load_dotenv so a real local .env can't repopulate the var.
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    import pytest
    with pytest.raises(ValueError, match="TELEGRAM_TOKEN"):
        config.load()


def test_load_defaults_db_path(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    monkeypatch.delenv("DB_PATH", raising=False)
    cfg = config.load()
    assert cfg.db_path == "spanish_bot.db"


def test_load_reads_db_path(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    monkeypatch.setenv("DB_PATH", "/var/lib/spanish-bot/spanish_bot.db")
    cfg = config.load()
    assert cfg.db_path == "/var/lib/spanish-bot/spanish_bot.db"
