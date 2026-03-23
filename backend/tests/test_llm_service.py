"""Tests for LLMService — all OpenRouter calls are mocked."""
from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.services.llm_service import (
    LLMAdvisorResult,
    LLMService,
    LLMTransactionResult,
    LLMUnavailableError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(db=None, mock_response_content: str = "{}"):
    """Return an LLMService with a mocked OpenAI client."""
    if db is None:
        db = MagicMock()
        db.scalars.return_value.all.return_value = []

    mock_message = MagicMock()
    mock_message.content = mock_response_content
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    with patch("app.services.llm_service.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_openai_cls.return_value = mock_client
        service = LLMService(db)
        service._client = mock_client  # keep reference for assertion
    return service


def _tx_response(*items: dict) -> str:
    return json.dumps({"intent": "transaction", "items": list(items)})


def _advisor_response(answer: str) -> str:
    return json.dumps({"intent": "advisor", "answer": answer})


# ---------------------------------------------------------------------------
# Transaction parsing tests
# ---------------------------------------------------------------------------

def test_parse_simple_expense(db_session):
    content = _tx_response({"type": "expense", "amount": 200, "category": "food", "description": "кофе", "date": None})
    svc = _make_service(db_session, content)
    result = svc.process("купил кофе 200", telegram_user_id=1)

    assert isinstance(result, LLMTransactionResult)
    assert len(result.items) == 1
    item = result.items[0]
    assert item.parsed.transaction_type == "expense"
    assert item.parsed.amount == Decimal("200")
    assert item.parsed.category == "food"
    assert item.override_date is None


def test_parse_freeform(db_session):
    content = _tx_response({"type": "expense", "amount": 500, "category": "transport", "description": "такси", "date": None})
    svc = _make_service(db_session, content)
    result = svc.process("ну там рублей 500 на такси потратил примерно", telegram_user_id=1)

    assert isinstance(result, LLMTransactionResult)
    item = result.items[0]
    assert item.parsed.transaction_type == "expense"
    assert item.parsed.amount == Decimal("500")
    assert item.parsed.category == "transport"


def test_parse_multi_transaction(db_session):
    content = _tx_response(
        {"type": "expense", "amount": 80, "category": "food", "description": "хлеб", "date": None},
        {"type": "expense", "amount": 120, "category": "food", "description": "молоко", "date": None},
    )
    svc = _make_service(db_session, content)
    result = svc.process("хлеб 80 и молоко 120", telegram_user_id=1)

    assert isinstance(result, LLMTransactionResult)
    assert len(result.items) == 2
    assert result.items[0].parsed.amount == Decimal("80")
    assert result.items[1].parsed.amount == Decimal("120")


def test_parse_income(db_session):
    content = _tx_response({"type": "income", "amount": 50000, "category": "salary", "description": None, "date": None})
    svc = _make_service(db_session, content)
    result = svc.process("получил зарплату 50000", telegram_user_id=1)

    assert isinstance(result, LLMTransactionResult)
    assert result.items[0].parsed.transaction_type == "income"
    assert result.items[0].parsed.amount == Decimal("50000")


def test_parse_result_fields(db_session):
    """ParseResult mapping: matched=True, confidence=0.95, pattern='llm'."""
    content = _tx_response({"type": "expense", "amount": 300, "category": "food", "description": None, "date": None})
    svc = _make_service(db_session, content)
    result = svc.process("обед 300", telegram_user_id=1)

    p = result.items[0].parsed
    assert p.matched is True
    assert p.confidence == 0.95
    assert p.confidence_label == "high"
    assert p.pattern == "llm"
    assert p.raw_input == "обед 300"


def test_date_extraction(db_session):
    """LLM-returned date is surfaced as override_date, not stored in ParseResult."""
    content = _tx_response({"type": "expense", "amount": 300, "category": "food", "description": None, "date": "2026-03-22"})
    svc = _make_service(db_session, content)
    result = svc.process("вчера потратил 300 на еду", telegram_user_id=1)

    item = result.items[0]
    assert item.override_date is not None
    assert str(item.override_date) == "2026-03-22"


def test_unknown_category_falls_back_to_other(db_session):
    """If LLM returns a category not in categories.yaml, use 'other'."""
    content = _tx_response({"type": "expense", "amount": 100, "category": "nonexistent_slug", "description": None, "date": None})
    svc = _make_service(db_session, content)
    result = svc.process("что-то купил за 100", telegram_user_id=1)

    assert result.items[0].parsed.category == "other"


# ---------------------------------------------------------------------------
# Advisor tests
# ---------------------------------------------------------------------------

def test_advisor_question(db_session):
    content = _advisor_response("В этом месяце ты потратил 3 200 ₽ на еду.")
    svc = _make_service(db_session, content)
    result = svc.process("сколько я потратил на еду?", telegram_user_id=1)

    assert isinstance(result, LLMAdvisorResult)
    assert result.intent == "advisor"
    assert len(result.answer) > 0


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

def test_invalid_json_raises(db_session):
    svc = _make_service(db_session, "this is not json at all")
    with pytest.raises(LLMUnavailableError):
        svc.process("купил что-то", telegram_user_id=1)


def test_unknown_intent_raises(db_session):
    svc = _make_service(db_session, json.dumps({"intent": "unknown"}))
    with pytest.raises(LLMUnavailableError):
        svc.process("...", telegram_user_id=1)


def test_empty_items_raises(db_session):
    svc = _make_service(db_session, json.dumps({"intent": "transaction", "items": []}))
    with pytest.raises(LLMUnavailableError):
        svc.process("купил что-то", telegram_user_id=1)


def test_http_error_raises(db_session):
    from openai import APIError

    db = MagicMock()
    db.scalars.return_value.all.return_value = []

    with patch("app.services.llm_service.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = APIError(
            message="500 Internal Server Error", request=MagicMock(), body=None
        )
        mock_openai_cls.return_value = mock_client
        svc = LLMService(db)
        svc._client = mock_client

    with pytest.raises(LLMUnavailableError):
        svc.process("купил что-то", telegram_user_id=1)
