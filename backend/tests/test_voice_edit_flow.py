from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from app.services.llm_service import LLMParsedItem, LLMTransactionResult
from app.schemas.parser import ParseResult
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


def test_voice_edit_flow_reuses_next_text_as_edit(db_session, tmp_path: Path) -> None:
    wav_path = tmp_path / "voice.wav"
    wav_path.write_bytes(b"fake wav")
    wav_path.with_suffix(".txt").write_text("купил самокат 700", encoding="utf-8")

    flow = TelegramTextFlow(db_session)

    # First: process voice — returns ambiguous result, user gets confirm_voice
    first_result = _make_llm_result([_make_item("expense", Decimal("700"), "other")])
    # Edit: user corrects text — maps to food
    edit_result = _make_llm_result([_make_item("expense", Decimal("700"), "food")])
    # Confirm: re-parses stored transcript (which is the edited text)
    confirm_result = _make_llm_result([_make_item("expense", Decimal("700"), "food")])

    process_mock = patch.object(flow.voice_flow_service.llm_service, "process")
    with process_mock as m:
        m.return_value = first_result
        first = flow.handle_voice(555, 1001, "file-edit", "voice", str(wav_path))

        edit_prompt = flow.start_voice_edit(first["voice_log_id"])

        m.return_value = edit_result
        edited = flow.handle_text(555, "купил продукты в самокате на 700")

        m.return_value = confirm_result
        confirmed = flow.confirm_voice(first["voice_log_id"])

    assert first["action"] == "confirm_voice"
    assert edit_prompt["action"] == "voice_edit_required"
    assert "Исправь текст" in edit_prompt["message"]
    assert edited["action"] == "confirm_voice"
    assert "700" in edited["message"]
    assert confirmed["action"] == "voice_confirmed"
    assert "Еда" in confirmed["message"]
