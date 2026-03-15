from app.telegram.bot_service import TelegramBotService


def seed_transactions(service: TelegramBotService, telegram_user_id: int) -> None:
    service.process_text_message(telegram_user_id, "расход 500 еда")
    service.process_text_message(telegram_user_id, "доход 1000 зарплата")


def test_delete_command_returns_recent_items(db_session) -> None:
    service = TelegramBotService(db_session)
    seed_transactions(service, 555)

    response = service.process_delete_command(555)

    assert response["action"] == "delete_select"
    assert len(response["items"]) == 2


def test_delete_transaction_removes_item(db_session) -> None:
    service = TelegramBotService(db_session)
    seed_transactions(service, 555)
    response = service.process_delete_command(555)
    transaction_id = response["items"][0]["id"]

    deleted = service.delete_transaction(555, transaction_id)
    after = service.process_delete_command(555)

    assert deleted["action"] == "delete_done"
    assert len(after["items"]) == 1


def test_delete_all_transactions(db_session) -> None:
    service = TelegramBotService(db_session)
    seed_transactions(service, 555)

    confirm = service.process_delete_all_command(555)
    deleted = service.delete_all_transactions(555)
    after = service.process_delete_command(555)

    assert confirm["action"] == "deleteall_confirm"
    assert deleted["action"] == "deleteall_done"
    assert after["action"] == "delete_empty"
