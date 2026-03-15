from pathlib import Path

from app.services.audio_file_service import AudioFileService


class FakeSTTService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def convert_ogg_to_wav(self, input_path: str, output_path: str) -> str:
        self.calls.append((input_path, output_path))
        Path(output_path).write_bytes(b"wav")
        return output_path


def test_prepare_wav_from_ogg_skips_copy_when_same_path(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "audio"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    ogg_path = runtime_dir / "same.ogg"
    ogg_path.write_bytes(b"ogg")
    fake = FakeSTTService()
    service = AudioFileService(stt_service=fake, runtime_dir=str(runtime_dir))

    wav_path = service.prepare_wav_from_ogg(str(ogg_path), suffix="same")

    assert fake.calls[0][0] == str(ogg_path)
    assert wav_path.endswith("same.wav")


def test_prepare_wav_from_ogg_copies_when_different_path(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "audio"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "input.ogg"
    source.write_bytes(b"ogg")
    fake = FakeSTTService()
    service = AudioFileService(stt_service=fake, runtime_dir=str(runtime_dir))

    wav_path = service.prepare_wav_from_ogg(str(source), suffix="copy")

    assert fake.calls[0][0].endswith("copy.ogg")
    assert wav_path.endswith("copy.wav")
