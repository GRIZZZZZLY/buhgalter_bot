from pathlib import Path
import os
import shutil
import tempfile
from uuid import uuid4

from app.services.stt_service import STTService


class AudioFileService:
    def __init__(self, stt_service: STTService | None = None, runtime_dir: str | None = None) -> None:
        self.stt_service = stt_service or STTService()
        self.runtime_dir = Path(runtime_dir or Path(__file__).resolve().parents[2] / "runtime" / "audio")
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    def prepare_wav_from_ogg(self, source_path: str, suffix: str | None = None) -> str:
        suffix = suffix or uuid4().hex
        source = Path(source_path)
        ogg_target = self.runtime_dir / f"{suffix}.ogg"
        wav_target = self.runtime_dir / f"{suffix}.wav"
        if source.resolve() != ogg_target.resolve():
            shutil.copyfile(source, ogg_target)
        else:
            ogg_target = source
        self.stt_service.convert_ogg_to_wav(str(ogg_target), str(wav_target))
        return str(wav_target)

    def temp_copy(self, source_path: str, extension: str) -> str:
        fd, temp_path = tempfile.mkstemp(prefix="finance-bot-", suffix=extension, dir=self.runtime_dir)
        os.close(fd)
        Path(temp_path).write_bytes(Path(source_path).read_bytes())
        return temp_path
