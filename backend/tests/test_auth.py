"""Tests for Telegram initData HMAC-SHA256 authentication."""
import hashlib
import hmac
import json
from collections.abc import Generator
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import _verify_telegram_init_data, _extract_user_id_from_parsed, get_telegram_user_id
from app.core.settings import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_BOT_TOKEN = "1234567890:test_bot_token_for_unit_tests"
TEST_USER_ID = 987654321


def _build_valid_init_data(bot_token: str, user_id: int) -> str:
    """Build a correctly signed initData string for testing."""
    user_json = json.dumps({"id": user_id, "first_name": "Test", "username": "testuser"}, separators=(",", ":"))
    fields = {
        "user": user_json,
        "auth_date": "1700000000",
        "query_id": "test_query_id",
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


# ---------------------------------------------------------------------------
# Unit tests for _verify_telegram_init_data
# ---------------------------------------------------------------------------

class TestVerifyTelegramInitData:
    def test_valid_signature_returns_parsed_fields(self) -> None:
        init_data = _build_valid_init_data(TEST_BOT_TOKEN, TEST_USER_ID)
        result = _verify_telegram_init_data(init_data, TEST_BOT_TOKEN)
        assert "user" in result
        assert "auth_date" in result
        assert "hash" not in result  # hash is popped

    def test_wrong_bot_token_raises_401(self) -> None:
        from fastapi import HTTPException
        init_data = _build_valid_init_data(TEST_BOT_TOKEN, TEST_USER_ID)
        with pytest.raises(HTTPException) as exc_info:
            _verify_telegram_init_data(init_data, "wrong_token")
        assert exc_info.value.status_code == 401
        assert "Invalid initData signature" in exc_info.value.detail

    def test_tampered_data_raises_401(self) -> None:
        from fastapi import HTTPException
        init_data = _build_valid_init_data(TEST_BOT_TOKEN, TEST_USER_ID)
        # Tamper: replace auth_date value
        tampered = init_data.replace("auth_date=1700000000", "auth_date=9999999999")
        with pytest.raises(HTTPException) as exc_info:
            _verify_telegram_init_data(tampered, TEST_BOT_TOKEN)
        assert exc_info.value.status_code == 401

    def test_missing_hash_raises_401(self) -> None:
        from fastapi import HTTPException
        # Build without hash
        fields = {"user": '{"id":1}', "auth_date": "1700000000"}
        init_data = urlencode(fields)
        with pytest.raises(HTTPException) as exc_info:
            _verify_telegram_init_data(init_data, TEST_BOT_TOKEN)
        assert exc_info.value.status_code == 401
        assert "Missing hash" in exc_info.value.detail

    def test_empty_string_raises_401(self) -> None:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_telegram_init_data("", TEST_BOT_TOKEN)
        assert exc_info.value.status_code == 401


class TestExtractUserIdFromParsed:
    def test_extracts_user_id_correctly(self) -> None:
        parsed = {"user": json.dumps({"id": TEST_USER_ID, "first_name": "Test"})}
        assert _extract_user_id_from_parsed(parsed) == TEST_USER_ID

    def test_missing_user_field_raises_401(self) -> None:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _extract_user_id_from_parsed({})
        assert exc_info.value.status_code == 401

    def test_invalid_json_raises_401(self) -> None:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _extract_user_id_from_parsed({"user": "not-json"})
        assert exc_info.value.status_code == 401

    def test_missing_id_in_user_raises_401(self) -> None:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _extract_user_id_from_parsed({"user": json.dumps({"first_name": "Test"})})
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Integration tests: API endpoints with initData auth
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session_auth() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.models.transaction import Transaction  # noqa: F401
    from app.models.voice_log import VoiceLog  # noqa: F401
    from app.models.user import User  # noqa: F401
    from app.models.user_category_mapping import UserCategoryMapping  # noqa: F401
    from app.models.category_budget import CategoryBudget  # noqa: F401
    from app.models.recurring_transaction import RecurringTransaction  # noqa: F401
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client_with_token(db_session_auth: Session) -> Generator[TestClient, None, None]:
    """TestClient that uses a real bot token — production auth mode."""
    def override_get_db():
        try:
            yield db_session_auth
        finally:
            pass

    def override_get_settings() -> Settings:
        return Settings(telegram_bot_token=TEST_BOT_TOKEN, database_url="sqlite://")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = override_get_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestApiAuthWithInitData:
    def test_no_headers_returns_401(self, client_with_token: TestClient) -> None:
        response = client_with_token.get("/api/summary?period=month")
        assert response.status_code == 401

    def test_plain_user_id_header_rejected_in_production_mode(self, client_with_token: TestClient) -> None:
        """When bot token is set, X-Telegram-User-Id alone must be rejected."""
        response = client_with_token.get(
            "/api/summary?period=month",
            headers={"X-Telegram-User-Id": "123"},
        )
        assert response.status_code == 401

    def test_invalid_init_data_returns_401(self, client_with_token: TestClient) -> None:
        response = client_with_token.get(
            "/api/summary?period=month",
            headers={"X-Telegram-Init-Data": "user=bad&hash=deadbeef"},
        )
        assert response.status_code == 401

    def test_valid_init_data_returns_200(self, client_with_token: TestClient) -> None:
        init_data = _build_valid_init_data(TEST_BOT_TOKEN, TEST_USER_ID)
        response = client_with_token.get(
            "/api/summary?period=month",
            headers={"X-Telegram-Init-Data": init_data},
        )
        assert response.status_code == 200
        assert response.json()["balance"] == "0.00"

    def test_valid_init_data_transactions_returns_200(self, client_with_token: TestClient) -> None:
        init_data = _build_valid_init_data(TEST_BOT_TOKEN, TEST_USER_ID)
        response = client_with_token.get(
            "/api/transactions?limit=10&offset=0&period=month",
            headers={"X-Telegram-Init-Data": init_data},
        )
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_wrong_signature_returns_401(self, client_with_token: TestClient) -> None:
        # Build valid data but sign with wrong token
        init_data = _build_valid_init_data("wrong_token_entirely", TEST_USER_ID)
        response = client_with_token.get(
            "/api/summary?period=month",
            headers={"X-Telegram-Init-Data": init_data},
        )
        assert response.status_code == 401


class TestApiAuthDevMode:
    """Existing dev-mode tests: no bot token → X-Telegram-User-Id is accepted."""

    def test_dev_mode_accepts_user_id_header(self, client: TestClient) -> None:
        response = client.get("/api/summary?period=month", headers={"X-Telegram-User-Id": "123"})
        assert response.status_code == 200

    def test_dev_mode_no_header_returns_401(self, client: TestClient) -> None:
        response = client.get("/api/summary?period=month")
        assert response.status_code == 401
