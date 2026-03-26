from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import BigInteger, Date, DateTime, Enum as SqlEnum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlannedExpenseSource(str, Enum):
    MANUAL = "manual"
    RECURRING = "recurring"


class PlannedExpenseStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class PlannedExpense(Base):
    __tablename__ = "planned_expenses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    planned_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    source: Mapped[PlannedExpenseSource] = mapped_column(
        SqlEnum(PlannedExpenseSource, name="planned_expense_source", native_enum=False),
        nullable=False,
        default=PlannedExpenseSource.MANUAL,
    )
    recurring_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("recurring_transactions.id"), nullable=True
    )
    status: Mapped[PlannedExpenseStatus] = mapped_column(
        SqlEnum(PlannedExpenseStatus, name="planned_expense_status", native_enum=False),
        nullable=False,
        default=PlannedExpenseStatus.PENDING,
    )
    reminder_sent_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
