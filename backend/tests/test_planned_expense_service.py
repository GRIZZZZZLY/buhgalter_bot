from datetime import date, timedelta

from app.services.planned_expense_service import PlannedExpenseService
from app.services.transaction_service import TransactionService


def test_create_manual_planned_expense_does_not_affect_balance(db_session) -> None:
    service = PlannedExpenseService(db_session)
    tx_service = TransactionService(db_session)

    item = service.create_manual(
        telegram_user_id=555,
        title="Маникюр",
        amount=2100,
        category="beauty",
        planned_date=date.today() + timedelta(days=7),
    )

    summary = tx_service.get_summary(telegram_user_id=555, period="month")
    future = service.list_future(telegram_user_id=555)

    assert item.status == "pending"
    assert item.title == "Маникюр"
    assert item.category == "beauty"
    assert item.amount == "2100.00"
    assert summary.balance == "0.00"
    assert summary.expense_total == "0.00"
    assert len(future) == 1


def test_confirm_planned_expense_creates_transaction_and_marks_confirmed(db_session) -> None:
    service = PlannedExpenseService(db_session)
    tx_service = TransactionService(db_session)

    item = service.create_manual(
        telegram_user_id=555,
        title="Маникюр",
        amount=2100,
        category="beauty",
        planned_date=date.today(),
    )

    result = service.confirm_expense(telegram_user_id=555, planned_expense_id=item.id)
    summary = tx_service.get_summary(telegram_user_id=555, period="month")
    future = service.list_future(telegram_user_id=555)

    assert result.planned.status == "confirmed"
    assert result.transaction is not None
    assert result.transaction.amount == "2100.00"
    assert result.transaction.category == "beauty"
    assert summary.expense_total == "2100.00"
    assert future == []


def test_confirm_planned_expense_with_new_amount_uses_override(db_session) -> None:
    service = PlannedExpenseService(db_session)
    tx_service = TransactionService(db_session)

    item = service.create_manual(
        telegram_user_id=555,
        title="Маникюр",
        amount=2100,
        category="beauty",
        planned_date=date.today(),
    )

    result = service.confirm_expense(
        telegram_user_id=555,
        planned_expense_id=item.id,
        actual_amount=2500,
    )
    summary = tx_service.get_summary(telegram_user_id=555, period="month")

    assert result.planned.status == "confirmed"
    assert result.transaction is not None
    assert result.transaction.amount == "2500.00"
    assert summary.expense_total == "2500.00"


def test_cancel_planned_expense_marks_cancelled_without_transaction(db_session) -> None:
    service = PlannedExpenseService(db_session)
    tx_service = TransactionService(db_session)

    item = service.create_manual(
        telegram_user_id=555,
        title="Маникюр",
        amount=2100,
        category="beauty",
        planned_date=date.today(),
    )

    cancelled = service.cancel_expense(telegram_user_id=555, planned_expense_id=item.id)
    summary = tx_service.get_summary(telegram_user_id=555, period="month")
    future = service.list_future(telegram_user_id=555)

    assert cancelled.status == "cancelled"
    assert summary.expense_total == "0.00"
    assert future == []


def test_cannot_confirm_same_planned_expense_twice(db_session) -> None:
    service = PlannedExpenseService(db_session)

    item = service.create_manual(
        telegram_user_id=555,
        title="Маникюр",
        amount=2100,
        category="beauty",
        planned_date=date.today(),
    )

    service.confirm_expense(telegram_user_id=555, planned_expense_id=item.id)
    second = service.confirm_expense(telegram_user_id=555, planned_expense_id=item.id)

    assert second is None


def test_list_due_today_returns_only_pending_today(db_session) -> None:
    service = PlannedExpenseService(db_session)
    service.create_manual(555, "Маникюр", 2100, "beauty", date.today())
    tomorrow = service.create_manual(555, "Зал", 3000, "health", date.today() + timedelta(days=1))
    confirmed = service.create_manual(555, "Подписка", 799, "subscriptions", date.today())
    service.confirm_expense(555, confirmed.id)

    due = service.list_due_today(date.today())

    assert len(due) == 1
    assert due[0].title == "Маникюр"


def test_list_for_week_returns_next_week_pending_only(db_session) -> None:
    service = PlannedExpenseService(db_session)
    start = date(2030, 4, 15)
    end = date(2030, 4, 21)
    service.create_manual(555, "Маникюр", 2100, "beauty", date(2030, 4, 15))
    service.create_manual(555, "Зал", 3000, "health", date(2030, 4, 19))
    outside = service.create_manual(555, "Аренда", 45000, "housing", date(2030, 4, 25))
    cancelled = service.create_manual(555, "Подписка", 799, "subscriptions", date(2030, 4, 16))
    service.cancel_expense(555, cancelled.id)

    items = service.list_for_week(555, start, end)

    assert [x.title for x in items] == ["Маникюр", "Зал"]


def test_update_planned_date_moves_item(db_session) -> None:
    service = PlannedExpenseService(db_session)
    item = service.create_manual(555, "Маникюр", 2100, "beauty", date(2030, 4, 15))

    updated = service.update_planned_date(555, item.id, date(2030, 4, 20))
    future = service.list_future(555)

    assert updated is not None
    assert updated.planned_date == "2030-04-20"
    assert future[0].planned_date == "2030-04-20"


def test_delete_planned_expense_marks_cancelled(db_session) -> None:
    service = PlannedExpenseService(db_session)
    item = service.create_manual(555, "Маникюр", 2100, "beauty", date(2030, 4, 15))

    deleted = service.delete_planned(555, item.id)

    assert deleted is not None
    assert deleted.status == "cancelled"
    assert service.list_future(555) == []


def test_list_all_includes_overdue_pending_first(db_session) -> None:
    service = PlannedExpenseService(db_session)
    overdue = service.create_manual(555, "Просроченный", 1000, "other", date.today())
    future = service.create_manual(555, "Будущий", 2000, "other", date.today() + timedelta(days=3))

    items = service.list_all(555, today=date.today() + timedelta(days=1))

    assert [x.title for x in items] == ["Просроченный", "Будущий"]
