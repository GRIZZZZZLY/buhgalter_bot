"""Tests for UserRepository — user creation, streak tracking, settings."""

from datetime import date, timedelta

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


class TestGetOrCreate:
    def test_creates_new_user(self, db: Session) -> None:
        repo = UserRepository(db)
        user = repo.get_or_create(12345, "Test User")
        db.commit()

        assert user.telegram_user_id == 12345
        assert user.display_name == "Test User"
        assert user.timezone == "Europe/Moscow"
        assert user.streak_days == 0
        assert user.reminder_morning == "09:00"
        assert user.reminder_evening == "21:00"

    def test_returns_existing_user(self, db: Session) -> None:
        repo = UserRepository(db)
        user1 = repo.get_or_create(12345, "Test User")
        db.commit()
        user2 = repo.get_or_create(12345, "Test User")
        db.commit()

        assert user1.id == user2.id

    def test_updates_display_name(self, db: Session) -> None:
        repo = UserRepository(db)
        repo.get_or_create(12345, "Old Name")
        db.commit()
        user = repo.get_or_create(12345, "New Name")
        db.commit()

        assert user.display_name == "New Name"


class TestStreak:
    def test_first_activity_starts_streak(self, db: Session) -> None:
        repo = UserRepository(db)
        user = repo.get_or_create(12345)
        db.commit()

        incremented = repo.update_streak(user, "2026-03-15")
        db.commit()

        assert incremented is True
        assert user.streak_days == 1
        assert user.streak_last_date == "2026-03-15"

    def test_consecutive_day_increments(self, db: Session) -> None:
        repo = UserRepository(db)
        user = repo.get_or_create(12345)
        db.commit()

        repo.update_streak(user, "2026-03-15")
        repo.update_streak(user, "2026-03-16")
        db.commit()

        assert user.streak_days == 2

    def test_same_day_does_not_increment(self, db: Session) -> None:
        repo = UserRepository(db)
        user = repo.get_or_create(12345)
        db.commit()

        repo.update_streak(user, "2026-03-15")
        incremented = repo.update_streak(user, "2026-03-15")
        db.commit()

        assert incremented is False
        assert user.streak_days == 1

    def test_gap_resets_streak(self, db: Session) -> None:
        repo = UserRepository(db)
        user = repo.get_or_create(12345)
        db.commit()

        repo.update_streak(user, "2026-03-15")
        repo.update_streak(user, "2026-03-16")
        repo.update_streak(user, "2026-03-17")
        # Skip a day
        repo.update_streak(user, "2026-03-19")
        db.commit()

        assert user.streak_days == 1
        assert user.streak_last_date == "2026-03-19"


class TestTransactionsToday:
    def test_increments_same_day(self, db: Session) -> None:
        repo = UserRepository(db)
        user = repo.get_or_create(12345)
        db.commit()

        repo.increment_transactions_today(user, "2026-03-15")
        repo.increment_transactions_today(user, "2026-03-15")
        repo.increment_transactions_today(user, "2026-03-15")
        db.commit()

        assert user.transactions_today == 3

    def test_resets_on_new_day(self, db: Session) -> None:
        repo = UserRepository(db)
        user = repo.get_or_create(12345)
        db.commit()

        repo.increment_transactions_today(user, "2026-03-15")
        repo.increment_transactions_today(user, "2026-03-15")
        repo.increment_transactions_today(user, "2026-03-16")
        db.commit()

        assert user.transactions_today == 1
        assert user.transactions_today_date == "2026-03-16"


class TestSettings:
    def test_update_budget(self, db: Session) -> None:
        repo = UserRepository(db)
        user = repo.get_or_create(12345)
        db.commit()

        repo.update_settings(user, budget_amount=50000.0, budget_start_day=10)
        db.commit()

        assert float(user.budget_amount) == 50000.0
        assert user.budget_start_day == 10

    def test_disable_reminders(self, db: Session) -> None:
        repo = UserRepository(db)
        user = repo.get_or_create(12345)
        db.commit()

        repo.update_settings(user, reminder_morning=None, reminder_evening=None)
        db.commit()

        assert user.reminder_morning is None
        assert user.reminder_evening is None
