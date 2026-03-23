"""Tests for CategorySuggestionService — all LLM calls are mocked."""
from __future__ import annotations
import json
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy.orm import Session
from app.services.category_suggestion_service import (
    AddSynonymSuggestion, CategorySuggestionService, NewCategorySuggestion,
)
from app.services.llm_service import LLMUnavailableError


def _mock_response(content: str):
    msg = MagicMock(); msg.content = content
    choice = MagicMock(); choice.message = msg
    resp = MagicMock(); resp.choices = [choice]
    return resp


@pytest.fixture
def db():
    return MagicMock(spec=Session)


@pytest.fixture
def svc(db):
    with patch("app.services.category_suggestion_service.OpenAI"):
        s = CategorySuggestionService(db)
    return s


def test_returns_add_synonym_suggestion(svc):
    payload = json.dumps({"suggestions": [{"type": "add_synonym", "category_slug": "food", "synonym": "бургер кинг"}]})
    svc._client.chat.completions.create.return_value = _mock_response(payload)
    with patch("app.services.category_suggestion_service.TransactionRepository") as MockRepo:
        MockRepo.return_value.list_for_user.return_value = []
        results = svc.get_suggestions(123)
    assert len(results) == 1
    assert isinstance(results[0], AddSynonymSuggestion)
    assert results[0].category_slug == "food"
    assert results[0].synonym == "бургер кинг"


def test_returns_new_category_suggestion(svc):
    payload = json.dumps({"suggestions": [{"type": "new_category", "slug": "sport", "transaction_type": "expense", "synonyms": ["gym", "фитнес"]}]})
    svc._client.chat.completions.create.return_value = _mock_response(payload)
    with patch("app.services.category_suggestion_service.TransactionRepository") as MockRepo:
        MockRepo.return_value.list_for_user.return_value = []
        results = svc.get_suggestions(123)
    assert len(results) == 1
    assert isinstance(results[0], NewCategorySuggestion)
    assert results[0].slug == "sport"
    assert results[0].synonyms == ["gym", "фитнес"]


def test_empty_suggestions(svc):
    payload = json.dumps({"suggestions": []})
    svc._client.chat.completions.create.return_value = _mock_response(payload)
    with patch("app.services.category_suggestion_service.TransactionRepository") as MockRepo:
        MockRepo.return_value.list_for_user.return_value = []
        results = svc.get_suggestions(123)
    assert results == []


def test_llm_error_raises(svc):
    from openai import APIError
    svc._client.chat.completions.create.side_effect = APIError(message="500", request=MagicMock(), body=None)
    with patch("app.services.category_suggestion_service.TransactionRepository") as MockRepo:
        MockRepo.return_value.list_for_user.return_value = []
        with pytest.raises(LLMUnavailableError):
            svc.get_suggestions(123)
