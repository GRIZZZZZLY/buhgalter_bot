from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from app.services.llm_service import LLMParsedItem, LLMTransactionResult
from app.schemas.parser import ParseResult
from app.services.parser_service import ParserService
from app.services.transcript_postprocessor import TranscriptPostprocessor
from app.telegram.handlers import TelegramTextFlow


def _make_llm_result(items: list[LLMParsedItem]) -> LLMTransactionResult:
    return LLMTransactionResult(intent="transaction", items=items)


def _make_item(tx_type: str, amount: Decimal, category: str) -> LLMParsedItem:
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
    return LLMParsedItem(parsed=parsed, override_date=None)


def test_parser_parse_many_two_expenses() -> None:
    parser = ParserService()

    result = parser.parse_many("сегодня купили продуктов в пятерке на 2600 и потратили на такси 400")

    assert len(result.items) == 2
    assert result.items[0].amount is not None
    assert result.items[1].amount is not None
    assert str(result.items[0].amount) == "2600"
    assert str(result.items[1].amount) == "400"


def test_postprocessor_compacts_spaced_amounts() -> None:
    processor = TranscriptPostprocessor()

    result = processor.normalize("потратила на реснички 2 300 рублей")

    assert result == "потратила на реснички 2300 рублей"


def test_parser_parse_many_skips_zero_income_and_keeps_expense() -> None:
    parser = ParserService()
    processor = TranscriptPostprocessor()
    normalized = processor.normalize("я заработала сегодня 0 рублей, потратила на реснички 2 300 рублей")

    result = parser.parse_many(normalized)

    assert len(result.items) == 1
    assert result.items[0].amount is not None
    assert str(result.items[0].amount) == "2300"


def test_voice_confirm_saves_multiple_transactions(db_session, tmp_path: Path) -> None:
    wav_path = tmp_path / "voice.wav"
    wav_path.write_bytes(b"fake wav")
    wav_path.with_suffix(".txt").write_text(
        "сегодня купили продуктов в пятерке на 2600 и потратили на такси 400 рублей",
        encoding="utf-8",
    )

    flow = TelegramTextFlow(db_session)
    multi_result = _make_llm_result([
        _make_item("expense", Decimal("2600"), "food"),
        _make_item("expense", Decimal("400"), "transport"),
    ])

    with patch.object(flow.voice_flow_service.llm_service, "process", return_value=multi_result):
        first = flow.handle_voice(555, 991, "file-multi", "voice", str(wav_path))
        confirmed = flow.confirm_voice(first["voice_log_id"])

    summary = flow.handle_summary(telegram_user_id=555, period="month")

    assert first["action"] == "confirm_voice"
    assert "2" in first["message"]
    assert "Верно?" in first["message"]
    assert confirmed["action"] == "voice_confirmed"
    assert "2600.00" in confirmed["message"]
    assert "400.00" in confirmed["message"]
    assert "3000.00" in summary["message"]
