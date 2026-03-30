import logging
import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from app.services.stt_service import STTService

logger = logging.getLogger(__name__)


class AudioFileService:
    def __init__(self, stt_service: STTService | None = None, runtime_dir: str | None = None) -> None:
        self.stt_service = stt_service or STTService()
        self.runtime_dir = Path(runtime_dir or Path(__file__).resolve().parents[2] / "runtime" / "audio")
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    def prepare_wav_from_ogg(self, source_path: str, suffix: str | None = None) -> str:
        """Convert source OGG to WAV in runtime_dir.

        Both the intermediate .ogg copy and the resulting .wav are the caller's
        responsibility to delete.  Use cleanup_audio_files() after processing.
        """
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
        """Copy source file to a temp path inside runtime_dir."""
        fd, temp_path = tempfile.mkstemp(prefix="finance-bot-", suffix=extension, dir=self.runtime_dir)
        os.close(fd)
        Path(temp_path).write_bytes(Path(source_path).read_bytes())
        return temp_path

    @staticmethod
    def cleanup_audio_files(*paths: str) -> None:
        """Delete audio files, logging but not raising on errors."""
        for path in paths:
            if not path:
                continue
            try:
                p = Path(path)
                if p.exists():
                    p.unlink()
                    logger.debug("deleted audio file: %s", path)
            except OSError as exc:
                logger.warning("failed to delete audio file %s: %s", path, exc)

    def cleanup_stale_files(self, max_age_seconds: int = 3600) -> int:
        """Delete all .ogg/.wav files in runtime_dir older than max_age_seconds.

        Returns number of files deleted.
        """
        import time as _time
        now = _time.time()
        deleted = 0
        for p in self.runtime_dir.glob("*"):
            if p.suffix not in (".ogg", ".wav"):
                continue
            try:
                age = now - p.stat().st_mtime
                if age > max_age_seconds:
                    p.unlink()
                    deleted += 1
                    logger.debug("stale audio cleanup: deleted %s (age=%.0fs)", p.name, age)
            except OSError as exc:
                logger.warning("stale audio cleanup: failed to delete %s: %s", p, exc)
        if deleted:
            logger.info("stale audio cleanup: deleted %d file(s) older than %ds", deleted, max_age_seconds)
        return deleted
