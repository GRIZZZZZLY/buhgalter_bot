"""Tests for expanded FinancialQAService context."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.models.category_budget import CategoryBudget
from app.models.recurring_transaction import RecurringTransaction
from app.models.planned_expense import PlannedExpense
from app.models.user import User
from app.services.financial_qa_service import FinancialQAService


def _seed_user(db, uid: int = 555) -> None:
    from app.repositories.user_repository import UserRepository
    repo = UserRepository(db)
    repo.get_or_create(uid)


def test_context_includes_budgets(db_session) -> None:
    """_build_context() should include budget info when budgets exist."""
    _seed_user(db_session)
    budget = CategoryBudget(telegram_user_id=555, category="food", amount=15000)
    db_session.add(budget)
    db_session.commit()

    service = FinancialQAService(db_session)
    context = service._build_context(555)
    assert "БЮДЖЕТЫ" in context
    assert "food" in context
    assert "15000" in context


def test_context_includes_planned_expenses(db_session) -> None:
    """_build_context() should include upcoming planned expenses."""
    from datetime import date, timedelta
    _seed_user(db_session)
    pe = PlannedExpense(
        telegram_user_id=555,
        title="Стоматолог",
        amount=12000,
        category="health",
        planned_date=date.today() + timedelta(days=10),
    )
    db_session.add(pe)
    db_session.commit()

    service = FinancialQAService(db_session)
    context = service._build_context(555)
    assert "ПЛАНОВЫЕ РАСХОДЫ" in context
    assert "Стоматолог" in context
    assert "12000" in context


def test_context_includes_recurring(db_session) -> None:
    """_build_context() should include active recurring transactions."""
    _seed_user(db_session)
    rt = RecurringTransaction(
        telegram_user_id=555,
        title="Аренда",
        amount=45000,
        transaction_type="expense",
        category="housing",
        frequency="monthly",
        day_value=1,
        is_active=1,
        next_run_date="2026-04-01",
    )
    db_session.add(rt)
    db_session.commit()

    service = FinancialQAService(db_session)
    context = service._build_context(555)
    assert "РЕГУЛЯРНЫЕ ПЛАТЕЖИ" in context
    assert "Аренда" in context
    assert "45000" in context


def test_context_omits_empty_sections(db_session) -> None:
    """_build_context() should omit budget/planned/recurring sections when empty."""
    _seed_user(db_session)
    service = FinancialQAService(db_session)
    context = service._build_context(555)
    assert "БЮДЖЕТЫ" not in context
    assert "ПЛАНОВЫЕ РАСХОДЫ" not in context
    assert "РЕГУЛЯРНЫЕ ПЛАТЕЖИ" not in context
