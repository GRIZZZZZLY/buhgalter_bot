"""Service for budget tracking, alerts, first-week summary, and weekly digest."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.category_budget import CategoryBudget
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.repositories.category_budget_repository import CategoryBudgetRepository
from app.repositories.transaction_repository import TransactionRepository
from app.telegram.formatter import TreasuryFormatter

logger = logging.getLogger("finance_bot.analytics")
formatter = TreasuryFormatter()

PROGRESS_BAR_LENGTH = 10


def _progress_bar(pct: float) -> str:
    """Build a text progress bar like ████████░░"""
    filled = min(int(pct / 100 * PROGRESS_BAR_LENGTH), PROGRESS_BAR_LENGTH)
    empty = PROGRESS_BAR_LENGTH - filled
    return "\u2588" * filled + "\u2591" * empty


def _traffic_light(pct: float) -> str:
    if pct > 100:
        return "\u26a0\ufe0f ПРЕВЫШЕН"
    if pct > 90:
        return "\U0001f534"  # 🔴
    if pct > 70:
        return "\U0001f7e1"  # 🟡
    return "\U0001f7e2"  # 🟢


class AnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.budget_repo = CategoryBudgetRepository(db)
        self.tx_repo = TransactionRepository(db)

    # ------------------------------------------------------------------
    # Budget status report (/budget command)
    # ------------------------------------------------------------------
    def build_budget_report(self, user: User) -> str:
        """Build a full budget status report for the user."""
        budgets = self.budget_repo.get_all_for_user(user.telegram_user_id)
        if not budgets:
            return (
                "\U0001f4ca У тебя пока нет бюджетов по категориям.\n\n"
                "Установи бюджет:\n"
                "/budget еда 15000\n"
                "/budget транспорт 5000\n\n"
                "Или удали:\n"
                "/budget еда 0"
            )

        summary = self.tx_repo.get_summary(user.telegram_user_id, period="month")

        # Build per-category spending map
        category_spending = self._get_category_spending_this_month(user.telegram_user_id)

        lines = ["\U0001f4ca Бюджеты на текущий месяц:\n"]
        for budget in budgets:
            cat_label = formatter.category_label(budget.category)
            spent = float(category_spending.get(budget.category, 0))
            limit = float(budget.amount)
            pct = (spent / limit * 100) if limit > 0 else 0
            bar = _progress_bar(pct)
            light = _traffic_light(pct)

            lines.append(
                f"{cat_label}: {bar} {spent:,.0f}/{limit:,.0f} \u20bd ({pct:.0f}%) {light}"
            )

        # Overall budget
        if user.budget_amount:
            total_expense = float(summary["expense_total"])
            total_budget = float(user.budget_amount)
            total_pct = (total_expense / total_budget * 100) if total_budget > 0 else 0
            lines.append(
                f"\n\U0001f4b0 Общий: {_progress_bar(total_pct)} "
                f"{total_expense:,.0f}/{total_budget:,.0f} \u20bd ({total_pct:.0f}%) {_traffic_light(total_pct)}"
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Budget alert after transaction
    # ------------------------------------------------------------------
    def check_budget_alert(self, telegram_user_id: int, category: str) -> str | None:
        """Check if a category budget was exceeded after a new transaction.
        Returns alert message or None."""
        budget = self.budget_repo.get(telegram_user_id, category)
        if budget is None:
            return None

        category_spending = self._get_category_spending_this_month(telegram_user_id)
        spent = float(category_spending.get(category, 0))
        limit = float(budget.amount)

        if spent <= limit:
            return None

        overspend = spent - limit
        pct = (spent / limit * 100) if limit > 0 else 0
        cat_label = formatter.category_label(category)
        return (
            f"\u26a0\ufe0f Бюджет \u00ab{cat_label}\u00bb превышен: "
            f"{spent:,.0f}/{limit:,.0f} \u20bd (+{pct - 100:.0f}%)"
        )

    # ------------------------------------------------------------------
    # First week summary ("aha moment")
    # ------------------------------------------------------------------
    def build_first_week_summary(self, user: User) -> str | None:
        """Build the first-week insights message. Returns None if not enough data."""
        # Get all transactions for this user in the last 7 days
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        stmt = (
            select(Transaction)
            .where(
                Transaction.telegram_user_id == user.telegram_user_id,
                Transaction.type == TransactionType.EXPENSE,
                Transaction.created_at >= seven_days_ago,
            )
            .order_by(Transaction.created_at.desc())
        )
        transactions = list(self.db.scalars(stmt).all())

        if len(transactions) < 3:
            return None  # Not enough data for meaningful insights

        total_expense = sum(float(tx.amount) for tx in transactions)
        tx_count = len(transactions)

        # Category breakdown
        category_totals: dict[str, float] = {}
        category_counts: dict[str, int] = {}
        for tx in transactions:
            cat = tx.category
            category_totals[cat] = category_totals.get(cat, 0) + float(tx.amount)
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Sort by amount
        sorted_cats = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)

        lines = [
            "\U0001f4ca Ваша первая неделя с ботом!\n",
            f"За 7 дней: {tx_count} расходов на {total_expense:,.0f} \u20bd\n",
            "\U0001f50d Находки:",
        ]

        for cat_slug, cat_total in sorted_cats[:3]:
            cat_label = formatter.category_label(cat_slug)
            pct = (cat_total / total_expense * 100) if total_expense > 0 else 0
            count = category_counts[cat_slug]
            avg = cat_total / count if count > 0 else 0

            # Monthly projection
            monthly_projection = cat_total / 7 * 30

            lines.append(
                f"\u2022 {cat_label}: {cat_total:,.0f} \u20bd ({pct:.0f}%) "
                f"\u2014 {count} раз, средний чек {avg:,.0f} \u20bd"
            )

            if pct >= 15:
                yearly = monthly_projection * 12
                lines.append(
                    f"  \u2192 это ~{monthly_projection:,.0f} \u20bd/мес "
                    f"или ~{yearly:,.0f} \u20bd/год"
                )

        # Biggest single expense
        biggest = max(transactions, key=lambda tx: float(tx.amount))
        biggest_label = formatter.category_label(biggest.category)
        lines.append(
            f"\n\U0001f4b8 Самый большой расход: {float(biggest.amount):,.0f} \u20bd \u2014 {biggest_label}"
        )

        # Savings tip
        if sorted_cats:
            top_cat_slug, top_cat_total = sorted_cats[0]
            top_label = formatter.category_label(top_cat_slug)
            savings_30pct = top_cat_total * 0.3 / 7 * 365
            lines.append(
                f"\n\U0001f4a1 Сократив {top_label} на 30%, за год сэкономишь ~{savings_30pct:,.0f} \u20bd"
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Weekly digest (Sunday evening)
    # ------------------------------------------------------------------
    def build_weekly_digest(self, user: User) -> str | None:
        """Build the weekly spending digest."""
        try:
            tz = ZoneInfo(user.timezone)
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now = datetime.now(tz)

        # This week: Monday to now
        this_monday = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        # Last week
        last_monday = this_monday - timedelta(days=7)
        last_sunday = this_monday

        this_week_data = self._get_period_stats(
            user.telegram_user_id, this_monday, now
        )
        last_week_data = self._get_period_stats(
            user.telegram_user_id, last_monday, last_sunday
        )

        if this_week_data["tx_count"] == 0:
            return None

        lines = [
            f"\U0001f4cb Неделя {this_monday.strftime('%d.%m')}\u2013{now.strftime('%d.%m')}\n",
        ]

        # Total spent comparison
        this_expense = this_week_data["expense_total"]
        last_expense = last_week_data["expense_total"]

        if last_expense > 0:
            change_pct = ((this_expense - last_expense) / last_expense) * 100
            arrow = "\u2193" if change_pct < 0 else "\u2191"
            lines.append(
                f"\U0001f4b8 Потрачено: {this_expense:,.0f} \u20bd "
                f"(прошлая: {last_expense:,.0f} \u20bd, {arrow}{abs(change_pct):.0f}%)"
            )
        else:
            lines.append(f"\U0001f4b8 Потрачено: {this_expense:,.0f} \u20bd")

        # Income
        this_income = this_week_data["income_total"]
        if this_income > 0:
            lines.append(f"\U0001f4b0 Доход: +{this_income:,.0f} \u20bd")

        # Transaction count
        lines.append(f"\U0001f4dd Записей: {this_week_data['tx_count']}")

        # Category changes
        this_cats = this_week_data["category_totals"]
        last_cats = last_week_data["category_totals"]

        # Find biggest growth and biggest savings
        changes: list[tuple[str, float]] = []
        for cat, amount in this_cats.items():
            last_amount = last_cats.get(cat, 0)
            if last_amount > 0:
                change = ((amount - last_amount) / last_amount) * 100
                changes.append((cat, change))

        if changes:
            changes.sort(key=lambda x: x[1])
            # Best savings
            if changes[0][1] < -10:
                cat_label = formatter.category_label(changes[0][0])
                lines.append(f"\U0001f3c6 Экономия: {cat_label} {changes[0][1]:+.0f}%")
            # Biggest growth
            if changes[-1][1] > 10:
                cat_label = formatter.category_label(changes[-1][0])
                lines.append(f"\u26a0\ufe0f Рост: {cat_label} {changes[-1][1]:+.0f}%")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_category_spending_this_month(self, telegram_user_id: int) -> dict[str, Decimal]:
        """Get spending per category for the current month."""
        now = datetime.now(timezone.utc)
        month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

        stmt = (
            select(Transaction.category, func.sum(Transaction.amount))
            .where(
                Transaction.telegram_user_id == telegram_user_id,
                Transaction.type == TransactionType.EXPENSE,
                Transaction.created_at >= month_start,
            )
            .group_by(Transaction.category)
        )
        rows = self.db.execute(stmt).all()
        return {row[0]: Decimal(str(row[1])) for row in rows}

    def _get_period_stats(
        self, telegram_user_id: int, start: datetime, end: datetime
    ) -> dict:
        """Get aggregated stats for a time period."""
        # Convert naive datetimes to UTC for comparison
        if start.tzinfo is not None:
            start_utc = start.astimezone(timezone.utc)
        else:
            start_utc = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is not None:
            end_utc = end.astimezone(timezone.utc)
        else:
            end_utc = end.replace(tzinfo=timezone.utc)

        stmt = (
            select(Transaction)
            .where(
                Transaction.telegram_user_id == telegram_user_id,
                Transaction.created_at >= start_utc,
                Transaction.created_at < end_utc,
            )
        )
        transactions = list(self.db.scalars(stmt).all())

        expense_total = sum(
            float(tx.amount) for tx in transactions if tx.type == TransactionType.EXPENSE
        )
        income_total = sum(
            float(tx.amount) for tx in transactions if tx.type == TransactionType.INCOME
        )

        category_totals: dict[str, float] = {}
        for tx in transactions:
            if tx.type == TransactionType.EXPENSE:
                category_totals[tx.category] = category_totals.get(tx.category, 0) + float(tx.amount)

        return {
            "expense_total": expense_total,
            "income_total": income_total,
            "tx_count": len(transactions),
            "category_totals": category_totals,
        }
