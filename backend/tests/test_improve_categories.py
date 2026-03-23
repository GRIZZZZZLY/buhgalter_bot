import pytest
from unittest.mock import MagicMock, patch
from app.services.category_suggestion_service import AddSynonymSuggestion, NewCategorySuggestion
from app.telegram.bot_service import TelegramBotService


def make_bot_service():
    db = MagicMock()
    return TelegramBotService(db)


def test_improve_categories_add_synonym():
    svc = make_bot_service()
    sugg = AddSynonymSuggestion(type="add_synonym", category_slug="food", synonym="бургер")
    with patch(
        "app.services.category_suggestion_service.CategorySuggestionService.get_suggestions",
        return_value=[sugg],
    ):
        results = svc.improve_categories(12345)
    assert len(results) == 1
    assert "бургер" in results[0]["text"]
    assert results[0]["key"].startswith("sugg:")


def test_improve_categories_new_category():
    svc = make_bot_service()
    sugg = NewCategorySuggestion(
        type="new_category", slug="sport", tx_type="expense", synonyms=["gym", "фитнес"]
    )
    with patch(
        "app.services.category_suggestion_service.CategorySuggestionService.get_suggestions",
        return_value=[sugg],
    ):
        results = svc.improve_categories(12345)
    assert len(results) == 1
    assert "sport" in results[0]["text"]


def test_improve_categories_empty():
    svc = make_bot_service()
    with patch(
        "app.services.category_suggestion_service.CategorySuggestionService.get_suggestions",
        return_value=[],
    ):
        results = svc.improve_categories(12345)
    assert results == []


def test_apply_suggestion_add_synonym():
    svc = make_bot_service()
    sugg = AddSynonymSuggestion(type="add_synonym", category_slug="food", synonym="бургер")
    with patch(
        "app.services.yaml_learner_service.YamlLearnerService.add_synonym",
        return_value=True,
    ) as mock_add:
        result = svc.apply_suggestion(sugg)
    assert result is True
    mock_add.assert_called_once_with("food", "бургер")
