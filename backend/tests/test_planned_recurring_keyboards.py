from app.telegram.keyboards import (
    main_menu_inline_keyboard,
    planned_input_keyboard,
    recurring_input_keyboard,
    planned_confirm_keyboard,
    recurring_confirm_keyboard,
)


def _all_callbacks(kb):
    return [btn.callback_data for row in kb.inline_keyboard for btn in row]


def test_main_menu_has_planned_input_button():
    cbs = _all_callbacks(main_menu_inline_keyboard())
    assert "nav:planned_input" in cbs
    assert "nav:recurring_input" in cbs


def test_planned_input_keyboard_has_list_and_back():
    cbs = _all_callbacks(planned_input_keyboard())
    assert "nav:planned_list" in cbs
    assert "nav:menu" in cbs


def test_recurring_input_keyboard_has_list_and_back():
    cbs = _all_callbacks(recurring_input_keyboard())
    assert "nav:recurring_list" in cbs
    assert "nav:menu" in cbs


def test_planned_confirm_keyboard_callbacks():
    cbs = _all_callbacks(planned_confirm_keyboard())
    assert "planned_input:confirm" in cbs
    assert "planned_input:cancel" in cbs


def test_recurring_confirm_keyboard_callbacks():
    cbs = _all_callbacks(recurring_confirm_keyboard())
    assert "recurring_input:confirm" in cbs
    assert "recurring_input:cancel" in cbs
