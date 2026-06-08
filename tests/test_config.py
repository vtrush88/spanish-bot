import config


def test_load_parses_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok123")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key456")
    monkeypatch.setenv("ALLOWED_USER_IDS", "111, 222 ,333")
    cfg = config.load()
    assert cfg.telegram_token == "tok123"
    assert cfg.anthropic_api_key == "key456"
    assert cfg.allowed_user_ids == {111, 222, 333}


def test_missing_required_raises(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    import pytest
    with pytest.raises(ValueError, match="TELEGRAM_TOKEN"):
        config.load()
