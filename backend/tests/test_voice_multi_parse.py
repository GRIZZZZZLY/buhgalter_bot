from pathlib import Path

from app.services.parser_service import ParserService
from app.services.transcript_postprocessor import TranscriptPostprocessor
from app.telegram.handlers import TelegramTextFlow


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
    first = flow.handle_voice(555, 991, "file-multi", "voice", str(wav_path))
    confirmed = flow.confirm_voice(first["voice_log_id"])
    summary = flow.handle_summary(telegram_user_id=555, period="month")

    assert first["action"] == "confirm_voice"
    assert "Я услышал 2 записи:" in first["message"]
    assert confirmed["action"] == "voice_confirmed"
    assert "В летопись внесены записи:" in confirmed["message"]
    assert "1. расход 2600.00₽ — Еда" in confirmed["message"]
    assert "2. расход 400.00₽ — Транспорт" in confirmed["message"]
    assert "Расход: -3000.00₽" in summary["message"]
