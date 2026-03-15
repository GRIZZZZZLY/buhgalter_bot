from pathlib import Path

from app.core.settings import get_settings


def test_env_example_exists() -> None:
    assert Path(".env.example").exists()


def test_settings_can_read_env_example_defaults(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_MODE", "polling")
    monkeypatch.setenv("FFMPEG_BIN", "/usr/bin/ffmpeg")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.telegram_mode == "polling"
    assert settings.ffmpeg_bin == "/usr/bin/ffmpeg"
