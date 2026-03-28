from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories.category_budget_repository import CategoryBudgetRepository
from app.repositories.planned_expense_repository import PlannedExpenseRepository
from app.repositories.recurring_transaction_repository import RecurringTransactionRepository
from app.repositories.transaction_repository import TransactionRepository


@dataclass(frozen=True)
class SummarySnapshot:
    income: Decimal
    expenses: Decimal
    balance: Decimal


@dataclass(frozen=True)
class CategorySpendSnapshot:
    category: str
    amount: Decimal


@dataclass(frozen=True)
class RecentTransactionSnapshot:
    date_label: str
    transaction_type: str
    amount: Decimal
    category: str
    description: str | None


@dataclass(frozen=True)
class MonthlyStatsSnapshot:
    year_month: str
    income: Decimal
    expenses: Decimal
    by_category: dict[str, Decimal]


@dataclass(frozen=True)
class BudgetSnapshot:
    category: str
    limit_amount: Decimal
    spent_amount: Decimal
    percent_used: int
    warning: bool


@dataclass(frozen=True)
class PlannedExpenseSnapshot:
    title: str
    amount: Decimal
    planned_date: str
    category: str | None


@dataclass(frozen=True)
class RecurringPaymentSnapshot:
    title: str
    amount: Decimal
    frequency: str
    transaction_type: str


@dataclass(frozen=True)
class FinancialSnapshot:
    today: str
    summary: SummarySnapshot
    top_categories: list[CategorySpendSnapshot]
    recent_transactions: list[RecentTransactionSnapshot]
    monthly_stats: list[MonthlyStatsSnapshot]
    budgets: list[BudgetSnapshot]
    planned_expenses: list[PlannedExpenseSnapshot]
    recurring_payments: list[RecurringPaymentSnapshot]

    @property
    def has_any_activity(self) -> bool:
        return any(
            (
                self.summary.income > 0,
                self.summary.expenses > 0,
                bool(self.top_categories),
                bool(self.recent_transactions),
                bool(self.budgets),
                bool(self.planned_expenses),
                bool(self.recurring_payments),
            )
        )


class FinancialSnapshotService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.tx_repo = TransactionRepository(db)
        self.budget_repo = CategoryBudgetRepository(db)
        self.planned_repo = PlannedExpenseRepository(db)
        self.recurring_repo = RecurringTransactionRepository(db)

    def build(self, telegram_user_id: int) -> FinancialSnapshot:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        summary_raw = self.tx_repo.get_summary(telegram_user_id, period="month")
        summary = SummarySnapshot(
            income=Decimal(summary_raw.get("income_total", 0)),
            expenses=Decimal(summary_raw.get("expense_total", 0)),
            balance=Decimal(summary_raw.get("balance", 0)),
        )

        category_totals = self.tx_repo.sum_expenses_by_category(telegram_user_id, start=month_start, end=now)
        top_categories = [
            CategorySpendSnapshot(category=category, amount=amount)
            for category, amount in sorted(category_totals.items(), key=lambda kv: kv[1], reverse=True)[:10]
        ]

        recent_transactions = [
            RecentTransactionSnapshot(
                date_label=tx.created_at.strftime("%d.%m"),
                transaction_type=tx.type.value,
                amount=Decimal(str(tx.amount)),
                category=tx.category,
                description=tx.description,
            )
            for tx in self.tx_repo.list_for_user(telegram_user_id, limit=20, offset=0, period="month")
        ]

        monthly_stats = [
            MonthlyStatsSnapshot(
                year_month=item["year_month"],
                income=Decimal(item["income"]),
                expenses=Decimal(item["expenses"]),
                by_category={category: Decimal(amount) for category, amount in item["by_category"].items()},
            )
            for item in self.tx_repo.monthly_summary(telegram_user_id, months=3)
        ]

        budgets = []
        for budget in self.budget_repo.get_all_for_user(telegram_user_id):
            spent_amount = Decimal(str(category_totals.get(budget.category, 0)))
            limit_amount = Decimal(str(budget.amount))
            percent_used = int(spent_amount / limit_amount * 100) if limit_amount > 0 else 0
            budgets.append(
                BudgetSnapshot(
                    category=budget.category,
                    limit_amount=limit_amount,
                    spent_amount=spent_amount,
                    percent_used=percent_used,
                    warning=percent_used >= 90,
                )
            )

        planned_expenses = [
            PlannedExpenseSnapshot(
                title=item.title,
                amount=Decimal(str(item.amount)),
                planned_date=str(item.planned_date),
                category=getattr(item, "category", None),
            )
            for item in self.planned_repo.list_future_for_user(telegram_user_id)[:10]
        ]

        recurring_payments = [
            RecurringPaymentSnapshot(
                title=item.title,
                amount=Decimal(str(item.amount)),
                frequency=item.frequency,
                transaction_type=item.transaction_type,
            )
            for item in self.recurring_repo.list_active(telegram_user_id)
        ]

        return FinancialSnapshot(
            today=today,
            summary=summary,
            top_categories=top_categories,
            recent_transactions=recent_transactions,
            monthly_stats=monthly_stats,
            budgets=budgets,
            planned_expenses=planned_expenses,
            recurring_payments=recurring_payments,
        )
