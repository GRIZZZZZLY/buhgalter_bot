def test_healthcheck(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_summary_endpoint_returns_data_for_user(client) -> None:
    headers = {"X-Telegram-User-Id": "123"}

    response = client.get("/api/summary?period=month", headers=headers)

    assert response.status_code == 200
    assert response.json()["period"] == "month"
    assert response.json()["balance"] == "0.00"


def test_transactions_endpoint_requires_header(client) -> None:
    response = client.get("/api/transactions?limit=20&offset=0&period=month")
    assert response.status_code == 401


def test_update_transaction_endpoint(client, db_session) -> None:
    from app.services.parser_service import ParserService
    from app.services.transaction_service import TransactionService

    parser = ParserService()
    parsed = parser.parse("расход 500 еда")
    service = TransactionService(db_session)
    item = service.create_from_parse(telegram_user_id=123, source="text", parsed=parsed)

    response = client.put(
        f"/api/transactions/{item.id}",
        headers={"X-Telegram-User-Id": "123"},
        json={"amount": "900.00", "category": "transport", "description": "Такси"},
    )

    assert response.status_code == 200
    assert response.json()["amount"] == "900.00"
    assert response.json()["category"] == "transport"
    assert response.json()["description"] == "Такси"


def test_delete_user_data_returns_204(client) -> None:
    headers = {"X-Telegram-User-Id": "123"}
    response = client.delete("/api/user/data", headers=headers)
    assert response.status_code == 204
