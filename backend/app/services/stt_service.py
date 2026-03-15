from pathlib import Path
import json
import shutil
import subprocess
from typing import Any

from app.core.settings import get_settings
from app.schemas.voice import VoiceTranscriptionResult


class STTService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.ffmpeg_bin = self.settings.ffmpeg_bin
        self.provider = self.settings.stt_provider
        self.whisper_model = self.settings.whisper_model
        self.whisper_device = self.settings.whisper_device
        self.whisper_compute_type = self.settings.whisper_compute_type
        self.whisper_beam_size = self.settings.whisper_beam_size
        self.whisper_best_of = self.settings.whisper_best_of
        self.whisper_temperature = self.settings.whisper_temperature
        self.whisper_initial_prompt = self.settings.whisper_initial_prompt
        self.whisper_cpp_bin = self.settings.whisper_cpp_bin
        self.whisper_cpp_model_path = self.settings.whisper_cpp_model_path

    def convert_ogg_to_wav(self, input_path: str, output_path: str) -> str:
        if shutil.which(self.ffmpeg_bin) is None:
            raise RuntimeError("ffmpeg not found")
        command = [
            self.ffmpeg_bin,
            "-y",
            "-i",
            input_path,
            "-ar",
            "16000",
            "-ac",
            "1",
            output_path,
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "ffmpeg conversion failed")
        return output_path

    def transcribe(self, wav_path: str) -> VoiceTranscriptionResult:
        if self.provider == "stub":
            return self._transcribe_stub(wav_path)
        if self.provider == "faster-whisper":
            return self._transcribe_faster_whisper(wav_path)
        if self.provider == "whisper-cpp":
            return self._transcribe_whisper_cpp(wav_path)
        return VoiceTranscriptionResult(
            text=None,
            confidence=0.0,
            provider=self.provider,
            needs_fallback=True,
            failure_reason=f"unknown stt provider: {self.provider}",
        )

    def _transcribe_stub(self, wav_path: str) -> VoiceTranscriptionResult:
        text = self._read_sidecar_transcript(wav_path)
        if not text:
            return VoiceTranscriptionResult(
                text=None,
                confidence=0.0,
                provider="stub",
                needs_fallback=True,
                failure_reason="empty transcript",
            )
        confidence = 0.92 if len(text.split()) >= 2 else 0.45
        return VoiceTranscriptionResult(
            text=text,
            confidence=confidence,
            provider="stub",
            needs_fallback=confidence < self.settings.stt_min_confidence,
            failure_reason=None if confidence >= self.settings.stt_min_confidence else "low stt confidence",
        )

    def _transcribe_faster_whisper(self, wav_path: str) -> VoiceTranscriptionResult:
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except Exception as exc:
            stub_result = self._transcribe_stub(wav_path)
            if stub_result.text:
                return VoiceTranscriptionResult(
                    text=stub_result.text,
                    confidence=stub_result.confidence,
                    provider="faster-whisper:stub-fallback",
                    needs_fallback=stub_result.needs_fallback,
                    failure_reason=f"faster-whisper import failed: {exc}",
                )
            return VoiceTranscriptionResult(
                text=None,
                confidence=0.0,
                provider="faster-whisper",
                needs_fallback=True,
                failure_reason=f"faster-whisper import failed: {exc}",
            )

        try:
            model = WhisperModel(
                self.whisper_model,
                device=self.whisper_device,
                compute_type=self.whisper_compute_type,
            )
            segments, info = model.transcribe(
                wav_path,
                language="ru",
                vad_filter=True,
                beam_size=self.whisper_beam_size,
                best_of=self.whisper_best_of,
                temperature=self.whisper_temperature,
                condition_on_previous_text=False,
                initial_prompt=self.whisper_initial_prompt,
            )
            _ = info
            segment_list = list(segments)
            text = " ".join(segment.text.strip() for segment in segment_list if segment.text.strip()).strip()
            avg_logprob = None
            if segment_list:
                values = [getattr(segment, "avg_logprob", None) for segment in segment_list]
                filtered = [value for value in values if value is not None]
                if filtered:
                    avg_logprob = sum(filtered) / len(filtered)
            confidence = self._logprob_to_confidence(avg_logprob)
            if not text:
                confidence = 0.0
            return VoiceTranscriptionResult(
                text=text or None,
                confidence=confidence,
                provider="faster-whisper",
                needs_fallback=(not text) or confidence < self.settings.stt_min_confidence,
                failure_reason=None if text and confidence >= self.settings.stt_min_confidence else "low stt confidence",
            )
        except Exception as exc:
            stub_result = self._transcribe_stub(wav_path)
            if stub_result.text:
                return VoiceTranscriptionResult(
                    text=stub_result.text,
                    confidence=stub_result.confidence,
                    provider="faster-whisper:stub-fallback",
                    needs_fallback=stub_result.needs_fallback,
                    failure_reason=f"faster-whisper runtime failed: {exc}",
                )
            return VoiceTranscriptionResult(
                text=None,
                confidence=0.0,
                provider="faster-whisper",
                needs_fallback=True,
                failure_reason=f"faster-whisper runtime failed: {exc}",
            )

    def _transcribe_whisper_cpp(self, wav_path: str) -> VoiceTranscriptionResult:
        if shutil.which(self.whisper_cpp_bin) is None:
            return VoiceTranscriptionResult(
                text=None,
                confidence=0.0,
                provider="whisper-cpp",
                needs_fallback=True,
                failure_reason="whisper.cpp binary not found",
            )
        if not self.whisper_cpp_model_path:
            return VoiceTranscriptionResult(
                text=None,
                confidence=0.0,
                provider="whisper-cpp",
                needs_fallback=True,
                failure_reason="whisper.cpp model path not configured",
            )

        output_json = str(Path(wav_path).with_suffix(".json"))
        command = [
            self.whisper_cpp_bin,
            "-m",
            self.whisper_cpp_model_path,
            "-f",
            wav_path,
            "-l",
            "ru",
            "-oj",
            "-of",
            str(Path(wav_path).with_suffix("")),
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0:
            return VoiceTranscriptionResult(
                text=None,
                confidence=0.0,
                provider="whisper-cpp",
                needs_fallback=True,
                failure_reason=completed.stderr.strip() or "whisper.cpp failed",
            )
        try:
            payload = json.loads(Path(output_json).read_text(encoding="utf-8"))
            text = (payload.get("transcription") or "").strip()
        except Exception as exc:
            return VoiceTranscriptionResult(
                text=None,
                confidence=0.0,
                provider="whisper-cpp",
                needs_fallback=True,
                failure_reason=f"whisper.cpp output parse failed: {exc}",
            )
        confidence = 0.85 if len(text.split()) >= 2 else 0.4
        return VoiceTranscriptionResult(
            text=text or None,
            confidence=confidence,
            provider="whisper-cpp",
            needs_fallback=(not text) or confidence < self.settings.stt_min_confidence,
            failure_reason=None if text and confidence >= self.settings.stt_min_confidence else "low stt confidence",
        )

    @staticmethod
    def _read_sidecar_transcript(wav_path: str) -> str | None:
        sidecar = Path(wav_path).with_suffix(".txt")
        if not sidecar.exists():
            return None
        return sidecar.read_text(encoding="utf-8").strip() or None

    @staticmethod
    def _logprob_to_confidence(avg_logprob: float | None) -> float:
        if avg_logprob is None:
            return 0.75
        if avg_logprob >= -0.2:
            return 0.97
        if avg_logprob >= -0.5:
            return 0.9
        if avg_logprob >= -1.0:
            return 0.75
        if avg_logprob >= -1.5:
            return 0.6
        return 0.35

    def debug_capabilities(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "ffmpeg_available": shutil.which(self.ffmpeg_bin) is not None,
            "whisper_cpp_available": shutil.which(self.whisper_cpp_bin) is not None,
            "whisper_cpp_model_configured": bool(self.whisper_cpp_model_path),
        }
