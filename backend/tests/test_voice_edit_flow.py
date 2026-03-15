from pathlib import Path

from app.telegram.handlers import TelegramTextFlow


def test_voice_edit_flow_reuses_next_text_as_edit(db_session, tmp_path: Path) -> None:
    wav_path = tmp_path / "voice.wav"
    wav_path.write_bytes(b"fake wav")
    wav_path.with_suffix(".txt").write_text("купил самокат 700", encoding="utf-8")

    flow = TelegramTextFlow(db_session)
    first = flow.handle_voice(555, 1001, "file-edit", "voice", str(wav_path))
    edit_prompt = flow.start_voice_edit(first["voice_log_id"])
    edited = flow.handle_text(555, "купил продукты в самокате на 700")
    confirmed = flow.confirm_voice(first["voice_log_id"])

    assert first["action"] == "confirm_voice"
    assert edit_prompt["action"] == "voice_edit_required"
    assert "Исправь текст и отправь его следующим сообщением" in edit_prompt["message"]
    assert edited["action"] == "confirm_voice"
    assert "Я услышал:" in edited["message"]
    assert confirmed["action"] == "voice_confirmed"
    assert "Еда" in confirmed["message"]
