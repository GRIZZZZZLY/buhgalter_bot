from app.services.parser_service import ParserService
from app.services.transaction_service import TransactionService
from app.telegram.handlers import TelegramTextFlow
from app.schemas.transaction import TransactionUpdateRequest


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
    flow = TelegramTextFlow(db_session)

    save_response = flow.handle_text(telegram_user_id=555, text="доход 3000 аванс")
    summary_response = flow.handle_summary(telegram_user_id=555, period="month")

    assert save_response["action"] == "saved"
    assert "В летопись внесено: доход 3000.00₽ — Зарплата" in save_response["message"]
    assert "Остаток казны за месяц: +3000.00₽" in save_response["message"]
    assert summary_response["action"] == "summary"
    assert "Баланс: +3000.00₽" in summary_response["message"]
    assert "Доход: +3000.00₽" in summary_response["message"]
