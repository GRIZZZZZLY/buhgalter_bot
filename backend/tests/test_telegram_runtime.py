from telegram import InlineKeyboardMarkup

from app.core.settings import get_settings
from app.telegram.keyboards import (
    start_keyboard,
    voice_confirmation_keyboard,
    category_resolution_keyboard,
    budgets_inline_keyboard,
    budget_category_keyboard,
    budget_confirm_keyboard,
    budget_cat_confirm_keyboard,
    settings_nav_inline_keyboard,
)


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
    assert keyboard.inline_keyboard


def test_settings_expose_telegram_mode(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_MODE", "polling")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.telegram_mode == "polling"


def test_voice_placeholder_copy_text() -> None:
    assert "Обрабатываю голосовое" in "🎤 Обрабатываю голосовое…"


# ---------------------------------------------------------------------------
# Budget keyboards
# ---------------------------------------------------------------------------

def _all_callbacks(keyboard: InlineKeyboardMarkup) -> set[str]:
    return {btn.callback_data for row in keyboard.inline_keyboard for btn in row if btn.callback_data}


def test_budgets_inline_keyboard_has_set_total_and_pick_category() -> None:
    kb = budgets_inline_keyboard()
    callbacks = _all_callbacks(kb)
    assert "budget:set_total" in callbacks
    assert "budget:pick_category" in callbacks
    assert "nav:menu" in callbacks


def test_budget_category_keyboard_has_category_buttons_and_back() -> None:
    cats = [("food", "🍽 Еда"), ("transport", "🚌 Транспорт"), ("housing", "🏠 Аренда")]
    kb = budget_category_keyboard(cats)
    callbacks = _all_callbacks(kb)
    assert "budget:set_category:food" in callbacks
    assert "budget:set_category:transport" in callbacks
    assert "budget:set_category:housing" in callbacks
    assert "nav:budgets" in callbacks


def test_budget_confirm_keyboard_has_confirm_and_cancel() -> None:
    kb = budget_confirm_keyboard()
    callbacks = _all_callbacks(kb)
    assert "budget:total_confirm" in callbacks
    assert "budget:total_cancel" in callbacks


def test_budget_cat_confirm_keyboard_has_confirm_and_cancel() -> None:
    kb = budget_cat_confirm_keyboard()
    callbacks = _all_callbacks(kb)
    assert "budget:cat_confirm" in callbacks
    assert "budget:cat_cancel" in callbacks


def test_settings_nav_keyboard_has_no_budget_button() -> None:
    """Regression: 'Бюджет на месяц' removed from settings — lives in Budgets screen now."""
    callbacks = _all_callbacks(settings_nav_inline_keyboard())
    assert "settings:budget" not in callbacks


def test_settings_nav_keyboard_has_budget_day_and_reminders() -> None:
    callbacks = _all_callbacks(settings_nav_inline_keyboard())
    assert "settings:budget_day" in callbacks
    assert "settings:reminders" in callbacks
