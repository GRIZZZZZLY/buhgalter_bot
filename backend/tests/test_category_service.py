import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.services.category_service import CategoryService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


USER_ID = 12345


def test_toggle_hidden_hides_category(db):
    svc = CategoryService(db)
    svc.ensure_seeded(USER_ID)
    cat = svc.toggle_hidden(USER_ID, "food")
    assert cat is not None
    assert cat.is_hidden is True


def test_toggle_hidden_shows_hidden_category(db):
    svc = CategoryService(db)
    svc.ensure_seeded(USER_ID)
    svc.toggle_hidden(USER_ID, "food")   # hide
    cat = svc.toggle_hidden(USER_ID, "food")  # show again
    assert cat is not None
    assert cat.is_hidden is False


def test_toggle_hidden_unknown_slug_returns_none(db):
    svc = CategoryService(db)
    svc.ensure_seeded(USER_ID)
    result = svc.toggle_hidden(USER_ID, "nonexistent_slug_xyz")
    assert result is None


def test_get_visible_for_type_excludes_hidden(db):
    svc = CategoryService(db)
    svc.ensure_seeded(USER_ID)
    svc.toggle_hidden(USER_ID, "food")
    visible = svc.get_visible_for_type(USER_ID, "expense")
    slugs = [c.slug for c in visible]
    assert "food" not in slugs
    assert "transport" in slugs


def test_get_visible_for_type_includes_both(db):
    svc = CategoryService(db)
    svc.ensure_seeded(USER_ID)
    visible = svc.get_visible_for_type(USER_ID, "expense")
    slugs = [c.slug for c in visible]
    assert "other" in slugs  # type="both" should be included


def test_get_visible_for_type_income_excludes_expenses(db):
    svc = CategoryService(db)
    svc.ensure_seeded(USER_ID)
    visible = svc.get_visible_for_type(USER_ID, "income")
    types = {c.type for c in visible}
    slugs = [c.slug for c in visible]
    assert "expense" not in types
    assert len(visible) > 0
    assert "salary" in slugs  # sanity check that income categories are present


def test_toggle_hidden_seeds_automatically(db):
    """toggle_hidden must seed built-ins automatically if not yet seeded."""
    svc = CategoryService(db)
    # Do NOT call ensure_seeded first
    cat = svc.toggle_hidden(USER_ID, "food")
    assert cat is not None
    assert cat.is_hidden is True
