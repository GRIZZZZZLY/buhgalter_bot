from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.llm_service import LLMParsedItem, LLMTransactionResult
from app.schemas.parser import ParseResult
from app.services.stt_service import STTService
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


def test_voice_flow_requires_confirmation_before_save(db_session, tmp_path: Path) -> None:
    wav_path = tmp_path / "voice.wav"
    wav_path.write_bytes(b"fake wav")
    wav_path.with_suffix(".txt").write_text("расход 1200 еда", encoding="utf-8")

    flow = TelegramTextFlow(db_session)
    llm_result = _make_llm_result([_make_item("expense", Decimal("1200"), "food")])
    with patch.object(flow.voice_flow_service.llm_service, "process", return_value=llm_result):
        response = flow.handle_voice(
            telegram_user_id=555,
            telegram_message_id=777,
            file_id="abc123",
            original_text="voice message",
            wav_path=str(wav_path),
        )

    assert response["action"] == "confirm_voice"
    assert "1200.00" in response["message"]
    assert "Верно?" in response["message"]

    summary = flow.handle_summary(telegram_user_id=555, period="month")
    assert "Баланс: +0.00" in summary["message"]


def test_voice_confirm_saves_transaction(db_session, tmp_path: Path) -> None:
    wav_path = tmp_path / "voice.wav"
    wav_path.write_bytes(b"fake wav")
    wav_path.with_suffix(".txt").write_text("доход 5000 зарплата", encoding="utf-8")

    flow = TelegramTextFlow(db_session)
    llm_result = _make_llm_result([_make_item("income", Decimal("5000"), "salary")])
    with patch.object(flow.voice_flow_service.llm_service, "process", return_value=llm_result):
        first = flow.handle_voice(555, 888, "file-1", "voice", str(wav_path))
        confirmed = flow.confirm_voice(first["voice_log_id"])

    summary = flow.handle_summary(telegram_user_id=555, period="month")

    assert confirmed["action"] == "voice_confirmed"
    assert "5000.00" in confirmed["message"]
    assert "Баланс за месяц" in confirmed["message"]
    assert "Баланс: +5000.00" in summary["message"]


def test_voice_fallback_on_bad_transcript(db_session, tmp_path: Path) -> None:
    wav_path = tmp_path / "voice.wav"
    wav_path.write_bytes(b"fake wav")
    wav_path.with_suffix(".txt").write_text("эээ", encoding="utf-8")

    from app.services.llm_service import LLMUnavailableError

    flow = TelegramTextFlow(db_session)
    with patch.object(
        flow.voice_flow_service.llm_service, "process", side_effect=LLMUnavailableError("no")
    ):
        response = flow.handle_voice(555, 999, "file-2", "voice", str(wav_path))

    assert response["action"] == "voice_fallback"
    assert "Не удалось распознать" in response["message"]


def test_stt_stub_reads_sidecar(tmp_path: Path) -> None:
    wav_path = tmp_path / "sample.wav"
    wav_path.write_bytes(b"wav")
    wav_path.with_suffix(".txt").write_text("расход 400 транспорт", encoding="utf-8")

    result = STTService().transcribe(str(wav_path))

    assert result.text == "расход 400 транспорт"
    assert result.needs_fallback is False
