"""Tests for ApplyAction payload validation (C2 / B2.2)."""
import pytest
from app.services.apply_action import ApplyAction, ApplyActionType


def _make_action(action_type: ApplyActionType, payload: dict) -> ApplyAction:
    return ApplyAction(
        action_type=action_type,
        label="test",
        payload=payload,
        preview_text="test",
        is_reversible=False,
    )


def test_set_budget_missing_category_raises() -> None:
    with pytest.raises(ValueError, match="missing payload fields"):
        _make_action(ApplyActionType.SET_BUDGET, {"suggested_limit": 5000.0})


def test_set_budget_missing_amount_raises() -> None:
    with pytest.raises(ValueError, match="missing payload fields"):
        _make_action(ApplyActionType.SET_BUDGET, {"category": "food"})


def test_set_budget_valid_does_not_raise() -> None:
    action = _make_action(ApplyActionType.SET_BUDGET, {"category": "food", "suggested_limit": 5000.0})
    assert action.action_type == ApplyActionType.SET_BUDGET


def test_set_reminder_missing_payment_date_raises() -> None:
    with pytest.raises(ValueError, match="missing payload fields"):
        _make_action(ApplyActionType.SET_REMINDER, {"description": "Аренда", "amount": 1000.0})


def test_all_known_action_types_have_required_fields_defined() -> None:
    """Все типы с непустым required_fields присутствуют в REQUIRED_PAYLOAD_FIELDS."""
    from app.services.apply_action import REQUIRED_PAYLOAD_FIELDS
    # Эти типы должны иметь определённые required поля
    required_types = [
        "set_budget", "set_total_budget", "add_planned_expense",
        "set_reminder", "update_planned_expense", "delete_planned_expense",
        "delete_reminder",
    ]
    for t in required_types:
        assert t in REQUIRED_PAYLOAD_FIELDS, f"{t} not in REQUIRED_PAYLOAD_FIELDS"
        assert len(REQUIRED_PAYLOAD_FIELDS[t]) > 0


def test_callback_data_under_64_bytes() -> None:
    """to_callback_data() должен возвращать строку <= 64 байт."""
    action = _make_action(
        ApplyActionType.SET_BUDGET,
        {"category": "food", "suggested_limit": 5000.0},
    )
    data = action.to_callback_data()
    assert len(data.encode()) <= 64, f"callback_data too long: {len(data.encode())} bytes"


def test_add_planned_expense_missing_planned_date_raises() -> None:
    with pytest.raises(ValueError, match="missing payload fields"):
        _make_action(ApplyActionType.ADD_PLANNED_EXPENSE, {"title": "test", "amount": 100.0})
