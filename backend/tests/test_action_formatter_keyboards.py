"""Tests for format_action_result and undo/back keyboards."""
import pytest


def _make_result(success: bool, message: str, detail: str = "", is_reversible: bool = False, undo_payload: dict | None = None):
    from app.services.action_service import ActionResult, ActionStatus
    return ActionResult(
        status=ActionStatus.SUCCESS if success else ActionStatus.FAILURE,
        action_type="set_budget",
        message=message,
        detail=detail,
        is_reversible=is_reversible,
        undo_payload=undo_payload or {},
    )


def test_format_success_result() -> None:
    from app.telegram.formatter import AdvisorFormatter
    formatter = AdvisorFormatter()
    result = _make_result(True, "✅ Бюджет установлен")
    text = formatter.format_action_result(result)
    assert "✅ Бюджет установлен" in text
    assert "❌" not in text


def test_format_failure_result_shows_error_icon() -> None:
    from app.telegram.formatter import AdvisorFormatter
    formatter = AdvisorFormatter()
    result = _make_result(False, "Данные не найдены")
    text = formatter.format_action_result(result)
    assert "❌" in text
    assert "Данные не найдены" in text


def test_format_detail_shown_in_italic() -> None:
    from app.telegram.formatter import AdvisorFormatter
    formatter = AdvisorFormatter()
    result = _make_result(True, "✅ Готово", detail="Бюджет на месяц")
    text = formatter.format_action_result(result)
    assert "<i>Бюджет на месяц</i>" in text


def test_undo_keyboard_shows_undo_button_when_reversible() -> None:
    from app.telegram.keyboards import undo_keyboard
    result = _make_result(True, "ok", is_reversible=True, undo_payload={"action_type": "set_budget", "category": "food", "old_amount": 0.0})
    kb = undo_keyboard(result)
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    callback_datas = [btn.callback_data for btn in all_buttons]
    assert "action:undo" in callback_datas


def test_undo_keyboard_no_undo_button_when_not_reversible() -> None:
    from app.telegram.keyboards import undo_keyboard
    result = _make_result(True, "ok", is_reversible=False, undo_payload={})
    kb = undo_keyboard(result)
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    callback_datas = [btn.callback_data for btn in all_buttons]
    assert "action:undo" not in callback_datas
    assert "nav:advisor" in callback_datas


def test_back_keyboard_has_nav_buttons() -> None:
    from app.telegram.keyboards import back_keyboard
    kb = back_keyboard()
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    callback_datas = [btn.callback_data for btn in all_buttons]
    assert "nav:advisor" in callback_datas
    assert "nav:menu" in callback_datas
    assert "action:undo" not in callback_datas
