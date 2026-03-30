from decimal import Decimal

from app.services.parser_service import ParserService
from app.services.transaction_service import TransactionService
from app.telegram.handlers import TelegramTextFlow
from app.schemas.transaction import TransactionUpdateRequest


def test_income_triggers_savings_auto_deduction(db_session) -> None:
    """Creating an income transaction must auto-deposit into savings goals."""
    from app.schemas.parser import ParseResult
    from app.services.savings_goal_service import SavingsGoalService

    goal_service = SavingsGoalService(db_session)
    goal_service.create(
        user_id=555, title="Отпуск", target_amount=Decimal("50000"), auto_percent=10
    )

    tx_service = TransactionService(db_session)
    tx_service.create_from_parse(
        telegram_user_id=555,
        source="text",
        parsed=ParseResult(
            matched=True, confidence=0.95, confidence_label="high",
            transaction_type="income", amount=Decimal("30000"),
            category="salary", description=None, pattern="test", raw_input="зп 30000",
        ),
    )

    updated_goals = goal_service.list_active(user_id=555)
    assert updated_goals[0].current_amount == Decimal("3000.00")


def test_create_transaction_and_summary(db_session) -> None:
    parser = ParserService()
    parsed = parser.parse("расход 500 еда")
    service = TransactionService(db_session)

    item = service.create_from_parse(telegram_user_id=555, source="text", parsed=parsed)
    summary = service.get_summary(telegram_user_id=555, period="month")

    assert item.category == "food"
    assert item.amount == "500.00"
    assert summary.expense_total == "500.00"
    assert summary.balance == "-500.00"
    assert summary.top_expense_categories[0].category == "food"


def test_update_transaction(db_session) -> None:
    parser = ParserService()
    parsed = parser.parse("расход 500 еда")
    service = TransactionService(db_session)
    item = service.create_from_parse(telegram_user_id=555, source="text", parsed=parsed)

    updated = service.update_transaction(
        telegram_user_id=555,
        transaction_id=item.id,
        payload=TransactionUpdateRequest(amount="700.00", category="transport", description="Такси"),
    )

    assert updated is not None
    assert updated.amount == "700.00"
    assert updated.category == "transport"
    assert updated.description == "Такси"


def test_telegram_text_flow_save_and_summary(db_session) -> None:
    from decimal import Decimal
    from unittest.mock import patch
    from app.services.llm_service import LLMParsedItem, LLMTransactionResult
    from app.schemas.parser import ParseResult

    flow = TelegramTextFlow(db_session)
    fake_parsed = ParseResult(
        matched=True,
        confidence=0.95,
        confidence_label="high",
        transaction_type="income",
        amount=Decimal("3000"),
        category="salary",
        description=None,
        pattern="llm",
        raw_input="доход 3000 аванс",
    )
    fake_llm_result = LLMTransactionResult(
        intent="transaction",
        items=[LLMParsedItem(parsed=fake_parsed, override_date=None)],
    )

    with patch.object(flow.llm_service, "process", return_value=fake_llm_result):
        save_response = flow.handle_text(telegram_user_id=555, text="доход 3000 аванс")
    summary_response = flow.handle_summary(telegram_user_id=555, period="month")

    assert save_response["action"] == "saved"
    assert "3000.00" in save_response["message"]
    assert "Зарплата" in save_response["message"]
    assert "Баланс за месяц" in save_response["message"]
    assert summary_response["action"] == "summary"
    assert "Баланс: +3000.00" in summary_response["message"]
    assert "Доход: +3000.00" in summary_response["message"]
