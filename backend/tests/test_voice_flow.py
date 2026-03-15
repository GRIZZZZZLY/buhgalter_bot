from pathlib import Path

from app.services.stt_service import STTService
from app.telegram.handlers import TelegramTextFlow


def test_voice_flow_requires_confirmation_before_save(db_session, tmp_path: Path) -> None:
    wav_path = tmp_path / "voice.wav"
    wav_path.write_bytes(b"fake wav")
    wav_path.with_suffix(".txt").write_text("расход 1200 еда", encoding="utf-8")

    flow = TelegramTextFlow(db_session)
    response = flow.handle_voice(
        telegram_user_id=555,
        telegram_message_id=777,
        file_id="abc123",
        original_text="voice message",
        wav_path=str(wav_path),
    )

    assert response["action"] == "confirm_voice"
    assert "Я услышал: расход 1200 еда. Верно?" == response["message"]

    summary = flow.handle_summary(telegram_user_id=555, period="month")
    assert "Баланс: +0.00₽" in summary["message"]


def test_voice_confirm_saves_transaction(db_session, tmp_path: Path) -> None:
    wav_path = tmp_path / "voice.wav"
    wav_path.write_bytes(b"fake wav")
    wav_path.with_suffix(".txt").write_text("доход 5000 зарплата", encoding="utf-8")

    flow = TelegramTextFlow(db_session)
    first = flow.handle_voice(555, 888, "file-1", "voice", str(wav_path))
    confirmed = flow.confirm_voice(first["voice_log_id"])
    summary = flow.handle_summary(telegram_user_id=555, period="month")

    assert confirmed["action"] == "voice_confirmed"
    assert "В летопись внесено: доход 5000.00₽ — Зарплата" in confirmed["message"]
    assert "Остаток казны за месяц: +5000.00₽" in confirmed["message"]
    assert "Баланс: +5000.00₽" in summary["message"]


def test_voice_medium_confidence_triggers_category_resolution(db_session, tmp_path: Path) -> None:
    wav_path = tmp_path / "voice.wav"
    wav_path.write_bytes(b"fake wav")
    wav_path.with_suffix(".txt").write_text("купил что-то прикольное на 1300", encoding="utf-8")

    flow = TelegramTextFlow(db_session)
    first = flow.handle_voice(555, 990, "file-3", "voice", str(wav_path))
    assert first["action"] == "clarify_category_choice"
    assert first["raw_category"] == "что-то прикольное"


def test_voice_fallback_on_bad_transcript(db_session, tmp_path: Path) -> None:
    wav_path = tmp_path / "voice.wav"
    wav_path.write_bytes(b"fake wav")
    wav_path.with_suffix(".txt").write_text("эээ", encoding="utf-8")

    flow = TelegramTextFlow(db_session)
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
