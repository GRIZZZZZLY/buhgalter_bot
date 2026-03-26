from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.recurring_transaction import RecurringTransaction


class RecurringTransactionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        telegram_user_id: int,
        title: str,
        amount: float,
        transaction_type: str,
        category: str,
        frequency: str,
        day_value: int,
    ) -> RecurringTransaction:
        next_run = self._calc_next_run(frequency, day_value, date.today())
        rt = RecurringTransaction(
            telegram_user_id=telegram_user_id,
            title=title,
            amount=amount,
            transaction_type=transaction_type,
            category=category,
            frequency=frequency,
            day_value=day_value,
            next_run_date=next_run.isoformat(),
        )
        self.db.add(rt)
        self.db.flush()
        return rt

    def list_active(self, telegram_user_id: int) -> list[RecurringTransaction]:
        stmt = (
            select(RecurringTransaction)
            .where(
                RecurringTransaction.telegram_user_id == telegram_user_id,
                RecurringTransaction.is_active == 1,
            )
            .order_by(RecurringTransaction.next_run_date)
        )
        return list(self.db.scalars(stmt).all())

    def get(self, telegram_user_id: int, rt_id: int) -> RecurringTransaction | None:
        stmt = select(RecurringTransaction).where(
            RecurringTransaction.id == rt_id,
            RecurringTransaction.telegram_user_id == telegram_user_id,
        )
        return self.db.scalar(stmt)

    def deactivate(self, telegram_user_id: int, rt_id: int) -> bool:
        rt = self.get(telegram_user_id, rt_id)
        if rt is None:
            return False
        rt.is_active = 0
        self.db.flush()
        return True

    def update(
        self,
        rt: RecurringTransaction,
        *,
        amount: float | None = None,
        category: str | None = None,
        frequency: str | None = None,
        day_value: int | None = None,
    ) -> RecurringTransaction:
        if amount is not None:
            rt.amount = amount
        if category is not None:
            rt.category = category
        if frequency is not None:
            rt.frequency = frequency
        if day_value is not None:
            rt.day_value = day_value
        self.db.flush()
        return rt

    def get_due_today(self, today_str: str) -> list[RecurringTransaction]:
        """Return all active recurring transactions whose next_run_date <= today."""
        stmt = select(RecurringTransaction).where(
            RecurringTransaction.is_active == 1,
            RecurringTransaction.next_run_date <= today_str,
        )
        return list(self.db.scalars(stmt).all())

    def get_due_tomorrow(self, tomorrow_str: str) -> list[RecurringTransaction]:
        """Return active recurring transactions due tomorrow (for advance reminder)."""
        stmt = select(RecurringTransaction).where(
            RecurringTransaction.is_active == 1,
            RecurringTransaction.next_run_date == tomorrow_str,
            RecurringTransaction.reminder_sent == 0,
        )
        return list(self.db.scalars(stmt).all())

    def advance(self, rt: RecurringTransaction) -> None:
        """Move next_run_date to the next occurrence and reset reminder_sent."""
        current = date.fromisoformat(rt.next_run_date)
        rt.next_run_date = self._calc_next_run(rt.frequency, rt.day_value, current).isoformat()
        rt.reminder_sent = 0
        self.db.flush()

    def mark_reminder_sent(self, rt: RecurringTransaction) -> None:
        rt.reminder_sent = 1
        self.db.flush()

    @staticmethod
    def _calc_next_run(frequency: str, day_value: int, from_date: date) -> date:
        """Calculate the next run date from a given base date."""
        if frequency == "daily":
            return from_date + timedelta(days=1)

        if frequency == "interval_days":
            interval = max(day_value, 1)
            return from_date + timedelta(days=interval)

        if frequency == "weekly":
            # day_value: 0=Mon … 6=Sun
            days_ahead = (day_value - from_date.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return from_date + timedelta(days=days_ahead)

        # monthly (default)
        day = min(day_value, 28)
        # Try same month first
        if from_date.day < day:
            try:
                return from_date.replace(day=day)
            except ValueError:
                pass
        # Next month
        if from_date.month == 12:
            next_month = from_date.replace(year=from_date.year + 1, month=1, day=day)
        else:
            next_month = from_date.replace(month=from_date.month + 1, day=day)
        return next_month
