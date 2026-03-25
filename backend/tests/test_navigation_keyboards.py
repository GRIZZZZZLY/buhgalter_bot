from app.telegram.keyboards import done_keyboard, advisor_keyboard, cancel_keyboard


def test_done_keyboard_menu_only():
    kb = done_keyboard()
    buttons = kb.inline_keyboard
    assert len(buttons) == 1  # one row
    assert len(buttons[0]) == 1  # one button
    assert buttons[0][0].text == "≡ Меню"
    assert buttons[0][0].callback_data == "nav:menu"


def test_done_keyboard_with_back():
    kb = done_keyboard(back_target="nav:categories")
    buttons = kb.inline_keyboard
    assert len(buttons) == 1
    assert len(buttons[0]) == 2  # back + menu
    assert buttons[0][0].text == "← Назад"
    assert buttons[0][0].callback_data == "nav:categories"
    assert buttons[0][1].text == "≡ Меню"
    assert buttons[0][1].callback_data == "nav:menu"


def test_advisor_keyboard():
    kb = advisor_keyboard()
    buttons = kb.inline_keyboard
    assert len(buttons) == 1
    assert len(buttons[0]) == 2
    assert buttons[0][0].text == "📊 Сводка"
    assert buttons[0][0].callback_data == "nav:stats"
    assert buttons[0][1].text == "≡ Меню"


def test_cancel_keyboard():
    kb = cancel_keyboard("nav:settings")
    buttons = kb.inline_keyboard
    assert len(buttons) == 1
    assert len(buttons[0]) == 1
    assert buttons[0][0].text == "❌ Отмена"
    assert buttons[0][0].callback_data == "nav:settings"
