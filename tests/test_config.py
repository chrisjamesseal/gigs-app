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


def test_dice_disabled_by_default(monkeypatch):
    # dice.fm blocks datacenter IPs, so it's off unless explicitly forced on.
    monkeypatch.delenv("DICE_ENABLED", raising=False)
    get_config.cache_clear()
    assert get_config().dice_enabled is False
    monkeypatch.setenv("DICE_ENABLED", "true")
    get_config.cache_clear()
    assert get_config().dice_enabled is True
    get_config.cache_clear()
