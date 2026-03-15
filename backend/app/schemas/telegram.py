from dataclasses import dataclass


@dataclass(slots=True)
class TelegramVoicePayload:
    telegram_user_id: int
    telegram_message_id: int | None
    file_id: str
    original_file_path: str
    original_text: str = "voice message"
