from app.telegram.keyboards import (
    ADVISOR_QUICK_SCENARIOS,
    advisor_keyboard,
    advisor_onboarding_keyboard,
    advisor_session_keyboard,
    cancel_keyboard,
    done_keyboard,
)


def test_done_keyboard_menu_only():
    kb = done_keyboard()
    buttons = kb.inline_keyboard
    assert len(buttons) == 1
    assert len(buttons[0]) == 1
    assert buttons[0][0].text == "≡ Меню"
    assert buttons[0][0].callback_data == "nav:menu"


def test_done_keyboard_with_back():
    kb = done_keyboard(back_target="nav:categories")
    buttons = kb.inline_keyboard
    assert len(buttons) == 1
    assert len(buttons[0]) == 2
    assert buttons[0][0].text == "← Назад"
    assert buttons[0][0].callback_data == "nav:categories"
    assert buttons[0][1].text == "≡ Меню"
    assert buttons[0][1].callback_data == "nav:menu"


def test_advisor_keyboard():
    kb = advisor_keyboard()
    buttons = kb.inline_keyboard
    assert len(buttons) == 2
    assert buttons[0][0].text == "🧠 Продолжить в советнике"
    assert buttons[0][0].callback_data == "nav:advisor"
    assert buttons[1][0].text == "📊 Сводка"
    assert buttons[1][1].text == "≡ Меню"


def test_advisor_onboarding_keyboard_contains_quick_scenarios():
    kb = advisor_onboarding_keyboard()
    all_callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    for slug, _label in ADVISOR_QUICK_SCENARIOS:
        assert f"advisor:scenario:{slug}" in all_callbacks
    assert "nav:menu" in all_callbacks


def test_advisor_session_keyboard_contains_quick_followups():
    kb = advisor_session_keyboard()
    all_callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "advisor:scenario:budget_risks" in all_callbacks
    assert "advisor:scenario:upcoming" in all_callbacks
    assert "advisor:scenario:export" in all_callbacks
    assert "nav:advisor" in all_callbacks
    assert "nav:menu" in all_callbacks


def test_cancel_keyboard():
    kb = cancel_keyboard("nav:settings")
    buttons = kb.inline_keyboard
    assert len(buttons) == 1
    assert len(buttons[0]) == 1
    assert buttons[0][0].text == "❌ Отмена"
    assert buttons[0][0].callback_data == "nav:settings"
