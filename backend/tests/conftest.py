from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.transaction import Transaction  # noqa: F401
from app.models.voice_log import VoiceLog  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.user_category_mapping import UserCategoryMapping  # noqa: F401
from app.models.category_budget import CategoryBudget  # noqa: F401
from app.models.recurring_transaction import RecurringTransaction  # noqa: F401
from app.models.planned_expense import PlannedExpense  # noqa: F401
from app.models.user_category import UserCategory  # noqa: F401
from app.telegram.handlers import _pending_store


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Test client in dev mode: no bot token → X-Telegram-User-Id is accepted."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_settings() -> Settings:
        # Empty bot token → dev mode, plain user id header accepted
        return Settings(telegram_bot_token="", database_url="sqlite://")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = override_get_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clear_telegram_pending_state() -> Generator[None, None, None]:
    _pending_store.clear()
    try:
        yield
    finally:
        _pending_store.clear()
