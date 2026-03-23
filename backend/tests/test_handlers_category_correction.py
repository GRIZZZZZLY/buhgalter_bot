from __future__ import annotations
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest
from sqlalchemy.orm import Session
from app.telegram.bot_service import TelegramBotService

@pytest.fixture
def db():
    return MagicMock(spec=Session)

@pytest.fixture
def svc(db):
    return TelegramBotService(db)

def _mock_tx(description="кофе старбакс", category="food"):
    tx = MagicMock(); tx.description = description; tx.category = category
    return tx

def test_correction_updates_transaction(svc):
    tx_id = str(uuid4())
    with patch.object(svc.transaction_service, "update_category", return_value=_mock_tx()) as mock_update:
        result = svc.handle_category_correction(123, tx_id, "transport")
    mock_update.assert_called_once_with(123, tx_id, "transport")
    assert result["message"]

def test_correction_adds_synonym_to_yaml(svc):
    tx_id = str(uuid4())
    tx = _mock_tx(description="бургер кинг 500", category="food")
    with patch.object(svc.transaction_service, "update_category", return_value=tx):
        with patch("app.telegram.bot_service.YamlLearnerService") as MockLearner:
            svc.handle_category_correction(123, tx_id, "food")
    MockLearner.return_value.add_synonym.assert_called_once_with("food", "бургер")

def test_correction_skips_yaml_on_empty_description(svc):
    tx_id = str(uuid4())
    tx = _mock_tx(description="", category="food")
    with patch.object(svc.transaction_service, "update_category", return_value=tx):
        with patch("app.telegram.bot_service.YamlLearnerService") as MockLearner:
            svc.handle_category_correction(123, tx_id, "food")
    MockLearner.return_value.add_synonym.assert_not_called()

def test_correction_skips_yaml_on_stopword(svc):
    tx_id = str(uuid4())
    tx = _mock_tx(description="оплата услуг", category="housing")
    with patch.object(svc.transaction_service, "update_category", return_value=tx):
        with patch("app.telegram.bot_service.YamlLearnerService") as MockLearner:
            svc.handle_category_correction(123, tx_id, "housing")
    MockLearner.return_value.add_synonym.assert_not_called()
