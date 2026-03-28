from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.services.financial_snapshot_service import FinancialSnapshot


@dataclass(frozen=True)
class ForecastSnapshot:
    days_passed: int
    days_in_month: int
    projected_expenses: Decimal
    projected_income: Decimal


@dataclass(frozen=True)
class BudgetHealthSnapshot:
    total_budgets: int
    risky_categories: list[str]
    overheated_categories: list[str]
    score: int


@dataclass(frozen=True)
class PrimaryRiskSnapshot:
    title: str
    detail: str
    severity: str


@dataclass(frozen=True)
class FinancialAnalyticsSnapshot:
    forecast: ForecastSnapshot
    budget_health: BudgetHealthSnapshot
    primary_risk: PrimaryRiskSnapshot | None


class FinancialAnalyticsService:
    def build(self, snapshot: FinancialSnapshot) -> FinancialAnalyticsSnapshot:
        forecast = self.forecast_month_end(snapshot)
        budget_health = self.budget_health_summary(snapshot)
        primary_risk = self.detect_primary_risk(snapshot, forecast, budget_health)
        return FinancialAnalyticsSnapshot(
            forecast=forecast,
            budget_health=budget_health,
            primary_risk=primary_risk,
        )

    def forecast_month_end(self, snapshot: FinancialSnapshot) -> ForecastSnapshot:
        today = date.fromisoformat(snapshot.today)
        days_passed = max(today.day, 1)
        days_in_month = calendar.monthrange(today.year, today.month)[1]

        projected_expenses = self._project_total(snapshot.summary.expenses, days_passed, days_in_month)
        projected_income = self._project_total(snapshot.summary.income, days_passed, days_in_month)
        return ForecastSnapshot(
            days_passed=days_passed,
            days_in_month=days_in_month,
            projected_expenses=projected_expenses,
            projected_income=projected_income,
        )

    def budget_health_summary(self, snapshot: FinancialSnapshot) -> BudgetHealthSnapshot:
        budgets = snapshot.budgets
        total = len(budgets)
        risky = [item.category for item in budgets if item.percent_used >= 90]
        overheated = [item.category for item in budgets if item.percent_used >= 100]

        score = 100
        score -= len(risky) * 15
        score -= len(overheated) * 10
        score = max(0, min(100, score)) if total else 100

        return BudgetHealthSnapshot(
            total_budgets=total,
            risky_categories=risky,
            overheated_categories=overheated,
            score=score,
        )

    def detect_primary_risk(
        self,
        snapshot: FinancialSnapshot,
        forecast: ForecastSnapshot,
        budget_health: BudgetHealthSnapshot,
    ) -> PrimaryRiskSnapshot | None:
        if budget_health.overheated_categories:
            category = budget_health.overheated_categories[0]
            return PrimaryRiskSnapshot(
                title="budget_overrun",
                detail=f"Категория {category} уже вышла за лимит.",
                severity="high",
            )

        if budget_health.risky_categories:
            category = budget_health.risky_categories[0]
            return PrimaryRiskSnapshot(
                title="budget_risk",
                detail=f"Категория {category} уже близко к перерасходу.",
                severity="medium",
            )

        total_budget = sum((item.limit_amount for item in snapshot.budgets), start=Decimal("0"))
        if total_budget > 0 and forecast.projected_expenses > total_budget:
            return PrimaryRiskSnapshot(
                title="month_forecast_over_budget",
                detail=(
                    f"Текущий темп даёт прогноз {self._fmt(forecast.projected_expenses)} к концу месяца, "
                    f"что выше общего бюджета {self._fmt(total_budget)}."
                ),
                severity="medium",
            )

        if snapshot.planned_expenses:
            item = snapshot.planned_expenses[0]
            return PrimaryRiskSnapshot(
                title="upcoming_payment",
                detail=f"Скоро запланирован расход {item.title} на {self._fmt(item.amount)}.",
                severity="medium",
            )

        if snapshot.top_categories:
            item = snapshot.top_categories[0]
            return PrimaryRiskSnapshot(
                title="top_category_pressure",
                detail=f"Самая тяжёлая категория сейчас — {item.category} ({self._fmt(item.amount)}).",
                severity="low",
            )

        return None

    @staticmethod
    def _project_total(current_total: Decimal, days_passed: int, days_in_month: int) -> Decimal:
        if current_total <= 0:
            return Decimal("0")
        projected = (current_total / Decimal(days_passed)) * Decimal(days_in_month)
        return projected.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _fmt(value: Decimal) -> str:
        return f"{value.quantize(Decimal('1'), rounding=ROUND_HALF_UP):.0f}₽"
