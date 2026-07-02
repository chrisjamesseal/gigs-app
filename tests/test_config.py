"""Tests for configuration defaults."""

from src.config import get_config


def test_defaults(monkeypatch):
    for var in ("LOOKAHEAD_DAYS", "FOLLOWED_ONLY", "DB_PATH"):
        monkeypatch.delenv(var, raising=False)
    get_config.cache_clear()
    config = get_config()
    assert config.lookahead_days == 180  # 6 months
    assert config.followed_only is True  # only artists you follow
    get_config.cache_clear()


def test_followed_only_can_be_disabled(monkeypatch):
    monkeypatch.setenv("FOLLOWED_ONLY", "false")
    get_config.cache_clear()
    assert get_config().followed_only is False
    get_config.cache_clear()
