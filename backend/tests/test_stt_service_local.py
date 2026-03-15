from app.core.settings import get_settings
from app.services.stt_service import STTService


def test_stt_stub_provider_reads_sidecar(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STT_PROVIDER", "stub")
    get_settings.cache_clear()
    wav_path = tmp_path / "voice.wav"
    wav_path.write_bytes(b"wav")
    wav_path.with_suffix(".txt").write_text("расход 700 еда", encoding="utf-8")

    service = STTService()
    result = service.transcribe(str(wav_path))

    assert result.provider == "stub"
    assert result.text == "расход 700 еда"
    assert result.needs_fallback is False


def test_stt_unknown_provider_fails_cleanly(monkeypatch) -> None:
    monkeypatch.setenv("STT_PROVIDER", "mystery")
    get_settings.cache_clear()
    service = STTService()

    result = service.transcribe("/tmp/missing.wav")

    assert result.needs_fallback is True
    assert "unknown stt provider" in (result.failure_reason or "")


def test_faster_whisper_missing_dependency_fails_cleanly(monkeypatch) -> None:
    monkeypatch.setenv("STT_PROVIDER", "faster-whisper")
    get_settings.cache_clear()
    service = STTService()

    result = service._transcribe_faster_whisper("/tmp/missing.wav")

    assert result.provider in {"faster-whisper", "faster-whisper:stub-fallback"}
    if result.provider == "faster-whisper":
        assert result.needs_fallback is True


def test_debug_capabilities_reports_missing_binaries(monkeypatch) -> None:
    monkeypatch.setenv("STT_PROVIDER", "faster-whisper")
    monkeypatch.setenv("FFMPEG_BIN", "definitely-not-ffmpeg")
    monkeypatch.setenv("WHISPER_CPP_BIN", "definitely-not-whisper-cli")
    monkeypatch.setenv("WHISPER_CPP_MODEL_PATH", "")
    get_settings.cache_clear()
    service = STTService()

    info = service.debug_capabilities()

    assert info["provider"] == "faster-whisper"
    assert info["ffmpeg_available"] is False
    assert info["whisper_cpp_available"] is False
    assert info["whisper_cpp_model_configured"] is False
