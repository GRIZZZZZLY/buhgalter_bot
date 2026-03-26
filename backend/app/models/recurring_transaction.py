from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RecurringTransaction(Base):
    """A user-defined recurring transaction that fires automatically on a schedule."""

    __tablename__ = "recurring_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)

    title: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    # "income" | "expense"
    transaction_type: Mapped[str] = mapped_column(String(10), nullable=False, default="expense")
    category: Mapped[str] = mapped_column(String(50), nullable=False)

    # "monthly" | "weekly" | "daily"
    frequency: Mapped[str] = mapped_column(String(10), nullable=False, default="monthly")
    # For monthly: day of month (1-28). For weekly: weekday (0=Mon … 6=Sun).
    day_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ISO date string of the next scheduled run, e.g. "2026-04-01"
    next_run_date: Mapped[str] = mapped_column(String(10), nullable=False)

    # Whether a reminder was sent the day before (reset after firing)
    reminder_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
