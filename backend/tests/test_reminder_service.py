"""Tests for ReminderService — morning briefing, evening check-in, streak loss."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.user import User
from app.models.transaction import Transaction  # noqa: F401
from app.models.voice_log import VoiceLog  # noqa: F401
from app.models.user_category_mapping import UserCategoryMapping  # noqa: F401
from app.repositories.user_repository import UserRepository
from app.services.reminder_service import ReminderService


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


class TestMorningBriefing:
    def test_basic_briefing_without_budget(self, db: Session, user: User) -> None:
        service = ReminderService(db)
        message = service.build_morning_briefing(user)

        assert message is not None
        assert "Доброе утро" in message
        assert "Баланс за месяц" in message

    def test_briefing_with_budget(self, db: Session, user: User) -> None:
        user.budget_amount = 50000.0
        db.commit()

        service = ReminderService(db)
        message = service.build_morning_briefing(user)

        assert message is not None
        assert "На сегодня" in message or "Бюджет исчерпан" in message
        assert "бюджета" in message

    def test_briefing_shows_streak(self, db: Session, user: User) -> None:
        user.streak_days = 5
        user.streak_last_date = date.today().isoformat()
        db.commit()

        service = ReminderService(db)
        message = service.build_morning_briefing(user)

        assert message is not None
        assert "5 дней" in message


class TestEveningCheckin:
    def test_basic_checkin_no_transactions(self, db: Session, user: User) -> None:
        service = ReminderService(db)
        message, categories = service.build_evening_checkin(user)

        assert message is not None
        assert "ничего не записано" in message
        assert len(categories) == 3  # defaults

    def test_smart_silence_when_enough_transactions(self, db: Session, user: User) -> None:
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(user.timezone)
        today_str = datetime.now(tz).date().isoformat()

        user.transactions_today = 5
        user.transactions_today_date = today_str
        db.commit()

        service = ReminderService(db)
        message, categories = service.build_evening_checkin(user)

        assert message is None  # Smart silence
        assert categories == []

    def test_checkin_with_some_transactions(self, db: Session, user: User) -> None:
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(user.timezone)
        today_str = datetime.now(tz).date().isoformat()

        user.transactions_today = 2
        user.transactions_today_date = today_str
        db.commit()

        service = ReminderService(db)
        message, categories = service.build_evening_checkin(user)

        assert message is not None
        assert "2 расход" in message


class TestStreakLoss:
    def test_no_notification_for_short_streak(self, db: Session, user: User) -> None:
        service = ReminderService(db)
        message = service.build_streak_loss_message(user, previous_streak=2)
        assert message is None

    def test_notification_for_long_streak(self, db: Session, user: User) -> None:
        service = ReminderService(db)
        message = service.build_streak_loss_message(user, previous_streak=10)

        assert message is not None
        assert "10 дней" in message
        assert "прервалась" in message


class TestBudgetPeriodCalculation:
    def test_days_left_mid_month(self) -> None:
        # Budget starts on 1st, today is 15th March
        days = ReminderService._days_left_in_budget_period(date(2026, 3, 15), 1)
        assert days == 17  # March 15 -> April 1 = 17 days

    def test_days_left_custom_start(self) -> None:
        # Budget starts on 10th, today is 15th March -> next period starts April 10
        days = ReminderService._days_left_in_budget_period(date(2026, 3, 15), 10)
        assert days == 26  # March 15 -> April 10 = 26 days

    def test_total_days_standard_month(self) -> None:
        total = ReminderService._total_days_in_budget_period(date(2026, 3, 15), 1)
        assert total == 31  # March 1 -> April 1 = 31 days
