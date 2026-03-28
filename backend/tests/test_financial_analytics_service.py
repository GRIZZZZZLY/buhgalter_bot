from __future__ import annotations

from decimal import Decimal

from app.services.financial_analytics_service import FinancialAnalyticsService
from app.services.financial_snapshot_service import (
    BudgetSnapshot,
    CategorySpendSnapshot,
    FinancialSnapshot,
    MonthlyStatsSnapshot,
    PlannedExpenseSnapshot,
    RecentTransactionSnapshot,
    RecurringPaymentSnapshot,
    SummarySnapshot,
)


def _snapshot() -> FinancialSnapshot:
    return FinancialSnapshot(
        today="2026-03-15",
        summary=SummarySnapshot(
            income=Decimal("40000"),
            expenses=Decimal("18000"),
            balance=Decimal("22000"),
        ),
        top_categories=[CategorySpendSnapshot(category="еда", amount=Decimal("9000"))],
        recent_transactions=[
            RecentTransactionSnapshot(
                date_label="15.03",
                transaction_type="expense",
                amount=Decimal("700"),
                category="еда",
                description="кофе",
            )
        ],
        monthly_stats=[
            MonthlyStatsSnapshot(
                year_month="2026-03",
                income=Decimal("40000"),
                expenses=Decimal("18000"),
                by_category={"еда": Decimal("9000")},
            ),
            MonthlyStatsSnapshot(
                year_month="2026-02",
                income=Decimal("42000"),
                expenses=Decimal("15000"),
                by_category={"еда": Decimal("7000")},
            ),
        ],
        budgets=[
            BudgetSnapshot(
                category="еда",
                limit_amount=Decimal("8000"),
                spent_amount=Decimal("9000"),
                percent_used=112,
                warning=True,
            )
        ],
        planned_expenses=[
            PlannedExpenseSnapshot(
                title="Налог",
                amount=Decimal("4200"),
                planned_date="2026-04-10",
                category="fees",
            )
        ],
        recurring_payments=[
            RecurringPaymentSnapshot(
                title="Интернет",
                amount=Decimal("800"),
                frequency="monthly",
                transaction_type="expense",
            )
        ],
    )


def test_forecast_month_end_uses_real_month_length() -> None:
    analytics = FinancialAnalyticsService().build(_snapshot())

    assert analytics.forecast.days_passed == 15
    assert analytics.forecast.days_in_month == 31
    assert analytics.forecast.projected_expenses == Decimal("37200")


def test_budget_health_flags_overheated_categories() -> None:
    analytics = FinancialAnalyticsService().build(_snapshot())

    assert analytics.budget_health.total_budgets == 1
    assert analytics.budget_health.overheated_categories == ["еда"]
    assert analytics.budget_health.score < 100


def test_primary_risk_prefers_budget_overrun() -> None:
    analytics = FinancialAnalyticsService().build(_snapshot())

    assert analytics.primary_risk is not None
    assert analytics.primary_risk.title == "budget_overrun"
    assert "еда" in analytics.primary_risk.detail
