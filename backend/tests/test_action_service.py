from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.services.action_service import ActionResult, ActionService, ActionStatus
from app.services.apply_action import ApplyAction, ApplyActionType


def _make_action(action_type: ApplyActionType, payload: dict, label: str = "test") -> ApplyAction:
    return ApplyAction(
        action_type=action_type,
        label=label,
        payload=payload,
        preview_text="preview",
        is_reversible=True,
    )


def test_set_budget_success(db_session: Session) -> None:
    """SET_BUDGET creates/updates category budget and returns success."""
    action = _make_action(
        ApplyActionType.SET_BUDGET,
        {"category": "food", "suggested_limit": 5000.0},
        label="Поставить бюджет «еда» 5000 ₽/мес",
    )
    svc = ActionService(db_session)
    result = svc.execute(action, telegram_user_id=555)

    assert isinstance(result, ActionResult)
    assert result.success is True
    assert "5000" in result.message

    from app.repositories.category_budget_repository import CategoryBudgetRepository
    repo = CategoryBudgetRepository(db_session)
    budget = repo.get(555, "food")
    assert budget is not None
    assert float(budget.amount) == 5000.0


def test_set_budget_missing_payload_raises_at_construction(db_session: Session) -> None:
    """SET_BUDGET with missing keys in payload raises ValueError at construction."""
    with pytest.raises(ValueError, match="missing payload fields"):
        _make_action(ApplyActionType.SET_BUDGET, {})


def test_set_reminder_creates_planned_expense(db_session: Session) -> None:
    """SET_REMINDER creates a planned expense with category 'other' and reminder_time 09:00."""
    action = _make_action(
        ApplyActionType.SET_REMINDER,
        {
            "description": "Аренда",
            "amount": 30000.0,
            "payment_date": "2026-04-03",
        },
    )
    svc = ActionService(db_session)
    result = svc.execute(action, telegram_user_id=777)

    assert result.success is True
    assert "Аренда" in result.message
    assert "2026-04-03" in result.message

    from app.services.planned_expense_service import PlannedExpenseService
    pe_svc = PlannedExpenseService(db_session)
    items = pe_svc.list_future(777)
    assert len(items) == 1
    assert items[0].title == "Аренда"
    assert float(items[0].amount) == 30000.0
    assert items[0].category == "other"
    assert str(items[0].planned_date) == "2026-04-03"


def test_add_planned_expense_creates_record(db_session: Session) -> None:
    """ADD_PLANNED_EXPENSE creates a planned expense record."""
    action = _make_action(
        ApplyActionType.ADD_PLANNED_EXPENSE,
        {
            "title": "Страховка",
            "amount": 5000.0,
            "category": "other",
            "planned_date": "2026-05-01",
        },
    )
    svc = ActionService(db_session)
    result = svc.execute(action, telegram_user_id=888)

    assert result.success is True
    assert "Страховка" in result.message
    assert "2026-05-01" in result.message

    from app.services.planned_expense_service import PlannedExpenseService
    pe_svc = PlannedExpenseService(db_session)
    items = pe_svc.list_future(888)
    assert len(items) == 1
    assert items[0].title == "Страховка"
    assert float(items[0].amount) == 5000.0


def test_set_total_budget_returns_graceful_failure(db_session: Session) -> None:
    """SET_TOTAL_BUDGET is not implemented — returns graceful failure message."""
    action = _make_action(
        ApplyActionType.SET_TOTAL_BUDGET,
        {"amount": 100000.0},
    )
    svc = ActionService(db_session)
    result = svc.execute(action, telegram_user_id=999)

    assert isinstance(result, ActionResult)
    assert result.success is False
    assert result.message  # non-empty explanation


def test_set_budget_idempotent_update(db_session: Session) -> None:
    """Repeated SET_BUDGET updates the existing budget, does not create a duplicate."""
    svc = ActionService(db_session)

    action1 = _make_action(ApplyActionType.SET_BUDGET, {"category": "transport", "suggested_limit": 3000.0})
    svc.execute(action1, telegram_user_id=111)

    action2 = _make_action(ApplyActionType.SET_BUDGET, {"category": "transport", "suggested_limit": 4500.0})
    result = svc.execute(action2, telegram_user_id=111)

    assert result.success is True
    assert "4500" in result.message

    from app.repositories.category_budget_repository import CategoryBudgetRepository
    repo = CategoryBudgetRepository(db_session)
    budgets = repo.get_all_for_user(111)
    transport_budgets = [b for b in budgets if b.category == "transport"]
    assert len(transport_budgets) == 1
    assert float(transport_budgets[0].amount) == 4500.0


