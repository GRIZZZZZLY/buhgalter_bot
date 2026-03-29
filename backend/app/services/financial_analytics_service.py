from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

from app.services.financial_snapshot_service import FinancialSnapshot, MonthlyStatsSnapshot


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
    # Agent v1 additions:
    primary_risk_v2: PrimaryRisk | None = None
    saving_opportunity: SavingOpportunity | None = None
    payment_pressure: PaymentPressure | None = None


class RiskType(Enum):
    BUDGET_OVERRUN = "budget_overrun"
    BUDGET_NEAR_LIMIT = "budget_near_limit"
    FORECAST_OVERRUN = "forecast_overrun"
    UPCOMING_LARGE = "upcoming_large"
    SPENDING_SPIKE = "spending_spike"
    NONE = "none"


@dataclass(frozen=True)
class PrimaryRisk:
    risk_type: RiskType
    title: str
    detail: str
    severity: float
    category: str | None
    amount: Decimal | None


@dataclass(frozen=True)
class SavingOpportunity:
    category: str
    current_spend: Decimal
    suggested_limit: Decimal
    potential_saving: Decimal
    reason: str
    confidence: str


@dataclass(frozen=True)
class PaymentPressure:
    total_upcoming: Decimal
    available_balance: Decimal
    coverage_ratio: float
    critical_payments: list[dict]
    pressure_level: str


