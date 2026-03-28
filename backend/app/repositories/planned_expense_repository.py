from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.planned_expense import PlannedExpense, PlannedExpenseSource, PlannedExpenseStatus


class PlannedExpenseRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        telegram_user_id: int,
        title: str,
        amount: float | Decimal,
        category: str,
        planned_date: date,
        source: str = "manual",
        recurring_transaction_id: int | None = None,
        reminder_time: str | None = None,
    ) -> PlannedExpense:
        item = PlannedExpense(
            telegram_user_id=telegram_user_id,
            title=title,
            amount=Decimal(str(amount)),
            category=category,
            planned_date=planned_date,
            source=PlannedExpenseSource(source),
            recurring_transaction_id=recurring_transaction_id,
            status=PlannedExpenseStatus.PENDING,
            reminder_time=reminder_time,
        )
        self.db.add(item)
        self.db.flush()
        self.db.refresh(item)
        return item

    def get(self, telegram_user_id: int, planned_expense_id: int) -> PlannedExpense | None:
        stmt = select(PlannedExpense).where(
            PlannedExpense.telegram_user_id == telegram_user_id,
            PlannedExpense.id == planned_expense_id,
        )
        return self.db.scalar(stmt)

    def list_future_for_user(self, telegram_user_id: int, today: date | None = None) -> list[PlannedExpense]:
        today = today or date.today()
        stmt = (
            select(PlannedExpense)
            .where(
                PlannedExpense.telegram_user_id == telegram_user_id,
                PlannedExpense.status == PlannedExpenseStatus.PENDING,
                PlannedExpense.planned_date >= today,
            )
            .order_by(PlannedExpense.planned_date.asc(), PlannedExpense.id.asc())
        )
        return list(self.db.scalars(stmt).all())

    def list_due_today(self, today: date, telegram_user_id: int | None = None) -> list[PlannedExpense]:
        stmt = (
            select(PlannedExpense)
            .where(
                PlannedExpense.status == PlannedExpenseStatus.PENDING,
                PlannedExpense.planned_date == today,
            )
            .order_by(PlannedExpense.id.asc())
        )
        if telegram_user_id is not None:
            stmt = stmt.where(PlannedExpense.telegram_user_id == telegram_user_id)
        return list(self.db.scalars(stmt).all())

    def list_for_week(self, telegram_user_id: int, start: date, end: date) -> list[PlannedExpense]:
        stmt = (
            select(PlannedExpense)
            .where(
                PlannedExpense.telegram_user_id == telegram_user_id,
                PlannedExpense.status == PlannedExpenseStatus.PENDING,
                PlannedExpense.planned_date >= start,
                PlannedExpense.planned_date <= end,
            )
            .order_by(PlannedExpense.planned_date.asc(), PlannedExpense.id.asc())
        )
        return list(self.db.scalars(stmt).all())

    def list_all_for_user(self, telegram_user_id: int) -> list[PlannedExpense]:
        stmt = (
            select(PlannedExpense)
            .where(
                PlannedExpense.telegram_user_id == telegram_user_id,
                PlannedExpense.status == PlannedExpenseStatus.PENDING,
            )
            .order_by(PlannedExpense.planned_date.asc(), PlannedExpense.id.asc())
        )
        return list(self.db.scalars(stmt).all())

    def update_planned_date(self, item: PlannedExpense, planned_date: date) -> PlannedExpense:
        item.planned_date = planned_date
        self.db.add(item)
        self.db.flush()
        self.db.refresh(item)
        return item

    def mark_confirmed(self, item: PlannedExpense) -> PlannedExpense:
        item.status = PlannedExpenseStatus.CONFIRMED
        self.db.add(item)
        self.db.flush()
        self.db.refresh(item)
        return item

    def mark_cancelled(self, item: PlannedExpense) -> PlannedExpense:
        item.status = PlannedExpenseStatus.CANCELLED
        self.db.add(item)
        self.db.flush()
        self.db.refresh(item)
        return item
