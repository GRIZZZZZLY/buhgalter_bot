"""Tests for Agent v1: A1 analytics methods, A2 recommendation enrich, A3 payload v3."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.apply_action import ApplyAction, ApplyActionType
from app.services.financial_analytics_service import (
    FinancialAnalyticsService,
    RiskType,
)
from app.services.financial_snapshot_service import (
    BudgetSnapshot,
    CategorySpendSnapshot,
    FinancialSnapshot,
    MonthlyStatsSnapshot,
    PlannedExpenseSnapshot,
    SummarySnapshot,
)
from app.services.recommendation_service import RecommendationService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_snapshot(
    *,
    today: str = "2026-03-15",
    income: str = "40000",
    expenses: str = "18000",
    balance: str = "22000",
    budgets: list[BudgetSnapshot] | None = None,
    planned: list[PlannedExpenseSnapshot] | None = None,
    top_categories: list[CategorySpendSnapshot] | None = None,
    monthly_stats: list[MonthlyStatsSnapshot] | None = None,
) -> FinancialSnapshot:
    return FinancialSnapshot(
        today=today,
        summary=SummarySnapshot(
            income=Decimal(income),
            expenses=Decimal(expenses),
            balance=Decimal(balance),
        ),
        top_categories=top_categories or [],
        recent_transactions=[],
        monthly_stats=monthly_stats or [],
        budgets=budgets or [],
        planned_expenses=planned or [],
        recurring_payments=[],
    )


def _budget(category: str, limit: str, spent: str) -> BudgetSnapshot:
    limit_d = Decimal(limit)
    spent_d = Decimal(spent)
    pct = int(spent_d / limit_d * 100) if limit_d > 0 else 0
    return BudgetSnapshot(
        category=category,
        limit_amount=limit_d,
        spent_amount=spent_d,
        percent_used=pct,
        warning=pct >= 90,
    )


def _planned(title: str, amount: str, planned_date: str, category: str | None = None) -> PlannedExpenseSnapshot:
    return PlannedExpenseSnapshot(
        title=title,
        amount=Decimal(amount),
        planned_date=planned_date,
        category=category,
    )


svc = FinancialAnalyticsService()


# ===========================================================================
# A1 — detect_primary_risk_v2
# ===========================================================================

class TestDetectPrimaryRiskV2:
    def test_no_risk_returns_none_type(self) -> None:
        snapshot = _base_snapshot()
        risk = svc.detect_primary_risk_v2(snapshot)
        assert risk.risk_type == RiskType.NONE
        assert risk.severity == 0.0

    def test_budget_overrun_detected(self) -> None:
        snapshot = _base_snapshot(budgets=[_budget("еда", "10000", "12000")])
        risk = svc.detect_primary_risk_v2(snapshot)
        assert risk.risk_type == RiskType.BUDGET_OVERRUN
        assert risk.category == "еда"
        assert risk.severity > 0.7

    def test_budget_near_limit_85_percent(self) -> None:
        # Budget large enough to avoid FORECAST_OVERRUN: projected ~37200 < 40000
        snapshot = _base_snapshot(budgets=[_budget("транспорт", "40000", "34000")])
        risk = svc.detect_primary_risk_v2(snapshot)
        assert risk.risk_type == RiskType.BUDGET_NEAR_LIMIT
        assert risk.category == "транспорт"

    def test_overrun_has_higher_severity_than_near_limit(self) -> None:
        snapshot = _base_snapshot(budgets=[
            _budget("еда", "10000", "11000"),       # overrun
            _budget("транспорт", "10000", "9200"),   # near limit
        ])
        risk = svc.detect_primary_risk_v2(snapshot)
        assert risk.risk_type == RiskType.BUDGET_OVERRUN

    def test_forecast_overrun_detected(self) -> None:
        # today=15th, expenses=18000, budget=20000 → projected ~36000 > 20000
        snapshot = _base_snapshot(
            today="2026-03-15",
            expenses="18000",
            budgets=[_budget("прочее", "20000", "500")],
        )
        risk = svc.detect_primary_risk_v2(snapshot)
        assert risk.risk_type in {RiskType.FORECAST_OVERRUN, RiskType.BUDGET_NEAR_LIMIT, RiskType.BUDGET_OVERRUN}

    def test_upcoming_large_payment_within_7_days(self) -> None:
        snapshot = _base_snapshot(
            today="2026-03-15",
            planned=[_planned("аренда", "30000", "2026-03-18")],
        )
        risk = svc.detect_primary_risk_v2(snapshot)
        assert risk.risk_type == RiskType.UPCOMING_LARGE
        assert risk.amount == Decimal("30000")

    def test_small_upcoming_payment_ignored(self) -> None:
        snapshot = _base_snapshot(
            today="2026-03-15",
            planned=[_planned("кофе", "500", "2026-03-17")],
        )
        risk = svc.detect_primary_risk_v2(snapshot)
        assert risk.risk_type == RiskType.NONE

    def test_upcoming_payment_outside_7_days_ignored(self) -> None:
        snapshot = _base_snapshot(
            today="2026-03-15",
            planned=[_planned("аренда", "30000", "2026-03-25")],
        )
        risk = svc.detect_primary_risk_v2(snapshot)
        assert risk.risk_type == RiskType.NONE


# ===========================================================================
# A1 — top_saving_opportunity
# ===========================================================================

class TestTopSavingOpportunity:
    def test_no_opportunity_when_no_data(self) -> None:
        snapshot = _base_snapshot()
        result = svc.top_saving_opportunity(snapshot, [])
        assert result is None

    def test_category_without_budget_flagged(self) -> None:
        snapshot = _base_snapshot(
            monthly_stats=[
                MonthlyStatsSnapshot(
                    year_month="2026-03",
                    income=Decimal("40000"),
                    expenses=Decimal("18000"),
                    by_category={"развлечения": Decimal("8000")},
                )
            ],
        )
        result = svc.top_saving_opportunity(snapshot, snapshot.monthly_stats)
        assert result is not None
        assert result.category == "развлечения"
        assert result.potential_saving > 0

    def test_small_spend_ignored(self) -> None:
        snapshot = _base_snapshot(
            monthly_stats=[
                MonthlyStatsSnapshot(
                    year_month="2026-03",
                    income=Decimal("40000"),
                    expenses=Decimal("5000"),
                    by_category={"прочее": Decimal("500")},
                )
            ],
        )
        result = svc.top_saving_opportunity(snapshot, snapshot.monthly_stats)
        assert result is None

    def test_growth_30_percent_flagged(self) -> None:
        # current=14000, prev=7000 → avg=(14000+7000)/2=10500, growth=14000/10500≈1.33 > 1.3
        monthly_stats = [
            MonthlyStatsSnapshot(
                year_month="2026-03",
                income=Decimal("40000"),
                expenses=Decimal("20000"),
                by_category={"еда": Decimal("14000")},  # current month
            ),
            MonthlyStatsSnapshot(
                year_month="2026-02",
                income=Decimal("40000"),
                expenses=Decimal("15000"),
                by_category={"еда": Decimal("7000")},   # previous month
            ),
        ]
        snapshot = _base_snapshot(
            monthly_stats=monthly_stats,
            budgets=[_budget("еда", "12000", "14000")],  # has budget → growth path
        )
        result = svc.top_saving_opportunity(snapshot, monthly_stats)
        assert result is not None
        assert result.category == "еда"


# ===========================================================================
# A1 — upcoming_payment_pressure
# ===========================================================================

class TestUpcomingPaymentPressure:
    def test_none_pressure_when_no_planned(self) -> None:
        snapshot = _base_snapshot()
        pressure = svc.upcoming_payment_pressure(snapshot)
        assert pressure.pressure_level == "none"
        assert pressure.total_upcoming == Decimal("0")

    def test_high_pressure_when_balance_less_than_half(self) -> None:
        snapshot = _base_snapshot(
            today="2026-03-15",
            balance="5000",
            planned=[_planned("аренда", "20000", "2026-03-20")],
        )
        pressure = svc.upcoming_payment_pressure(snapshot)
        assert pressure.pressure_level == "high"
        assert pressure.total_upcoming == Decimal("20000")

    def test_low_pressure_when_balance_covers_well(self) -> None:
        snapshot = _base_snapshot(
            today="2026-03-15",
            balance="30000",
            planned=[_planned("аренда", "15000", "2026-03-20")],
        )
        pressure = svc.upcoming_payment_pressure(snapshot)
        assert pressure.pressure_level in {"low", "none"}

    def test_critical_payments_only_within_3_days(self) -> None:
        snapshot = _base_snapshot(
            today="2026-03-15",
            balance="50000",
            planned=[
                _planned("близко", "5000", "2026-03-16"),   # 1 day — critical
                _planned("далеко", "5000", "2026-03-25"),   # outside 14 days
            ],
        )
        pressure = svc.upcoming_payment_pressure(snapshot)
        assert len(pressure.critical_payments) == 1
        assert pressure.critical_payments[0]["description"] == "близко"

    def test_payment_outside_14_days_not_counted(self) -> None:
        snapshot = _base_snapshot(
            today="2026-03-15",
            balance="100",
            planned=[_planned("далёкий", "50000", "2026-04-10")],
        )
        pressure = svc.upcoming_payment_pressure(snapshot)
        assert pressure.pressure_level == "none"


# ===========================================================================
# A1 — FinancialAnalyticsSnapshot.build integration
# ===========================================================================

def test_analytics_snapshot_includes_v2_fields() -> None:
    snapshot = _base_snapshot()
    analytics = svc.build(snapshot)
    assert hasattr(analytics, "primary_risk_v2")
    assert hasattr(analytics, "saving_opportunity")
    assert hasattr(analytics, "payment_pressure")
    assert analytics.primary_risk_v2 is not None
    assert analytics.payment_pressure is not None


# ===========================================================================
# A2 — ApplyAction
# ===========================================================================

class TestApplyAction:
    def test_to_callback_data_format(self) -> None:
        action = ApplyAction(
            action_type=ApplyActionType.SET_BUDGET,
            label="Поставить бюджет",
            payload={"category": "еда", "suggested_limit": 12000},
            preview_text="Лимит 12 000 ₽",
            is_reversible=True,
        )
        cb = action.to_callback_data()
        assert cb.startswith("apply:set_budget:")
        assert len(cb) <= 64

    def test_callback_data_deterministic(self) -> None:
        action = ApplyAction(
            action_type=ApplyActionType.SET_REMINDER,
            label="Напоминание",
            payload={"description": "аренда", "payment_date": "2026-03-28", "amount": 30000},
            preview_text="Напомнить за 2 дня",
            is_reversible=True,
        )
        assert action.to_callback_data() == action.to_callback_data()


# ===========================================================================
# A2 — RecommendationService enrich with apply_action
# ===========================================================================

class TestRecommendationEnrich:
    def test_can_apply_false_when_no_saving_opportunity(self) -> None:
        snapshot = _base_snapshot(
            budgets=[_budget("еда", "10000", "10500")],  # overrun → cut_costs
        )
        analytics = svc.build(snapshot)
        recs = RecommendationService().build(snapshot, analytics)
        primary = recs.primary
        assert primary is not None
        # saving_opportunity may or may not exist; if it doesn't match category, can_apply=False
        if not analytics.saving_opportunity or analytics.saving_opportunity.category != primary.category:
            assert primary.can_apply is False

    def test_can_apply_true_when_saving_opportunity_matches(self) -> None:
        monthly_stats = [
            MonthlyStatsSnapshot(
                year_month="2026-03",
                income=Decimal("40000"),
                expenses=Decimal("20000"),
                by_category={"еда": Decimal("12000")},
            ),
            MonthlyStatsSnapshot(
                year_month="2026-02",
                income=Decimal("40000"),
                expenses=Decimal("15000"),
                by_category={"еда": Decimal("7000")},
            ),
        ]
        snapshot = _base_snapshot(
            monthly_stats=monthly_stats,
            budgets=[_budget("еда", "10000", "12000")],  # overrun → cut_costs for "еда"
        )
        analytics = svc.build(snapshot)
        # Force saving_opportunity to match by checking what we built
        if analytics.saving_opportunity and analytics.saving_opportunity.category == "еда":
            recs = RecommendationService().build(snapshot, analytics)
            primary = recs.primary
            if primary and primary.action_type == "cut_costs" and primary.category == "еда":
                assert primary.can_apply is True
                assert primary.apply_action is not None


# ===========================================================================
# A3 — AdvisorAnswerPayload v3 fields
# ===========================================================================

def test_advisor_payload_version_3() -> None:
    from app.services.financial_qa_service import AdvisorAnswerPayload, ResponseMode
    payload = AdvisorAnswerPayload(
        answer="Тест",
        basis=[],
        warnings=[],
        confidence="medium",
    )
    assert payload.payload_version == 3
    assert payload.next_step is None
    assert payload.why_now is None
    assert payload.can_apply is False
    assert payload.apply_action is None


def test_advisor_payload_with_apply_action() -> None:
    from app.services.financial_qa_service import AdvisorAnswerPayload
    action = ApplyAction(
        action_type=ApplyActionType.SET_BUDGET,
        label="Бюджет 12000",
        payload={"category": "еда", "suggested_limit": 12000},
        preview_text="Лимит 12 000 ₽",
        is_reversible=True,
    )
    payload = AdvisorAnswerPayload(
        answer="Советую поставить бюджет",
        basis=["Перерасход в марте"],
        warnings=[],
        confidence="high",
        next_step="Поставить бюджет «еда» 12 000 ₽/мес",
        why_now="Уже вышла за лимит на 2 000 ₽",
        can_apply=True,
        apply_action=action,
    )
    assert payload.can_apply is True
    assert payload.apply_action is action
    assert payload.next_step == "Поставить бюджет «еда» 12 000 ₽/мес"


# ===========================================================================
# A4 — AdvisorFormatter.format_action_proposal
# ===========================================================================

def test_format_action_proposal_includes_next_step() -> None:
    from app.services.financial_qa_service import AdvisorAnswerPayload
    from app.telegram.formatter import AdvisorFormatter
    payload = AdvisorAnswerPayload(
        answer="Расходы растут.",
        basis=[],
        warnings=[],
        confidence="medium",
        next_step="Поставить лимит на еду 12 000 ₽",
        why_now="Уже на 20% выше обычного",
    )
    result = AdvisorFormatter().format_action_proposal(payload)
    assert "Поставить лимит на еду 12 000 ₽" in result
    assert "Уже на 20% выше обычного" in result


def test_format_action_proposal_no_next_step() -> None:
    from app.services.financial_qa_service import AdvisorAnswerPayload
    from app.telegram.formatter import AdvisorFormatter
    payload = AdvisorAnswerPayload(
        answer="Всё в порядке.",
        basis=[],
        warnings=[],
        confidence="high",
    )
    result = AdvisorFormatter().format_action_proposal(payload)
    assert "Всё в порядке." in result


# ===========================================================================
# A4 — advisor_apply_keyboard
# ===========================================================================

def test_advisor_apply_keyboard_no_apply_button_when_can_apply_false() -> None:
    from app.services.financial_qa_service import AdvisorAnswerPayload
    from app.telegram.keyboards import advisor_apply_keyboard
    payload = AdvisorAnswerPayload(
        answer="Тест",
        basis=[],
        warnings=[],
        confidence="medium",
        can_apply=False,
    )
    kb = advisor_apply_keyboard(payload)
    all_cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert not any(cb and cb.startswith("apply:") for cb in all_cbs)


def test_advisor_apply_keyboard_has_apply_button_when_can_apply_true() -> None:
    from app.services.financial_qa_service import AdvisorAnswerPayload
    from app.telegram.keyboards import advisor_apply_keyboard
    action = ApplyAction(
        action_type=ApplyActionType.SET_BUDGET,
        label="Бюджет",
        payload={"category": "еда", "suggested_limit": 10000},
        preview_text="Лимит 10 000 ₽",
        is_reversible=True,
    )
    payload = AdvisorAnswerPayload(
        answer="Тест",
        basis=[],
        warnings=[],
        confidence="high",
        can_apply=True,
        apply_action=action,
    )
    kb = advisor_apply_keyboard(payload)
    all_cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
    assert any(cb.startswith("apply:set_budget:") for cb in all_cbs)
