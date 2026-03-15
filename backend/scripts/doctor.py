from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.settings import get_settings
from app.services.stt_service import STTService


def main() -> int:
    settings = get_settings()
    stt = STTService()
    capabilities = stt.debug_capabilities()

    checks: list[tuple[str, bool, str]] = [
        ("python_venv", Path(".venv").exists(), "Локальный .venv должен существовать"),
        ("telegram_token", bool(settings.telegram_bot_token), "TELEGRAM_BOT_TOKEN должен быть задан"),
        ("ffmpeg", capabilities["ffmpeg_available"], f"ffmpeg path: {settings.ffmpeg_bin}"),
        ("run_bot", Path("run_bot.py").exists(), "Точка входа polling runtime"),
        ("alembic", Path("alembic.ini").exists(), "Alembic config"),
    ]

    if settings.stt_provider == "whisper-cpp":
        checks.append(
            (
                "whisper_cpp_model",
                capabilities["whisper_cpp_model_configured"],
                "Для whisper-cpp нужен WHISPER_CPP_MODEL_PATH",
            )
        )
        checks.append(
            (
                "whisper_cpp_bin",
                capabilities["whisper_cpp_available"],
                f"whisper.cpp bin: {settings.whisper_cpp_bin}",
            )
        )

    print("Finance Bot Doctor")
    print(f"STT provider: {settings.stt_provider}")
    print(f"whisper model: {settings.whisper_model}")
    if shutil.which("ffmpeg"):
        print(f"system ffmpeg: {shutil.which('ffmpeg')}")

    failed = 0
    for name, ok, detail in checks:
        mark = "OK" if ok else "FAIL"
        print(f"[{mark}] {name}: {detail}")
        if not ok:
            failed += 1

    if settings.stt_provider == "faster-whisper":
        try:
            import faster_whisper  # type: ignore

            print(f"[OK] faster_whisper_import: {getattr(faster_whisper, '__file__', 'imported')}")
        except Exception as exc:
            failed += 1
            print(f"[FAIL] faster_whisper_import: {exc}")

    if failed:
        print(f"\nDoctor result: {failed} problem(s) found")
        return 1

    print("\nDoctor result: ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
