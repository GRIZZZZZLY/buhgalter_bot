"""Tests for TransactionRepository date-range helpers used by InsightService."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.transaction import Transaction, TransactionType, TransactionSource
from app.repositories.transaction_repository import TransactionRepository


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _tx(db, uid, category, amount, days_ago, tx_type="expense"):
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    t = Transaction(
        telegram_user_id=uid,
        type=TransactionType(tx_type),
        amount=Decimal(str(amount)),
        category=category,
        source=TransactionSource("text"),
        raw_input="test",
        confidence=0.9,
        created_at=dt,
    )
    db.add(t)
    db.commit()
    return t


def test_sum_expenses_by_category_basic(db):
    _tx(db, 1, "food", 500, days_ago=2)
    _tx(db, 1, "food", 300, days_ago=4)
    _tx(db, 1, "transport", 200, days_ago=3)

    repo = TransactionRepository(db)
    start = datetime.now(timezone.utc) - timedelta(days=7)
    end = datetime.now(timezone.utc)
    result = repo.sum_expenses_by_category(1, start, end)

    assert result["food"] == Decimal("800")
    assert result["transport"] == Decimal("200")


def test_sum_expenses_by_category_excludes_income(db):
    _tx(db, 1, "salary", 10000, days_ago=2, tx_type="income")
    repo = TransactionRepository(db)
    start = datetime.now(timezone.utc) - timedelta(days=7)
    end = datetime.now(timezone.utc)
    result = repo.sum_expenses_by_category(1, start, end)
    assert "salary" not in result


def test_sum_expenses_by_category_empty(db):
    repo = TransactionRepository(db)
    start = datetime.now(timezone.utc) - timedelta(days=7)
    end = datetime.now(timezone.utc)
    result = repo.sum_expenses_by_category(1, start, end)
    assert result == {}


def test_sum_expenses_per_day_basic(db):
    _tx(db, 1, "food", 300, days_ago=1)
    _tx(db, 1, "food", 200, days_ago=1)
    _tx(db, 1, "transport", 100, days_ago=2)

    repo = TransactionRepository(db)
    start = datetime.now(timezone.utc) - timedelta(days=7)
    end = datetime.now(timezone.utc)
    result = repo.sum_expenses_per_day(1, start, end)

    day_1 = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    assert result[day_1] == Decimal("500")


def test_sum_expenses_per_day_empty(db):
    repo = TransactionRepository(db)
    start = datetime.now(timezone.utc) - timedelta(days=7)
    end = datetime.now(timezone.utc)
    result = repo.sum_expenses_per_day(1, start, end)
    assert result == {}