# ------------------------------------------------------------------
# Undo tests
# ------------------------------------------------------------------

def test_undo_set_budget_restores_old_value(db_session: Session) -> None:
    """undo SET_BUDGET восстанавливает предыдущее значение."""
    from app.repositories.category_budget_repository import CategoryBudgetRepository
    repo = CategoryBudgetRepository(db_session)
    repo.upsert(555, "food", 3000.0)
    db_session.commit()

    action = ApplyAction(
        action_type=ApplyActionType.SET_BUDGET,
        label="Бюджет еда 5000",
        payload={"category": "food", "suggested_limit": 5000.0},
        preview_text="...",
        is_reversible=True,
    )
    svc = ActionService(db_session)
    result = svc.execute(action, telegram_user_id=555)
    assert result.success is True
    assert result.is_reversible is True
    assert result.undo_payload["old_amount"] == 3000.0

    undo_result = svc.undo(result.undo_payload, telegram_user_id=555)
    assert undo_result.success is True
    budget = repo.get(555, "food")
    assert float(budget.amount) == 3000.0


def test_undo_set_budget_deletes_if_was_zero(db_session: Session) -> None:
    """undo SET_BUDGET удаляет бюджет если его не было."""
    action = ApplyAction(
        action_type=ApplyActionType.SET_BUDGET,
        label="Бюджет транспорт 2000",
        payload={"category": "transport", "suggested_limit": 2000.0},
        preview_text="...",
        is_reversible=True,
    )
    svc = ActionService(db_session)
    result = svc.execute(action, telegram_user_id=555)
    assert result.undo_payload["old_amount"] == 0.0

    undo_result = svc.undo(result.undo_payload, telegram_user_id=555)
    assert undo_result.success is True
    from app.repositories.category_budget_repository import CategoryBudgetRepository
    repo = CategoryBudgetRepository(db_session)
    assert repo.get(555, "transport") is None


def test_undo_add_planned_expense_deletes_record(db_session: Session) -> None:
    """undo ADD_PLANNED_EXPENSE удаляет созданную запись."""
    action = ApplyAction(
        action_type=ApplyActionType.ADD_PLANNED_EXPENSE,
        label="Страховка",
        payload={"title": "Страховка", "amount": 5000.0, "category": "other", "planned_date": "2026-06-01"},
        preview_text="...",
        is_reversible=False,
    )
    svc = ActionService(db_session)
    result = svc.execute(action, telegram_user_id=555)
    assert result.success is True
    planned_id = result.undo_payload["planned_id"]

    undo_result = svc.undo(result.undo_payload, telegram_user_id=555)
    assert undo_result.success is True
    from app.services.planned_expense_service import PlannedExpenseService
    pe_svc = PlannedExpenseService(db_session)
    items = pe_svc.list_future(555)
    assert not any(i.id == planned_id for i in items)


def test_undo_set_reminder_deletes_record(db_session) -> None:
    """undo SET_REMINDER удаляет созданное напоминание."""
    action = ApplyAction(
        action_type=ApplyActionType.SET_REMINDER,
        label="Напомнить об «Аренда»",
        payload={
            "description": "Аренда",
            "amount": 30000.0,
            "payment_date": "2026-07-03",
        },
        preview_text="...",
        is_reversible=False,
    )
    svc = ActionService(db_session)
    result = svc.execute(action, telegram_user_id=555)
    assert result.success is True
    planned_id = result.undo_payload["planned_id"]

    undo_result = svc.undo(result.undo_payload, telegram_user_id=555)
    assert undo_result.success is True
    from app.services.planned_expense_service import PlannedExpenseService
    pe_svc = PlannedExpenseService(db_session)
    items = pe_svc.list_future(555)
    assert not any(i.id == planned_id for i in items)
