import pytest
from app.services.category_service import CategoryService, _to_slug, _is_emoji

TG_USER = 999


# --- Unit: _to_slug ---

def test_to_slug_russian():
    assert _to_slug("Спорт") == "sport"

def test_to_slug_spaces_become_underscores():
    assert _to_slug("Бытовая химия") == "bytovaya_khimiya"

def test_to_slug_strips_special_chars():
    assert _to_slug("Café!") == "caf"

def test_to_slug_max_50():
    assert len(_to_slug("а" * 100)) <= 50


# --- Unit: _is_emoji ---

def test_is_emoji_true():
    assert _is_emoji("🏋") is True

def test_is_emoji_false_plain_text():
    assert _is_emoji("abc") is False

def test_is_emoji_bullet():
    assert _is_emoji("•") is False


# --- Service: ensure_seeded ---

def test_ensure_seeded_idempotent(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    svc.ensure_seeded(TG_USER)
    groups = svc.list_categories(TG_USER)
    food_list = [c for c in groups["expense"] if c.slug == "food"]
    assert len(food_list) == 1


def test_ensure_seeded_creates_system_categories(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    groups = svc.list_categories(TG_USER)
    slugs = {c.slug for cats in groups.values() for c in cats}
    assert "food" in slugs
    assert "salary" in slugs
    assert "other" in slugs


# --- Service: add_custom ---

def test_add_custom_creates_category(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    cat = svc.add_custom(TG_USER, "Спорт", "🏋", "expense")
    assert cat.slug == "sport"
    assert cat.is_custom is True
    assert cat.type == "expense"


def test_add_custom_slug_collision_gets_suffix(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    svc.add_custom(TG_USER, "Спорт", "🏋", "expense")
    cat2 = svc.add_custom(TG_USER, "Спорт", "⚽", "expense")
    assert cat2.slug == "sport_2"


def test_add_custom_invalid_emoji_raises(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    with pytest.raises(ValueError, match="emoji"):
        svc.add_custom(TG_USER, "Спорт", "abc", "expense")


def test_add_custom_invalid_type_raises(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    with pytest.raises(ValueError, match="тип"):
        svc.add_custom(TG_USER, "Спорт", "🏋", "unknown")


# --- Service: rename ---

def test_rename_system_category(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    cat = svc.rename(TG_USER, "food", "Питание")
    assert cat is not None
    assert cat.name_ru == "Питание"
    assert cat.slug == "food"


def test_rename_nonexistent_returns_none(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    result = svc.rename(TG_USER, "nonexistent", "Что-то")
    assert result is None


# --- Service: change_emoji ---

def test_change_emoji_success(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    cat = svc.change_emoji(TG_USER, "food", "🥗")
    assert cat is not None
    assert cat.emoji == "🥗"


def test_change_emoji_invalid_raises(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    with pytest.raises(ValueError):
        svc.change_emoji(TG_USER, "food", "xyz")


# --- Service: count_transactions ---

def test_count_transactions_zero(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    assert svc.count_transactions(TG_USER, "food") == 0


# --- Service: delete_custom ---

def test_delete_custom_no_transactions(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    cat = svc.add_custom(TG_USER, "Спорт", "🏋", "expense")
    svc.delete_custom(TG_USER, cat.slug, "other")
    assert svc._repo.get_by_slug(TG_USER, cat.slug) is None


def test_delete_system_category_raises(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    with pytest.raises(ValueError):
        svc.delete_custom(TG_USER, "food", "other")