class FinancialAnalyticsService:
    def build(self, snapshot: FinancialSnapshot) -> FinancialAnalyticsSnapshot:
        forecast = self.forecast_month_end(snapshot)
        budget_health = self.budget_health_summary(snapshot)
        primary_risk = self.detect_primary_risk(snapshot, forecast, budget_health)
        primary_risk_v2 = self.detect_primary_risk_v2(snapshot)
        saving_opportunity = self.top_saving_opportunity(snapshot, snapshot.monthly_stats)
        payment_pressure = self.upcoming_payment_pressure(snapshot)
        return FinancialAnalyticsSnapshot(
            forecast=forecast,
            budget_health=budget_health,
            primary_risk=primary_risk,
            primary_risk_v2=primary_risk_v2,
            saving_opportunity=saving_opportunity,
            payment_pressure=payment_pressure,
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

    def detect_primary_risk_v2(self, snapshot: FinancialSnapshot) -> PrimaryRisk:
        candidates: list[PrimaryRisk] = []

        for budget in snapshot.budgets:
            pct = budget.percent_used
            if pct >= 100:
                severity = min(1.0, (pct - 100) / 50 + 0.8)
                overspend = budget.spent_amount - budget.limit_amount
                candidates.append(PrimaryRisk(
                    risk_type=RiskType.BUDGET_OVERRUN,
                    title="Превышен бюджет",
                    detail=f"Категория «{budget.category}» вышла за лимит на {self._fmt(overspend)}.",
                    severity=severity,
                    category=budget.category,
                    amount=overspend,
                ))
            elif 85 <= pct < 100:
                severity = 0.5 + (pct - 85) / 100
                candidates.append(PrimaryRisk(
                    risk_type=RiskType.BUDGET_NEAR_LIMIT,
                    title="Бюджет почти исчерпан",
                    detail=f"Категория «{budget.category}» использована на {pct:.0f}%.",
                    severity=severity,
                    category=budget.category,
                    amount=None,
                ))

        forecast = self.forecast_month_end(snapshot)
        total_budget = sum((b.limit_amount for b in snapshot.budgets), Decimal("0"))
        if total_budget > 0 and forecast.projected_expenses > total_budget:
            overrun = forecast.projected_expenses - total_budget
            candidates.append(PrimaryRisk(
                risk_type=RiskType.FORECAST_OVERRUN,
                title="Прогноз превысит бюджет",
                detail=(
                    f"При текущем темпе расходы к концу месяца составят "
                    f"{self._fmt(forecast.projected_expenses)}, что превышает бюджет на {self._fmt(overrun)}."
                ),
                severity=0.6,
                category=None,
                amount=overrun,
            ))

        today = date.fromisoformat(snapshot.today)
        for planned in snapshot.planned_expenses:
            planned_date = date.fromisoformat(planned.planned_date)
            days_until = (planned_date - today).days
            if 0 <= days_until <= 7 and planned.amount >= Decimal("5000"):
                candidates.append(PrimaryRisk(
                    risk_type=RiskType.UPCOMING_LARGE,
                    title="Крупный платёж на горизонте",
                    detail=f"Через {days_until} дн. запланирован платёж на {self._fmt(planned.amount)}: {planned.title}.",
                    severity=0.6,
                    category=planned.category,
                    amount=planned.amount,
                ))

        if not candidates:
            return PrimaryRisk(
                risk_type=RiskType.NONE,
                title="Рисков не обнаружено",
                detail="Финансовая ситуация в норме.",
                severity=0.0,
                category=None,
                amount=None,
            )

        return max(candidates, key=lambda r: r.severity)

    def _compute_avg_category_spend(
        self, monthly_stats: list[MonthlyStatsSnapshot]
    ) -> dict[str, Decimal]:
        totals: dict[str, list[Decimal]] = {}
        for month in monthly_stats:
            for cat, amount in month.by_category.items():
                totals.setdefault(cat, []).append(amount)
        return {
            cat: sum(amounts) / len(amounts)
            for cat, amounts in totals.items()
        }

    def top_saving_opportunity(
        self,
        snapshot: FinancialSnapshot,
        monthly_stats: list[MonthlyStatsSnapshot],
    ) -> SavingOpportunity | None:
        avg_spend = self._compute_avg_category_spend(monthly_stats)
        current_spend: dict[str, Decimal] = {}
        if snapshot.monthly_stats:
            current_spend = dict(snapshot.monthly_stats[0].by_category)

        budget_categories = {b.category for b in snapshot.budgets}
        opportunities: list[SavingOpportunity] = []

        for cat, spend in current_spend.items():
            if spend < Decimal("3000"):
                continue

            avg = avg_spend.get(cat)

            if cat not in budget_categories:
                opportunities.append(SavingOpportunity(
                    category=cat,
                    current_spend=spend,
                    suggested_limit=(spend * Decimal("0.8")).quantize(Decimal("1"), rounding=ROUND_HALF_UP),
                    potential_saving=(spend * Decimal("0.2")).quantize(Decimal("1"), rounding=ROUND_HALF_UP),
                    reason="Нет бюджетного лимита",
                    confidence="medium",
                ))
            elif avg and avg > Decimal("0"):
                growth = spend / avg  # Decimal / Decimal
                if growth >= Decimal("1.3"):
                    confidence = "high" if growth >= Decimal("1.5") else "medium"
                    opportunities.append(SavingOpportunity(
                        category=cat,
                        current_spend=spend,
                        suggested_limit=avg.quantize(Decimal("1"), rounding=ROUND_HALF_UP),
                        potential_saving=(spend - avg).quantize(Decimal("1"), rounding=ROUND_HALF_UP),
                        reason=f"На {float((growth - Decimal('1')) * 100):.0f}% выше среднего",
                        confidence=confidence,
                    ))

        if not opportunities:
            return None
        return max(opportunities, key=lambda o: o.potential_saving)

    def upcoming_payment_pressure(self, snapshot: FinancialSnapshot) -> PaymentPressure:
        today = date.fromisoformat(snapshot.today)
        upcoming_14: list = []
        critical_3: list[dict] = []

        for planned in snapshot.planned_expenses:
            planned_date = date.fromisoformat(planned.planned_date)
            days_until = (planned_date - today).days
            if 0 <= days_until <= 14:
                upcoming_14.append(planned)
            if 0 <= days_until <= 3:
                critical_3.append({
                    "description": planned.title,
                    "amount": float(planned.amount),
                    "date": planned.planned_date,
                    "days_until": days_until,
                })

        total = sum((p.amount for p in upcoming_14), Decimal("0"))
        balance = snapshot.summary.balance if snapshot.summary.balance is not None else Decimal("0")

        if total <= Decimal("0"):
            return PaymentPressure(
                total_upcoming=Decimal("0"),
                available_balance=balance,
                coverage_ratio=1.0,
                critical_payments=[],
                pressure_level="none",
            )

        ratio = float(balance) / float(total)
        if ratio < 0.5:
            level = "high"
        elif ratio < 1.0:
            level = "medium"
        elif ratio < 2.0:
            level = "low"
        else:
            level = "none"

        return PaymentPressure(
            total_upcoming=total,
            available_balance=balance,
            coverage_ratio=ratio,
            critical_payments=sorted(critical_3, key=lambda p: p["days_until"]),
            pressure_level=level,
        )
