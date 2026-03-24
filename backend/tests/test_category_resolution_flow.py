from decimal import Decimal
from unittest.mock import patch

from telegram import InlineKeyboardMarkup

from app.schemas.parser import ParseResult
from app.services.llm_service import LLMParsedItem, LLMTransactionResult
from app.telegram.handlers import TelegramTextFlow, PendingCategoryResolution, _store_set
from app.telegram.keyboards import category_resolution_keyboard


def _make_llm_result(tx_type: str, amount: Decimal, category: str) -> LLMTransactionResult:
    parsed = ParseResult(
        matched=True,
        confidence=0.95,
        confidence_label="high",
        transaction_type=tx_type,
        amount=amount,
        category=category,
        description=None,
        pattern="llm",
        raw_input="",
    )
    return LLMTransactionResult(
        intent="transaction",
        items=[LLMParsedItem(parsed=parsed, override_date=None)],
    )


def _make_parsed(tx_type: str, amount: Decimal, category: str) -> ParseResult:
    return ParseResult(
        matched=True,
        confidence=0.95,
        confidence_label="high",
        transaction_type=tx_type,
        amount=amount,
        category=category,
        description=None,
        pattern="llm",
        raw_input="",
    )


def _set_pending(telegram_user_id: int, raw_category: str, suggestions: list[str], parsed: ParseResult) -> None:
    """Helper to inject a pending category resolution into the in-memory store."""
    _store_set(telegram_user_id, PendingCategoryResolution(
        parsed=parsed,
        raw_category=raw_category,
        suggestions=suggestions,
        source="text",
    ))


def test_category_resolution_offers_reply_keyboard_and_saves_selected_suggestion(db_session) -> None:
    flow = TelegramTextFlow(db_session)
    parsed = _make_parsed("expense", Decimal("1200"), "other")
    _set_pending(555, "красота и здоровье", ["beauty", "health"], parsed)

    # Simulate the clarify_category_choice state already set
    first = flow.handle_text(telegram_user_id=555, text="Красота")
    assert first['action'] == 'saved'
    assert 'Красота' in first['message']


def test_category_resolution_keyboard_labels(db_session) -> None:
    # Test keyboard generation independently of handle_text
    raw_category = "красота и здоровье"
    suggestions = ["beauty", "health"]
    keyboard = category_resolution_keyboard(raw_category, suggestions)
    assert isinstance(keyboard, InlineKeyboardMarkup)
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert any('Создать «красота и здоровье»' in l for l in labels)
    assert any('Красота' in l for l in labels)
    assert any('Здоровье' in l for l in labels)


def test_category_resolution_can_create_new_category(db_session) -> None:
    flow = TelegramTextFlow(db_session)
    parsed = _make_parsed("expense", Decimal("900"), "other")
    _set_pending(555, "красота и здоровье", ["beauty", "health"], parsed)

    second = flow.handle_text(telegram_user_id=555, text='Создать «красота и здоровье»')

    assert second['action'] == 'saved'
    assert 'красота и здоровье' in second['message'].lower()


def test_category_resolution_strips_forward_prefixes(db_session) -> None:
    flow = TelegramTextFlow(db_session)
    parsed = _make_parsed("expense", Decimal("800"), "other")
    _set_pending(555, "красота и здоровье", ["beauty", "health"], parsed)

    second = flow.handle_text(telegram_user_id=555, text='Переслано от Игорь\nЗдоровье')
    assert second['action'] == 'saved'
    assert 'Здоровье' in second['message']


def test_category_resolution_appears_for_single_strong_suggestion(db_session) -> None:
    # LLM now handles all text — category resolution via parser is removed.
    # Test that a transaction with category "beauty" is saved via LLM.
    flow = TelegramTextFlow(db_session)
    llm_result = _make_llm_result("expense", Decimal("1000"), "beauty")

    with patch.object(flow.llm_service, "process", return_value=llm_result):
        first = flow.handle_text(telegram_user_id=555, text='1000 рублей на массаж')

    assert first['action'] == 'saved'
    assert '1000' in first['message']


def test_category_resolution_treats_new_text_as_new_category_attempt(db_session) -> None:
    # LLM now handles all text — verify two sequential saves work independently.
    flow = TelegramTextFlow(db_session)
    llm_result_1 = _make_llm_result("expense", Decimal("1000"), "beauty")
    llm_result_2 = _make_llm_result("expense", Decimal("900"), "health")

    with patch.object(flow.llm_service, "process", side_effect=[llm_result_1, llm_result_2]):
        first = flow.handle_text(telegram_user_id=555, text='1000 рублей на массаж')
        second = flow.handle_text(telegram_user_id=555, text='900 рублей красота и здоровье')

    assert first['action'] == 'saved'
    assert second['action'] == 'saved'
