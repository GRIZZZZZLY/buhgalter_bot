from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        stmt = select(User).where(User.telegram_user_id == telegram_user_id)
        return self.db.scalar(stmt)

    def get_or_create(self, telegram_user_id: int, display_name: str | None = None) -> User:
        """Return existing user or create a new one. Always updates last_active_at."""
        user = self.get_by_telegram_id(telegram_user_id)
        if user is None:
            user = User(
                telegram_user_id=telegram_user_id,
                display_name=display_name,
            )
            self.db.add(user)
            self.db.flush()
        else:
            if display_name and user.display_name != display_name:
                user.display_name = display_name
        user.last_active_at = datetime.now(timezone.utc)
        self.db.flush()
        return user

    def update_streak(self, user: User, today_str: str) -> bool:
        """Update streak for today. Returns True if streak was incremented (first activity today)."""
        if user.streak_last_date == today_str:
            return False

        from datetime import date, timedelta
        today = date.fromisoformat(today_str)

        if user.streak_last_date:
            last_date = date.fromisoformat(user.streak_last_date)
            if today - last_date == timedelta(days=1):
                user.streak_days += 1
            elif today - last_date > timedelta(days=1):
                user.streak_days = 1
        else:
            user.streak_days = 1

        user.streak_last_date = today_str
        self.db.flush()
        return True

    def increment_transactions_today(self, user: User, today_str: str) -> None:
        """Increment the daily transaction counter. Resets if date changed."""
        if user.transactions_today_date != today_str:
            user.transactions_today = 1
            user.transactions_today_date = today_str
        else:
            user.transactions_today += 1
        self.db.flush()

    def get_all_with_morning_reminder(self) -> list[User]:
        """Return all users who have morning reminders enabled."""
        stmt = select(User).where(User.reminder_morning.isnot(None))
        return list(self.db.scalars(stmt).all())

    def get_all_with_evening_reminder(self) -> list[User]:
        """Return all users who have evening reminders enabled."""
        stmt = select(User).where(User.reminder_evening.isnot(None))
        return list(self.db.scalars(stmt).all())

    def update_settings(self, user: User, **kwargs) -> User:
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        self.db.flush()
        return user

    def reset_ignored_evening_reminders(self, user: User) -> None:
        user.ignored_evening_reminders = 0
        self.db.flush()

    def increment_ignored_evening_reminders(self, user: User) -> None:
        user.ignored_evening_reminders += 1
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()
