from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.apply_action import ApplyAction, ApplyActionType
from app.services.financial_analytics_service import FinancialAnalyticsSnapshot
from app.services.financial_snapshot_service import FinancialSnapshot


@dataclass(frozen=True)
class RecommendationItem:
    title: str
    detail: str
    score: float
    action_type: str
    category: str | None = None
    can_apply: bool = False
    apply_action: ApplyAction | None = None
    why_now: str | None = None

    @property
    def priority(self) -> str:
        if self.score >= 0.75:
            return "high"
        if self.score >= 0.40:
            return "medium"
        return "low"


@dataclass(frozen=True)
class RecommendationSnapshot:
    primary: RecommendationItem | None
    secondary: list[RecommendationItem]
    generated_at: datetime
    data_quality: str

    def is_empty(self) -> bool:
        return self.primary is None and not self.secondary


class RecommendationService:
    def build(
        self,
        snapshot: FinancialSnapshot,
        analytics: FinancialAnalyticsSnapshot,
        exclude_action_types: list[str] | None = None,
    ) -> RecommendationSnapshot:
        data_quality = self._assess_data_quality(snapshot)
        candidates: list[RecommendationItem] = []
        candidates.extend(self._score_budget_overrun(snapshot))
        candidates.extend(self._score_forecast_risk(snapshot, analytics))
        candidates.extend(self._score_upcoming_payments(snapshot, analytics))
        candidates.extend(self._score_top_category_pressure(snapshot))

        if exclude_action_types:
            candidates = [c for c in candidates if c.action_type not in exclude_action_types]

        sorted_items = sorted(candidates, key=lambda item: item.score, reverse=True)
        primary = sorted_items[0] if sorted_items else None
        secondary = sorted_items[1:3] if len(sorted_items) > 1 else []
        if primary is not None:
            primary = self._enrich_with_apply_action(primary, snapshot, analytics)
        return RecommendationSnapshot(
            primary=primary,
            secondary=secondary,
            generated_at=datetime.now(UTC),
            data_quality=data_quality,
        )

    def _assess_data_quality(self, snapshot: FinancialSnapshot) -> str:
        if not snapshot.has_any_activity:
            return 'minimal'
        signals = sum(
            1
            for present in (
                bool(snapshot.recent_transactions),
                bool(snapshot.monthly_stats),
                bool(snapshot.budgets),
                bool(snapshot.planned_expenses),
                bool(snapshot.recurring_payments),
            )
            if present
        )
        if signals >= 3:
            return 'full'
        return 'partial'

    def _score_budget_overrun(self, snapshot: FinancialSnapshot) -> list[RecommendationItem]:
        items: list[RecommendationItem] = []
        for budget in snapshot.budgets:
            if budget.limit_amount <= 0:
                continue
            ratio = float(budget.spent_amount / budget.limit_amount)
            if ratio >= 1:
                score = min(1.0, 0.9 + min(ratio - 1.0, 0.1))
                items.append(
                    RecommendationItem(
                        title=f'Срочно охлади категорию «{budget.category}»',
                        detail=f'Уже потрачено {budget.percent_used}% от лимита {budget.limit_amount:.0f}₽.',
                        score=score,
                        action_type='cut_costs',
                        category=budget.category,
                    )
                )
            elif ratio >= 0.9:
                score = min(0.79, 0.45 + (ratio - 0.9) * 3)
                items.append(
                    RecommendationItem(
                        title=f'Проверь бюджет по категории «{budget.category}»',
                        detail=f'Категория уже на {budget.percent_used}% от лимита {budget.limit_amount:.0f}₽.',
                        score=score,
                        action_type='budget_check',
                        category=budget.category,
                    )
                )
        return items

    def _score_forecast_risk(
        self,
        snapshot: FinancialSnapshot,
        analytics: FinancialAnalyticsSnapshot,
    ) -> list[RecommendationItem]:
        total_budget = sum((item.limit_amount for item in snapshot.budgets), start=Decimal('0'))
        if total_budget <= 0:
            return []
        projected = analytics.forecast.projected_expenses
        if projected <= total_budget:
            return []
        overflow = projected - total_budget
        ratio = float(projected / total_budget) if total_budget > 0 else 0.0
        score = min(0.84, 0.45 + max(0.0, ratio - 1.0))
        return [
            RecommendationItem(
                title='Сократи темп расходов до конца месяца',
                detail=(
                    f'Текущий прогноз {projected:.0f}₽ выше общего бюджета {total_budget:.0f}₽ '
                    f'примерно на {overflow:.0f}₽.'
                ),
                score=score,
                action_type='forecast_control',
            )
        ]

    def _score_upcoming_payments(
        self,
        snapshot: FinancialSnapshot,
        analytics: FinancialAnalyticsSnapshot,
    ) -> list[RecommendationItem]:
        if not snapshot.planned_expenses:
            return []
        item = snapshot.planned_expenses[0]
        baseline = max(snapshot.summary.income, Decimal('1'))
        ratio = float(item.amount / baseline)
        score = min(0.7, 0.25 + max(0.0, ratio))
        if analytics.primary_risk and analytics.primary_risk.title == 'upcoming_payment':
            score = max(score, 0.55)
        return [
            RecommendationItem(
                title=f'Подготовь ближайший платёж «{item.title}»',
                detail=f'{item.amount:.0f}₽ запланировано на {item.planned_date}.',
                score=score,
                action_type='upcoming_payment',
                category=item.category,
            )
        ]

    def _score_top_category_pressure(self, snapshot: FinancialSnapshot) -> list[RecommendationItem]:
        if not snapshot.top_categories or snapshot.summary.expenses <= 0:
            return []
        top = snapshot.top_categories[0]
        share = float(top.amount / snapshot.summary.expenses)
        if share < 0.35:
            return []
        score = min(0.65, 0.2 + share)
        return [
            RecommendationItem(
                title=f'Разбери категорию «{top.category}»',
                detail=f'Она уже забирает около {share * 100:.0f}% расходов месяца.',
                score=score,
                action_type='top_category_pressure',
                category=top.category,
            )
        ]

    def _make_apply_action_for_budget(
        self,
        category: str,
        suggested_limit: Decimal,
    ) -> ApplyAction:
        return ApplyAction(
            action_type=ApplyActionType.SET_BUDGET,
            label=f"Поставить бюджет «{category}» {suggested_limit:.0f} ₽/мес",
            payload={
                "category": category,
                "amount": str(suggested_limit),
            },
            preview_text=(
                f"Будет установлен месячный лимит:\n"
                f"• Категория: {category}\n"
                f"• Сумма: {suggested_limit:.0f} ₽\n\n"
                f"Текущий лимит будет заменён."
            ),
            is_reversible=True,
        )

    def _make_apply_action_for_reminder(
        self,
        description: str,
        payment_date,   # date
        amount: Decimal,
    ) -> ApplyAction:
        remind_date = payment_date - timedelta(days=2)
        return ApplyAction(
            action_type=ApplyActionType.SET_REMINDER,
            label=f"Напомнить о «{description}» за 2 дня",
            payload={
                "description": description,
                "remind_date": remind_date.isoformat(),
                "amount": str(amount),
            },
            preview_text=(
                f"Будет установлено напоминание:\n"
                f"• Платёж: {description} · {amount:.0f} ₽\n"
                f"• Напомнить: {remind_date.strftime('%d %b')}"
            ),
            is_reversible=True,
        )

    def _enrich_with_apply_action(
        self,
        item: RecommendationItem,
        snapshot,   # FinancialSnapshot
        analytics,  # FinancialAnalyticsSnapshot
    ) -> RecommendationItem:
        """Добавляет can_apply, apply_action, why_now к primary recommendation."""
        if item.action_type == "cut_costs" and item.category:
            opportunity = getattr(analytics, "saving_opportunity", None)
            if opportunity and opportunity.category == item.category:
                apply_action = self._make_apply_action_for_budget(
                    item.category,
                    opportunity.suggested_limit,
                )
                return dataclasses.replace(
                    item,
                    can_apply=True,
                    apply_action=apply_action,
                    why_now=f"Можно сэкономить {float(opportunity.potential_saving):.0f} ₽/мес",
                )

        if item.action_type == "prepare_payment":
            from datetime import date as _date
            today_date = _date.fromisoformat(snapshot.today)
            for planned in snapshot.planned_expenses:
                if planned.description and planned.amount:
                    days = (planned.date - today_date).days
                    if 0 <= days <= 7:
                        apply_action = self._make_apply_action_for_reminder(
                            planned.description,
                            planned.date,
                            planned.amount,
                        )
                        return dataclasses.replace(
                            item,
                            can_apply=True,
                            apply_action=apply_action,
                            why_now=f"Платёж через {days} дн.",
                        )

        return item
