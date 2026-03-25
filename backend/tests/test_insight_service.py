"""Tests for InsightService — LLM calls and DB queries are mocked."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.insight_service import InsightFact, InsightService


def _user(budget=None, transactions_today=0, last_insight_at=None):
    u = MagicMock(spec=User)
    u.telegram_user_id = 123
    u.timezone = "Europe/Moscow"
    u.budget_amount = budget
    u.transactions_today = transactions_today
    u.last_insight_at = last_insight_at
    return u


def _make_svc(db=None):
    db = db or MagicMock(spec=Session)
    with patch("app.services.insight_service.OpenAI"):
        svc = InsightService(db)
    return svc


def _mock_llm_response(svc, text="Инсайт!"):
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    svc._client.chat.completions.create.return_value = resp


def test_category_spike_detected():
    svc = _make_svc()
    _mock_llm_response(svc)
    user = _user()
    with patch.object(svc._repo, "sum_expenses_by_category") as mock_sum:
        mock_sum.side_effect = [
            {"food": Decimal("2000")},
            {"food": Decimal("800")},
        ]
        fact = svc._detect_category_spike(user)
    assert fact is not None
    assert fact.type == "category_spike"
    assert fact.data["category"] == "food"


def test_category_spike_below_threshold():
    svc = _make_svc()
    user = _user()
    with patch.object(svc._repo, "sum_expenses_by_category") as mock_sum:
        mock_sum.side_effect = [
            {"food": Decimal("1200")},
            {"food": Decimal("800")},
        ]
        fact = svc._detect_category_spike(user)
    assert fact is None


def test_budget_milestone_7_days():
    svc = _make_svc()
    user = _user(budget=30000.0)
    today = datetime.now(timezone.utc).date()
    per_day = {today - timedelta(days=i): Decimal("800") for i in range(7)}
    with patch.object(svc._repo, "sum_expenses_per_day", return_value=per_day):
        fact = svc._detect_budget_milestone(user)
    assert fact is not None
    assert fact.data["streak_days"] == 7


def test_budget_milestone_no_budget_set():
    svc = _make_svc()
    user = _user(budget=None)
    fact = svc._detect_budget_milestone(user)
    assert fact is None


def test_weekly_anomaly_detected():
    svc = _make_svc()
    user = _user()
    with patch.object(svc._repo, "sum_expenses_by_category") as mock_sum:
        mock_sum.side_effect = [
            {"food": Decimal("15000")},
            {"food": Decimal("40000")},
        ]
        fact = svc._detect_weekly_anomaly(user)
    assert fact is not None
    assert fact.type == "weekly_anomaly"


def test_weekly_anomaly_no_history():
    svc = _make_svc()
    user = _user()
    with patch.object(svc._repo, "sum_expenses_by_category") as mock_sum:
        mock_sum.side_effect = [{"food": Decimal("5000")}, {}]
        fact = svc._detect_weekly_anomaly(user)
    assert fact is None


def test_motivational_streak_uses_cached_counter():
    svc = _make_svc()
    user = _user(transactions_today=3)
    fact = svc._detect_motivational_streak(user)
    assert fact is not None
    assert fact.type == "motivational_streak"
    assert fact.data["count"] == 3


def test_no_transactions_returns_none():
    svc = _make_svc()
    user = _user(transactions_today=0)
    with patch.object(svc._repo, "sum_expenses_by_category", return_value={}):
        with patch.object(svc._repo, "sum_expenses_per_day", return_value={}):
            result = svc.get_scheduled_insight(user)
    assert result is None


def test_cooldown_skips_realtime():
    svc = _make_svc()
    tz = ZoneInfo("Europe/Moscow")
    today_dt = datetime.now(tz).replace(hour=10, minute=0, second=0, microsecond=0)
    user = _user(last_insight_at=today_dt)
    tx = MagicMock()
    result = svc.get_realtime_insight(user, tx)
    assert result is None


def test_cooldown_skips_scheduled():
    svc = _make_svc()
    tz = ZoneInfo("Europe/Moscow")
    today_dt = datetime.now(tz).replace(hour=9, minute=0, second=0, microsecond=0)
    user = _user(last_insight_at=today_dt)
    result = svc.get_scheduled_insight(user)
    assert result is None


def test_llm_error_returns_none():
    svc = _make_svc()
    user = _user(transactions_today=5)
    svc._client.chat.completions.create.side_effect = Exception("network error")
    result = svc.get_scheduled_insight(user)
    assert result is None
