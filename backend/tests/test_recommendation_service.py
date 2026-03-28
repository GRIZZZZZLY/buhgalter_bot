from __future__ import annotations

from decimal import Decimal

from app.services.financial_analytics_service import FinancialAnalyticsService
from app.services.financial_snapshot_service import (
    BudgetSnapshot,
    CategorySpendSnapshot,
    FinancialSnapshot,
    PlannedExpenseSnapshot,
    SummarySnapshot,
)
from app.services.recommendation_service import RecommendationService


def _snapshot(
    *,
    expenses: str = "18000",
    budgets: list[BudgetSnapshot] | None = None,
    planned: list[PlannedExpenseSnapshot] | None = None,
    top_categories: list[CategorySpendSnapshot] | None = None,
) -> FinancialSnapshot:
    return FinancialSnapshot(
        today="2026-03-15",
        summary=SummarySnapshot(
            income=Decimal("40000"),
            expenses=Decimal(expenses),
            balance=Decimal("22000"),
        ),
        top_categories=top_categories or [CategorySpendSnapshot(category="еда", amount=Decimal("9000"))],
        recent_transactions=[],
        monthly_stats=[],
        budgets=budgets or [],
        planned_expenses=planned or [],
        recurring_payments=[],
    )


def test_recommendation_snapshot_empty_for_minimal_data() -> None:
    snapshot = FinancialSnapshot(
        today="2026-03-15",
        summary=SummarySnapshot(income=Decimal("0"), expenses=Decimal("0"), balance=Decimal("0")),
        top_categories=[],
        recent_transactions=[],
        monthly_stats=[],
        budgets=[],
        planned_expenses=[],
        recurring_payments=[],
    )
    analytics = FinancialAnalyticsService().build(snapshot)
    recs = RecommendationService().build(snapshot, analytics)

    assert recs.primary is None
    assert recs.secondary == []
    assert recs.data_quality == "minimal"
    assert recs.is_empty() is True


def test_recommendation_primary_prefers_budget_overrun() -> None:
    snapshot = _snapshot(
        budgets=[
            BudgetSnapshot(
                category="еда",
                limit_amount=Decimal("8000"),
                spent_amount=Decimal("9000"),
                percent_used=112,
                warning=True,
            )
        ],
        planned=[
            PlannedExpenseSnapshot(
                title="Налог",
                amount=Decimal("4200"),
                planned_date="2026-04-10",
                category="fees",
            )
        ],
    )
    analytics = FinancialAnalyticsService().build(snapshot)
    recs = RecommendationService().build(snapshot, analytics)

    assert recs.primary is not None
    assert recs.primary.action_type == "cut_costs"
    assert recs.primary.priority == "high"
    assert recs.primary.score >= 0.75
    assert len(recs.secondary) <= 2


def test_recommendation_detects_forecast_over_budget() -> None:
    snapshot = _snapshot(
        expenses="30000",
        budgets=[
            BudgetSnapshot(
                category="еда",
                limit_amount=Decimal("8000"),
                spent_amount=Decimal("5000"),
                percent_used=62,
                warning=False,
            ),
            BudgetSnapshot(
                category="транспорт",
                limit_amount=Decimal("6000"),
                spent_amount=Decimal("4000"),
                percent_used=66,
                warning=False,
            ),
        ],
        top_categories=[CategorySpendSnapshot(category="еда", amount=Decimal("12000"))],
    )
    analytics = FinancialAnalyticsService().build(snapshot)
    recs = RecommendationService().build(snapshot, analytics)

    all_items = [item for item in [recs.primary, *recs.secondary] if item is not None]
    assert any(item.action_type == "forecast_control" for item in all_items)


def test_recommendation_data_quality_partial_when_some_signals_exist() -> None:
    snapshot = _snapshot(
        budgets=[
            BudgetSnapshot(
                category="еда",
                limit_amount=Decimal("8000"),
                spent_amount=Decimal("7200"),
                percent_used=90,
                warning=True,
            )
        ],
        planned=[],
        top_categories=[],
    )
    analytics = FinancialAnalyticsService().build(snapshot)
    recs = RecommendationService().build(snapshot, analytics)

    assert recs.data_quality == "partial"
