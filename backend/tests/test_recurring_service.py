"""Tests for RecurringService and RecurringTransactionRepository."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.category_budget import CategoryBudget  # noqa: F401
from app.models.planned_expense import PlannedExpense  # noqa: F401
from app.models.recurring_transaction import RecurringTransaction  # noqa: F401
from app.models.transaction import Transaction  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.user_category_mapping import UserCategoryMapping  # noqa: F401
from app.models.voice_log import VoiceLog  # noqa: F401
from app.repositories.recurring_transaction_repository import RecurringTransactionRepository
from app.services.recurring_service import RecurringService, parse_recurring_args, parse_recurring_schedule_args


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite://", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


USER_ID = 12345


class TestNextRunCalculation:
    def test_monthly_same_month(self) -> None:
        # Today is the 5th, day_value=20 → next run is the 20th of same month
        result = RecurringTransactionRepository._calc_next_run("monthly", 20, date(2026, 3, 5))
        assert result == date(2026, 3, 20)

    def test_monthly_next_month(self) -> None:
        # Today is the 25th, day_value=1 → next run is the 1st of next month
        result = RecurringTransactionRepository._calc_next_run("monthly", 1, date(2026, 3, 25))
        assert result == date(2026, 4, 1)

    def test_monthly_year_boundary(self) -> None:
        result = RecurringTransactionRepository._calc_next_run("monthly", 15, date(2026, 12, 20))
        assert result == date(2027, 1, 15)

    def test_weekly(self) -> None:
        # Today is Monday (weekday=0), day_value=4 (Friday) → next Friday
        monday = date(2026, 3, 16)  # Monday
        result = RecurringTransactionRepository._calc_next_run("weekly", 4, monday)
        assert result == date(2026, 3, 20)  # Friday

    def test_weekly_same_day_advances(self) -> None:
        # Today is Friday, day_value=4 (Friday) → next Friday (7 days ahead)
        friday = date(2026, 3, 20)
        result = RecurringTransactionRepository._calc_next_run("weekly", 4, friday)
        assert result == date(2026, 3, 27)

    def test_daily(self) -> None:
        result = RecurringTransactionRepository._calc_next_run("daily", 0, date(2026, 3, 15))
        assert result == date(2026, 3, 16)

    def test_interval_days(self) -> None:
        result = RecurringTransactionRepository._calc_next_run("interval_days", 30, date(2026, 3, 15))
        assert result == date(2026, 4, 14)


class TestRecurringRepository:
    def test_create_and_list(self, db: Session) -> None:
        repo = RecurringTransactionRepository(db)
        rt = repo.create(USER_ID, "Аренда", 45000, "expense", "housing", "monthly", 1)
        db.commit()

        items = repo.list_active(USER_ID)
        assert len(items) == 1
        assert items[0].title == "Аренда"
        assert float(items[0].amount) == 45000.0

    def test_deactivate(self, db: Session) -> None:
        repo = RecurringTransactionRepository(db)
        rt = repo.create(USER_ID, "Netflix", 799, "expense", "subscriptions", "monthly", 15)
        db.commit()

        ok = repo.deactivate(USER_ID, rt.id)
        db.commit()

        assert ok is True
        assert repo.list_active(USER_ID) == []

    def test_get_due_today(self, db: Session) -> None:
        repo = RecurringTransactionRepository(db)
        rt = repo.create(USER_ID, "Аренда", 45000, "expense", "housing", "monthly", 1)
        # Force next_run_date to today
        rt.next_run_date = date.today().isoformat()
        db.commit()

        due = repo.get_due_today(date.today().isoformat())
        assert len(due) == 1

    def test_get_due_tomorrow(self, db: Session) -> None:
        repo = RecurringTransactionRepository(db)
        rt = repo.create(USER_ID, "Netflix", 799, "expense", "subscriptions", "monthly", 15)
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        rt.next_run_date = tomorrow
        db.commit()

        due = repo.get_due_tomorrow(tomorrow)
        assert len(due) == 1

    def test_advance_monthly(self, db: Session) -> None:
        repo = RecurringTransactionRepository(db)
        rt = repo.create(USER_ID, "Аренда", 45000, "expense", "housing", "monthly", 1)
        rt.next_run_date = "2026-03-01"
        db.commit()

        repo.advance(rt)
        db.commit()

        assert rt.next_run_date == "2026-04-01"
        assert rt.reminder_sent == 0

    def test_update_fields(self, db: Session) -> None:
        repo = RecurringTransactionRepository(db)
        rt = repo.create(USER_ID, "Аренда", 45000, "expense", "housing", "monthly", 1)

        repo.update(rt, amount=47000, category="home", frequency="weekly", day_value=4)
        db.commit()

        assert float(rt.amount) == 47000.0
        assert rt.category == "home"
        assert rt.frequency == "weekly"
        assert rt.day_value == 4

    def test_create_interval_days(self, db: Session) -> None:
        repo = RecurringTransactionRepository(db)
        rt = repo.create(USER_ID, "Маникюр", 2100, "expense", "beauty", "interval_days", 30)
        db.commit()

        assert rt.frequency == "interval_days"
        assert rt.day_value == 30


class TestRecurringService:
    def test_create_and_spawn_planned(self, db: Session) -> None:
        svc = RecurringService(db)
        rt = svc.create(USER_ID, "Аренда", 45000, "expense", "housing", "monthly", 1)

        # Force due today
        rt.next_run_date = date.today().isoformat()
        db.commit()

        svc.spawn_planned_expense(rt)

        # Check planned expense was created, not transaction
        from sqlalchemy import select
        from app.models.planned_expense import PlannedExpense
        planned = list(db.scalars(select(PlannedExpense).where(PlannedExpense.telegram_user_id == USER_ID)).all())
        assert len(planned) == 1
        assert float(planned[0].amount) == 45000.0
        assert planned[0].category == "housing"
        assert planned[0].source.value == "recurring"

        # And no actual transaction yet
        from sqlalchemy import select
        from app.models.transaction import Transaction
        txs = list(db.scalars(select(Transaction).where(Transaction.telegram_user_id == USER_ID)).all())
        assert len(txs) == 0

    def test_spawn_planned_advances_schedule(self, db: Session) -> None:
        svc = RecurringService(db)
        rt = svc.create(USER_ID, "Маникюр", 2100, "expense", "beauty", "interval_days", 30)
        rt.next_run_date = "2026-03-15"
        db.commit()

        svc.spawn_planned_expense(rt)

        assert rt.next_run_date == "2026-04-14"

    def test_update_amount(self, db: Session) -> None:
        svc = RecurringService(db)
        rt = svc.create(USER_ID, "Аренда", 45000, "expense", "housing", "monthly", 1)

        updated = svc.update_amount(USER_ID, rt.id, 47000)

        assert updated is not None
        assert float(updated.amount) == 47000.0

    def test_update_category(self, db: Session) -> None:
        svc = RecurringService(db)
        rt = svc.create(USER_ID, "Аренда", 45000, "expense", "housing", "monthly", 1)

        updated = svc.update_category(USER_ID, rt.id, "home")

        assert updated is not None
        assert updated.category == "home"

    def test_update_schedule(self, db: Session) -> None:
        svc = RecurringService(db)
        rt = svc.create(USER_ID, "Маникюр", 2100, "expense", "beauty", "interval_days", 30)

        updated = svc.update_schedule(USER_ID, rt.id, "interval_days", 45)

        assert updated is not None
        assert updated.frequency == "interval_days"
        assert updated.day_value == 45

    def test_format_list_empty(self, db: Session) -> None:
        svc = RecurringService(db)
        result = svc.format_list([])
        assert "нет" in result

    def test_format_list_with_items(self, db: Session) -> None:
        svc = RecurringService(db)
        rt = svc.create(USER_ID, "Аренда", 45000, "expense", "housing", "monthly", 1)
        result = svc.format_list([rt])
        assert "Аренда" in result
        assert "45,000" in result or "45000" in result


class TestParseRecurringArgs:
    def test_valid_monthly(self) -> None:
        result = parse_recurring_args(["аренда", "45000", "расход", "жильё", "ежемесячно", "1"])
        assert isinstance(result, dict)
        assert result["title"] == "аренда"
        assert result["amount"] == 45000.0
        assert result["transaction_type"] == "expense"
        assert result["frequency"] == "monthly"
        assert result["day_value"] == 1

    def test_valid_income(self) -> None:
        result = parse_recurring_args(["зарплата", "120000", "доход", "зарплата", "ежемесячно", "10"])
        assert isinstance(result, dict)
        assert result["transaction_type"] == "income"

    def test_too_few_args(self) -> None:
        result = parse_recurring_args(["аренда", "45000"])
        assert isinstance(result, str)
        assert "Формат" in result

    def test_invalid_amount(self) -> None:
        result = parse_recurring_args(["аренда", "abc", "расход", "жильё", "ежемесячно", "1"])
        assert isinstance(result, str)
        assert "сумму" in result

    def test_invalid_type(self) -> None:
        result = parse_recurring_args(["аренда", "45000", "неизвестно", "жильё", "ежемесячно", "1"])
        assert isinstance(result, str)
        assert "Тип" in result

    def test_invalid_frequency(self) -> None:
        result = parse_recurring_args(["аренда", "45000", "расход", "жильё", "раз_в_год", "1"])
        assert isinstance(result, str)
        assert "Частота" in result

    def test_day_out_of_range(self) -> None:
        result = parse_recurring_args(["аренда", "45000", "расход", "жильё", "ежемесячно", "31"])
        assert isinstance(result, str)
        assert "28" in result

    def test_default_day_value(self) -> None:
        # No day argument → defaults to 1
        result = parse_recurring_args(["аренда", "45000", "расход", "жильё", "ежемесячно"])
        assert isinstance(result, dict)
        assert result["day_value"] == 1

    def test_interval_days(self) -> None:
        result = parse_recurring_args(["маникюр", "2100", "расход", "красота", "каждые", "30"])
        assert isinstance(result, dict)
        assert result["frequency"] == "interval_days"
        assert result["day_value"] == 30

    def test_human_monthly_phrase(self) -> None:
        result = parse_recurring_args(["аренда", "45000", "расход", "жильё", "каждый", "месяц", "1", "числа"])
        assert isinstance(result, dict)
        assert result["frequency"] == "monthly"
        assert result["day_value"] == 1

    def test_human_weekly_phrase(self) -> None:
        result = parse_recurring_args(["зал", "3000", "расход", "здоровье", "каждую", "неделю", "4"])
        assert isinstance(result, dict)
        assert result["frequency"] == "weekly"
        assert result["day_value"] == 4

    def test_human_interval_days_phrase(self) -> None:
        result = parse_recurring_args(["маникюр", "2100", "расход", "красота", "каждые", "30", "дней"])
        assert isinstance(result, dict)
        assert result["frequency"] == "interval_days"
        assert result["day_value"] == 30


class TestParseRecurringScheduleArgs:
    def test_monthly(self) -> None:
        result = parse_recurring_schedule_args(["ежемесячно", "10"])
        assert isinstance(result, dict)
        assert result["frequency"] == "monthly"
        assert result["day_value"] == 10

    def test_interval_days(self) -> None:
        result = parse_recurring_schedule_args(["каждые", "45"])
        assert isinstance(result, dict)
        assert result["frequency"] == "interval_days"
        assert result["day_value"] == 45

    def test_invalid(self) -> None:
        result = parse_recurring_schedule_args(["раз", "вечно"])
        assert isinstance(result, str)

    def test_human_monthly(self) -> None:
        result = parse_recurring_schedule_args(["каждый", "месяц", "10", "числа"])
        assert isinstance(result, dict)
        assert result["frequency"] == "monthly"
        assert result["day_value"] == 10

    def test_human_interval_days(self) -> None:
        result = parse_recurring_schedule_args(["каждые", "45", "дней"])
        assert isinstance(result, dict)
        assert result["frequency"] == "interval_days"
        assert result["day_value"] == 45
