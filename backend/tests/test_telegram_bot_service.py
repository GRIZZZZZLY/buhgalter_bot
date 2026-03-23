from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.schemas.parser import ParseResult
from app.schemas.telegram import TelegramVoicePayload
from app.services.llm_service import LLMParsedItem, LLMTransactionResult
from app.telegram.bot_service import TelegramBotService


class FakeAudioService:
    def __init__(self, wav_path: str, fail: bool = False) -> None:
        self.wav_path = wav_path
        self.fail = fail

    def temp_copy(self, source_path: str, extension: str) -> str:
        assert source_path
        assert extension == ".ogg"
        return source_path

    def prepare_wav_from_ogg(self, source_path: str, suffix: str | None = None) -> str:
        assert source_path
        _ = suffix
        if self.fail:
            raise RuntimeError("conversion exploded")
        return self.wav_path

    @staticmethod
    def cleanup_audio_files(*paths: str) -> None:
        pass  # no-op in tests


def test_bot_service_processes_text_message(db_session) -> None:
    fake_parsed = ParseResult(
        matched=True,
        confidence=0.95,
        confidence_label="high",
        transaction_type="expense",
        amount=Decimal("250"),
        category="food",
        description=None,
        pattern="llm",
        raw_input="расход 250 еда",
    )
    fake_llm_result = LLMTransactionResult(
        intent="transaction",
        items=[LLMParsedItem(parsed=fake_parsed, override_date=None)],
    )

    service = TelegramBotService(db_session)
    with patch.object(service.flow.llm_service, "process", return_value=fake_llm_result):
        response = service.process_text_message(telegram_user_id=555, text="расход 250 еда")

    assert response["action"] == "saved"
    assert "250.00" in response["message"]
    assert "Еда" in response["message"]


def test_bot_service_processes_voice_message(db_session, tmp_path: Path) -> None:
    wav_path = tmp_path / "voice.wav"
    wav_path.write_bytes(b"wav")
    wav_path.with_suffix(".txt").write_text("расход 300 транспорт", encoding="utf-8")
    ogg_path = tmp_path / "voice.ogg"
    ogg_path.write_bytes(b"ogg")

    service = TelegramBotService(db_session, audio_service=FakeAudioService(str(wav_path)))
    response, debug = service.process_voice_message(
        TelegramVoicePayload(
            telegram_user_id=555,
            telegram_message_id=101,
            file_id="file-voice",
            original_file_path=str(ogg_path),
        )
    )

    assert response["action"] == "confirm_voice"
    assert debug.converted is True
    assert debug.wav_path == str(wav_path)


def test_bot_service_handles_voice_conversion_failure(db_session, tmp_path: Path) -> None:
    ogg_path = tmp_path / "voice.ogg"
    ogg_path.write_bytes(b"ogg")

    service = TelegramBotService(db_session, audio_service=FakeAudioService(str(tmp_path / "missing.wav"), fail=True))
    response, debug = service.process_voice_message(
        TelegramVoicePayload(
            telegram_user_id=555,
            telegram_message_id=101,
            file_id="file-voice",
            original_file_path=str(ogg_path),
        )
    )

    assert response["action"] == "voice_fallback"
    assert "conversion exploded" in response["message"]
    assert debug.converted is False
