from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from app.models.transaction import Transaction, TransactionSource, TransactionType


class TransactionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, payload: dict) -> Transaction:
        kwargs: dict = dict(
            telegram_user_id=payload["telegram_user_id"],
            type=TransactionType(payload["type"]),
            amount=payload["amount"],
            category=payload["category"],
            description=payload.get("description"),
            source=TransactionSource(payload["source"]),
            raw_input=payload["raw_input"],
            confidence=payload["confidence"],
        )
        # Allow overriding created_at for past-date entries
        if payload.get("created_at") is not None:
            kwargs["created_at"] = payload["created_at"]
        transaction = Transaction(**kwargs)
        self.db.add(transaction)
        self.db.commit()
        self.db.refresh(transaction)
        return transaction

    def list_for_user(self, telegram_user_id: int, limit: int, offset: int, period: str) -> list[Transaction]:
        stmt = (
            select(Transaction)
            .where(Transaction.telegram_user_id == telegram_user_id)
            .order_by(Transaction.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        period_filter = self._build_period_filter(period)
        if period_filter is not None:
            stmt = stmt.where(period_filter)
        return list(self.db.scalars(stmt).all())

    def get_summary(self, telegram_user_id: int, period: str) -> dict:
        income_case = case((Transaction.type == TransactionType.INCOME, Transaction.amount), else_=0)
        expense_case = case((Transaction.type == TransactionType.EXPENSE, Transaction.amount), else_=0)

        stmt = select(func.coalesce(func.sum(income_case), 0), func.coalesce(func.sum(expense_case), 0)).where(
            Transaction.telegram_user_id == telegram_user_id
        )
        period_filter = self._build_period_filter(period)
        if period_filter is not None:
            stmt = stmt.where(period_filter)
        income_total, expense_total = self.db.execute(stmt).one()

        top_stmt = (
            select(Transaction.category, func.sum(Transaction.amount).label("amount"))
            .where(
                Transaction.telegram_user_id == telegram_user_id,
                Transaction.type == TransactionType.EXPENSE,
            )
            .group_by(Transaction.category)
            .order_by(func.sum(Transaction.amount).desc(), Transaction.category.asc())
            .limit(3)
        )
        if period_filter is not None:
            top_stmt = top_stmt.where(period_filter)
        top_rows = self.db.execute(top_stmt).all()

        income_total = Decimal(income_total)
        expense_total = Decimal(expense_total)
        return {
            "income_total": income_total,
            "expense_total": expense_total,
            "balance": income_total - expense_total,
            "top_expense_categories": [
                {"category": row.category, "amount": Decimal(row.amount)} for row in top_rows
            ],
        }

    def update(self, telegram_user_id: int, transaction_id: UUID, payload: dict) -> Transaction | None:
        transaction = self.get(telegram_user_id, transaction_id)
        if transaction is None:
            return None

        if payload.get("type") is not None:
            transaction.type = TransactionType(payload["type"])
        if payload.get("amount") is not None:
            transaction.amount = Decimal(payload["amount"])
        if payload.get("category") is not None:
            transaction.category = payload["category"]
        if "description" in payload:
            transaction.description = payload.get("description")

        self.db.add(transaction)
        self.db.commit()
        self.db.refresh(transaction)
        return transaction

    def get(self, telegram_user_id: int, transaction_id: UUID) -> Transaction | None:
        stmt = select(Transaction).where(
            Transaction.telegram_user_id == telegram_user_id,
            Transaction.id == transaction_id,
        )
        return self.db.scalar(stmt)

    def delete(self, telegram_user_id: int, transaction_id: UUID) -> bool:
        stmt = delete(Transaction).where(
            Transaction.telegram_user_id == telegram_user_id,
            Transaction.id == transaction_id,
        )
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount > 0

    def delete_all_for_user(self, telegram_user_id: int) -> int:
        stmt = delete(Transaction).where(Transaction.telegram_user_id == telegram_user_id)
        result = self.db.execute(stmt)
        self.db.commit()
        return int(result.rowcount or 0)

    def sum_expenses_by_category(
        self, telegram_user_id: int, start: datetime, end: datetime
    ) -> dict[str, Decimal]:
        """Sum expense amounts grouped by category between start (inclusive) and end (exclusive)."""
        stmt = (
            select(Transaction.category, func.sum(Transaction.amount).label("total"))
            .where(
                Transaction.telegram_user_id == telegram_user_id,
                Transaction.type == TransactionType.EXPENSE,
                Transaction.created_at >= start,
                Transaction.created_at < end,
            )
            .group_by(Transaction.category)
        )
        rows = self.db.execute(stmt).all()
        return {row.category: Decimal(str(row.total)) for row in rows}

    def sum_expenses_per_day(
        self, telegram_user_id: int, start: datetime, end: datetime
    ) -> dict[date, Decimal]:
        """Sum expense amounts grouped by UTC date between start (inclusive) and end (exclusive)."""
        stmt = (
            select(
                func.date(Transaction.created_at).label("day"),
                func.sum(Transaction.amount).label("total"),
            )
            .where(
                Transaction.telegram_user_id == telegram_user_id,
                Transaction.type == TransactionType.EXPENSE,
                Transaction.created_at >= start,
                Transaction.created_at < end,
            )
            .group_by(func.date(Transaction.created_at))
        )
        rows = self.db.execute(stmt).all()
        return {date.fromisoformat(row.day): Decimal(str(row.total)) for row in rows}

    def monthly_summary(self, telegram_user_id: int, months: int = 3) -> list[dict]:
        """Return per-month income/expense totals and category breakdowns for the last N months.

        Uses Python-side aggregation for database portability (SQLite dev / PostgreSQL prod).
        """
        now = datetime.now()
        start_month = now.month - months + 1
        start_year = now.year
        while start_month <= 0:
            start_month += 12
            start_year -= 1
        start = datetime(start_year, start_month, 1)

        stmt = (
            select(Transaction)
            .where(
                Transaction.telegram_user_id == telegram_user_id,
                Transaction.created_at >= start,
            )
            .order_by(Transaction.created_at.desc())
        )
        transactions = self.db.scalars(stmt).all()

        from collections import defaultdict
        months_data: dict[str, dict] = defaultdict(
            lambda: {"income": Decimal(0), "expenses": Decimal(0), "by_category": defaultdict(Decimal)}
        )

        for tx in transactions:
            ym = tx.created_at.strftime("%Y-%m")
            entry = months_data[ym]
            amount = Decimal(str(tx.amount))
            if tx.type == TransactionType.INCOME:
                entry["income"] += amount
            else:
                entry["expenses"] += amount
                entry["by_category"][tx.category] += amount

        result = []
        for ym in sorted(months_data.keys(), reverse=True):
            d = months_data[ym]
            by_cat = dict(sorted(d["by_category"].items(), key=lambda kv: kv[1], reverse=True)[:10])
            result.append({
                "year_month": ym,
                "income": d["income"],
                "expenses": d["expenses"],
                "by_category": by_cat,
            })
        return result

    @staticmethod
    def _build_period_filter(period: str):
        if period == "all":
            return None

        now = datetime.now(timezone.utc)
        if period == "today":
            start = datetime.combine(date.today(), time.min, tzinfo=timezone.utc)
        elif period == "week":
            monday = (now - timedelta(days=now.weekday())).date()
            start = datetime.combine(monday, time.min, tzinfo=timezone.utc)
        else:
            month_start = now.date().replace(day=1)
            start = datetime.combine(month_start, time.min, tzinfo=timezone.utc)
        return Transaction.created_at >= start
