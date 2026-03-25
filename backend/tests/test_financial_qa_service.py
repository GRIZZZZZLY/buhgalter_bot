"""Tests for FinancialQAService — Conversational Financial Intelligence."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.services.financial_qa_service import FinancialQAService


def test_financial_qa_returns_string(db_session) -> None:
    """answer() должен вернуть непустую строку."""
    service = FinancialQAService(db_session)
    fake_response = MagicMock()
    fake_response.choices[0].message.content = '{"answer": "За этот месяц ты потратил 1500₽ на еду."}'

    with patch.object(service._client.chat.completions, "create", return_value=fake_response):
        result = service.answer("сколько я потратил на еду?", telegram_user_id=555)

    assert isinstance(result, str)
    assert len(result) > 0


def test_financial_qa_includes_user_data_in_prompt(db_session) -> None:
    """Промпт должен содержать реальные финансовые данные пользователя."""
    from app.services.transaction_service import TransactionService
    from app.schemas.parser import ParseResult

    # Создаём транзакцию для пользователя
    tx_service = TransactionService(db_session)
    tx_service.create_from_parse(
        telegram_user_id=555,
        source="text",
        parsed=ParseResult(
            matched=True,
            confidence=0.95,
            confidence_label="high",
            transaction_type="expense",
            amount=Decimal("1500"),
            category="food",
            description=None,
            pattern="test",
            raw_input="тест",
        ),
    )

    service = FinancialQAService(db_session)
    captured_messages: list = []

    def fake_create(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        fake_resp = MagicMock()
        fake_resp.choices[0].message.content = '{"answer": "Ответ"}'
        return fake_resp

    with patch.object(service._client.chat.completions, "create", side_effect=fake_create):
        service.answer("сколько я потратил на еду?", telegram_user_id=555)

    full_prompt = " ".join(m["content"] for m in captured_messages)
    # Промпт должен содержать данные о расходах пользователя
    assert "1500" in full_prompt or "food" in full_prompt.lower()


def test_financial_qa_handles_llm_unavailable(db_session) -> None:
    """При недоступности LLM возвращает понятное сообщение, не падает."""
    from openai import APIError
    service = FinancialQAService(db_session)

    with patch.object(
        service._client.chat.completions,
        "create",
        side_effect=APIError("timeout", request=MagicMock(), body=None),
    ):
        result = service.answer("сколько потратил?", telegram_user_id=555)

    assert isinstance(result, str)
    assert len(result) > 0


def test_financial_qa_no_transactions_gives_helpful_answer(db_session) -> None:
    """Если транзакций нет — сервис сообщает об этом, не падает."""
    service = FinancialQAService(db_session)
    fake_response = MagicMock()
    fake_response.choices[0].message.content = '{"answer": "У тебя пока нет записанных трат."}'

    with patch.object(service._client.chat.completions, "create", return_value=fake_response):
        result = service.answer("сколько я трачу?", telegram_user_id=999)

    assert isinstance(result, str)
    assert len(result) > 0


def test_financial_qa_passes_history_to_llm(db_session) -> None:
    """answer() should include conversation history in LLM messages."""
    service = FinancialQAService(db_session)
    captured_messages: list = []

    def fake_create(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        fake_resp = MagicMock()
        fake_resp.choices[0].message.content = '{"answer": "Ответ с историей"}'
        return fake_resp

    history = [
        {"role": "user", "content": "сколько я потратил?"},
        {"role": "assistant", "content": "5000₽ за этот месяц."},
    ]

    with patch.object(service._client.chat.completions, "create", side_effect=fake_create):
        result = service.answer("а на еду?", telegram_user_id=555, history=history)

    assert result == "Ответ с историей"
    assert len(captured_messages) == 4
    assert captured_messages[0]["role"] == "system"
    assert captured_messages[1]["content"] == "сколько я потратил?"
    assert captured_messages[2]["content"] == "5000₽ за этот месяц."
    assert captured_messages[3]["content"] == "а на еду?"
