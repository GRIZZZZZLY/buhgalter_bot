from datetime import datetime, time

from sqlalchemy import BigInteger, DateTime, Float, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="Europe/Moscow")
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="RUB")

    # Budget
    budget_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    budget_start_day: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Reminders (stored as "HH:MM" strings, null = disabled)
    reminder_morning: Mapped[str | None] = mapped_column(String(5), nullable=True, default="09:00")
    reminder_evening: Mapped[str | None] = mapped_column(String(5), nullable=True, default="21:00")

    # Streak
    streak_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    streak_last_date: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Activity tracking
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transactions_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transactions_today_date: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Reminder suppression (count of consecutive ignored evening reminders)
    ignored_evening_reminders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
