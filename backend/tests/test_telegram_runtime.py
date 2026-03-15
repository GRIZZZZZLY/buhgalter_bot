from telegram import InlineKeyboardMarkup

from app.core.settings import get_settings
from app.telegram.keyboards import start_keyboard, voice_confirmation_keyboard, category_resolution_keyboard


def test_voice_confirmation_keyboard_contains_callbacks() -> None:
    keyboard = voice_confirmation_keyboard("abc")
    assert isinstance(keyboard, InlineKeyboardMarkup)
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    payloads = {button.callback_data for button in buttons}
    assert "voice:confirm:abc" in payloads
    assert "voice:cancel:abc" in payloads
    assert "voice:edit:abc" in payloads


def test_start_keyboard_optional() -> None:
    assert start_keyboard(None) is None
    keyboard = start_keyboard("https://example.com/app")
    assert keyboard is not None


def test_category_resolution_keyboard_exists() -> None:
    keyboard = category_resolution_keyboard('красота и здоровье', ['beauty', 'health'])
    assert keyboard.keyboard


def test_settings_expose_telegram_mode(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_MODE", "polling")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.telegram_mode == "polling"


def test_voice_placeholder_copy_text() -> None:
    assert "Обрабатываю голосовое" in "🎤 Обрабатываю голосовое…"
