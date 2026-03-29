"""Tests for AnalyticsService — budgets, alerts, first-week summary, weekly digest."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.category_budget import CategoryBudget  # noqa: F401
from app.models.transaction import Transaction, TransactionSource, TransactionType
from app.models.user import User
from app.models.user_category_mapping import UserCategoryMapping  # noqa: F401
from app.models.voice_log import VoiceLog  # noqa: F401
from app.repositories.category_budget_repository import CategoryBudgetRepository
from app.repositories.user_repository import UserRepository
from app.services.analytics_service import AnalyticsService, _progress_bar, _traffic_light


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def user(db: Session) -> User:
    repo = UserRepository(db)
    u = repo.get_or_create(12345, "Test User")
    db.commit()
    return u


def _add_expense(db: Session, user_id: int, amount: float, category: str, days_ago: int = 0) -> Transaction:
    tx = Transaction(
        telegram_user_id=user_id,
        type=TransactionType.EXPENSE,
        amount=Decimal(str(amount)),
        category=category,
        source=TransactionSource.TEXT,
        raw_input=f"test {amount} {category}",
        confidence=0.95,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )
    db.add(tx)
    db.flush()
    return tx


class TestProgressBar:
    def test_zero_percent(self) -> None:
        bar = _progress_bar(0)
        assert "\u2591" * 10 == bar

    def test_fifty_percent(self) -> None:
        bar = _progress_bar(50)
        assert bar == "\u2588" * 5 + "\u2591" * 5

    def test_hundred_percent(self) -> None:
        bar = _progress_bar(100)
        assert bar == "\u2588" * 10

    def test_over_hundred(self) -> None:
        bar = _progress_bar(150)
        assert bar == "\u2588" * 10  # Capped


class TestTrafficLight:
    def test_green(self) -> None:
        assert "\U0001f7e2" in _traffic_light(50)

    def test_yellow(self) -> None:
        assert "\U0001f7e1" in _traffic_light(80)

    def test_red(self) -> None:
        assert "\U0001f534" in _traffic_light(95)

    def test_exceeded(self) -> None:
        assert "ПРЕВЫШЕН" in _traffic_light(110)


class TestBudgetReport:
    def test_no_budgets(self, db: Session, user: User) -> None:
        analytics = AnalyticsService(db)
        report = analytics.build_budget_report(user)
        assert "не настроены" in report

    def test_with_budgets(self, db: Session, user: User) -> None:
        budget_repo = CategoryBudgetRepository(db)
        budget_repo.upsert(user.telegram_user_id, "food", 15000)
        _add_expense(db, user.telegram_user_id, 10000, "food")
        db.commit()

        analytics = AnalyticsService(db)
        report = analytics.build_budget_report(user)
        assert "Еда" in report
        assert "10,000" in report or "10000" in report


class TestBudgetAlert:
    def test_no_alert_under_budget(self, db: Session, user: User) -> None:
        budget_repo = CategoryBudgetRepository(db)
        budget_repo.upsert(user.telegram_user_id, "food", 15000)
        _add_expense(db, user.telegram_user_id, 5000, "food")
        db.commit()

        analytics = AnalyticsService(db)
        alert = analytics.check_budget_alert(user.telegram_user_id, "food")
        assert alert is None

    def test_alert_over_budget(self, db: Session, user: User) -> None:
        budget_repo = CategoryBudgetRepository(db)
        budget_repo.upsert(user.telegram_user_id, "food", 10000)
        _add_expense(db, user.telegram_user_id, 12000, "food")
        db.commit()

        analytics = AnalyticsService(db)
        alert = analytics.check_budget_alert(user.telegram_user_id, "food")
        assert alert is not None
        assert "ПРЕВЫШЕН" in alert or "превышен" in alert

    def test_no_alert_no_budget(self, db: Session, user: User) -> None:
        _add_expense(db, user.telegram_user_id, 50000, "food")
        db.commit()

        analytics = AnalyticsService(db)
        alert = analytics.check_budget_alert(user.telegram_user_id, "food")
        assert alert is None


class TestFirstWeekSummary:
    def test_not_enough_data(self, db: Session, user: User) -> None:
        _add_expense(db, user.telegram_user_id, 500, "food", days_ago=1)
        db.commit()

        analytics = AnalyticsService(db)
        summary = analytics.build_first_week_summary(user)
        assert summary is None  # Only 1 transaction, need >= 3

    def test_generates_summary(self, db: Session, user: User) -> None:
        _add_expense(db, user.telegram_user_id, 500, "food", days_ago=1)
        _add_expense(db, user.telegram_user_id, 300, "transport", days_ago=2)
        _add_expense(db, user.telegram_user_id, 200, "food", days_ago=3)
        _add_expense(db, user.telegram_user_id, 1500, "entertainment", days_ago=4)
        _add_expense(db, user.telegram_user_id, 400, "food", days_ago=5)
        db.commit()

        analytics = AnalyticsService(db)
        summary = analytics.build_first_week_summary(user)
        assert summary is not None
        assert "первая неделя" in summary
        assert "5 расходов" in summary
        assert "Еда" in summary

    def test_shows_savings_tip(self, db: Session, user: User) -> None:
        # Create enough data with one dominant category
        for i in range(5):
            _add_expense(db, user.telegram_user_id, 1000, "food", days_ago=i + 1)
        _add_expense(db, user.telegram_user_id, 200, "transport", days_ago=1)
        db.commit()

        analytics = AnalyticsService(db)
        summary = analytics.build_first_week_summary(user)
        assert summary is not None
        assert "Сократив" in summary


class TestWeeklyDigest:
    def test_no_transactions(self, db: Session, user: User) -> None:
        analytics = AnalyticsService(db)
        digest = analytics.build_weekly_digest(user)
        assert digest is None

    def test_generates_digest(self, db: Session, user: User) -> None:
        _add_expense(db, user.telegram_user_id, 500, "food", days_ago=0)
        _add_expense(db, user.telegram_user_id, 300, "transport", days_ago=1)
        db.commit()

        analytics = AnalyticsService(db)
        digest = analytics.build_weekly_digest(user)
        assert digest is not None
        assert "Потрачено" in digest
        assert "Записей" in digest


class TestCategoryBudgetRepository:
    def test_upsert_create(self, db: Session) -> None:
        repo = CategoryBudgetRepository(db)
        budget = repo.upsert(12345, "food", 15000)
        db.commit()
        assert budget.category == "food"
        assert float(budget.amount) == 15000.0

    def test_upsert_update(self, db: Session) -> None:
        repo = CategoryBudgetRepository(db)
        repo.upsert(12345, "food", 15000)
        budget = repo.upsert(12345, "food", 20000)
        db.commit()
        assert float(budget.amount) == 20000.0

    def test_remove(self, db: Session) -> None:
        repo = CategoryBudgetRepository(db)
        repo.upsert(12345, "food", 15000)
        db.commit()
        removed = repo.remove(12345, "food")
        db.commit()
        assert removed is True
        assert repo.get(12345, "food") is None

    def test_get_all_for_user(self, db: Session) -> None:
        repo = CategoryBudgetRepository(db)
        repo.upsert(12345, "food", 15000)
        repo.upsert(12345, "transport", 5000)
        db.commit()
        budgets = repo.get_all_for_user(12345)
        assert len(budgets) == 2
