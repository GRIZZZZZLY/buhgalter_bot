from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from openai import APIError

from app.models.category_budget import CategoryBudget
from app.models.planned_expense import PlannedExpense
from app.repositories.user_repository import UserRepository
from app.services.financial_qa_service import FinancialQAService


def _seed_user(db, uid: int = 555):
    return UserRepository(db).get_or_create(uid)


def test_financial_qa_fallback_for_budget_question_is_useful(db_session) -> None:
    _seed_user(db_session)
    db_session.add(CategoryBudget(telegram_user_id=555, category="food", amount=1000))
    db_session.commit()

    service = FinancialQAService(db_session)

    with patch.object(
        service._client.chat.completions,
        "create",
        side_effect=APIError("timeout", request=MagicMock(), body=None),
    ):
        result = service.answer("Где я вылезаю из бюджета?", telegram_user_id=555)

    assert "бюджет" in result.lower() or "перерасход" in result.lower()


def test_financial_qa_fallback_for_upcoming_question_is_useful(db_session) -> None:
    _seed_user(db_session)
    db_session.add(
        PlannedExpense(
            telegram_user_id=555,
            title="Налог",
            amount=Decimal("4200"),
            category="fees",
            planned_date=date(2026, 4, 10),
        )
    )
    db_session.commit()

    service = FinancialQAService(db_session)

    with patch.object(
        service._client.chat.completions,
        "create",
        side_effect=APIError("timeout", request=MagicMock(), body=None),
    ):
        result = service.answer("Какие платежи у меня скоро?", telegram_user_id=555)

    assert "Налог" in result or "платеж" in result.lower() or "расход" in result.lower()
