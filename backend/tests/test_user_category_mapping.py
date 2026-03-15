"""Tests for UserCategoryMappingRepository — learned categorization."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.user import User  # noqa: F401
from app.models.transaction import Transaction  # noqa: F401
from app.models.voice_log import VoiceLog  # noqa: F401
from app.models.user_category_mapping import UserCategoryMapping  # noqa: F401
from app.repositories.user_category_mapping_repository import UserCategoryMappingRepository


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


USER_ID = 12345


class TestUpsert:
    def test_creates_new_mapping(self, db: Session) -> None:
        repo = UserCategoryMappingRepository(db)
        mapping = repo.upsert(USER_ID, "старбакс", "food")
        db.commit()

        assert mapping.merchant_text == "старбакс"
        assert mapping.category == "food"
        assert mapping.usage_count == 1

    def test_increments_usage_count(self, db: Session) -> None:
        repo = UserCategoryMappingRepository(db)
        repo.upsert(USER_ID, "старбакс", "food")
        repo.upsert(USER_ID, "старбакс", "food")
        mapping = repo.upsert(USER_ID, "старбакс", "food")
        db.commit()

        assert mapping.usage_count == 3

    def test_updates_category_on_change(self, db: Session) -> None:
        repo = UserCategoryMappingRepository(db)
        repo.upsert(USER_ID, "старбакс", "food")
        mapping = repo.upsert(USER_ID, "старбакс", "entertainment")
        db.commit()

        assert mapping.category == "entertainment"
        assert mapping.usage_count == 2


class TestFind:
    def test_finds_existing(self, db: Session) -> None:
        repo = UserCategoryMappingRepository(db)
        repo.upsert(USER_ID, "пятёрочка", "food")
        db.commit()

        found = repo.find(USER_ID, "пятёрочка")
        assert found is not None
        assert found.category == "food"

    def test_returns_none_for_missing(self, db: Session) -> None:
        repo = UserCategoryMappingRepository(db)
        found = repo.find(USER_ID, "несуществующий")
        assert found is None

    def test_different_users_independent(self, db: Session) -> None:
        repo = UserCategoryMappingRepository(db)
        repo.upsert(USER_ID, "старбакс", "food")
        repo.upsert(99999, "старбакс", "entertainment")
        db.commit()

        m1 = repo.find(USER_ID, "старбакс")
        m2 = repo.find(99999, "старбакс")
        assert m1.category == "food"
        assert m2.category == "entertainment"


class TestConfidence:
    def test_not_confident_below_threshold(self, db: Session) -> None:
        repo = UserCategoryMappingRepository(db)
        mapping = repo.upsert(USER_ID, "старбакс", "food")
        db.commit()

        assert repo.is_confident(mapping) is False  # usage_count=1, threshold=3

    def test_confident_at_threshold(self, db: Session) -> None:
        repo = UserCategoryMappingRepository(db)
        repo.upsert(USER_ID, "старбакс", "food")
        repo.upsert(USER_ID, "старбакс", "food")
        mapping = repo.upsert(USER_ID, "старбакс", "food")
        db.commit()

        assert repo.is_confident(mapping) is True  # usage_count=3


class TestTopCategories:
    def test_returns_top_by_usage(self, db: Session) -> None:
        repo = UserCategoryMappingRepository(db)
        # food: 5 uses, transport: 3 uses, entertainment: 1 use
        for _ in range(5):
            repo.upsert(USER_ID, "пятёрочка", "food")
        for _ in range(3):
            repo.upsert(USER_ID, "яндекс такси", "transport")
        repo.upsert(USER_ID, "кино", "entertainment")
        db.commit()

        top = repo.get_top_categories(USER_ID, limit=2)
        assert top == ["food", "transport"]
