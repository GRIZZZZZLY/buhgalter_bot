from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    database_url: str = "sqlite:///./finance_bot.db"
    telegram_bot_token: str = ""
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    llm_model: str = "minimax/minimax-m1:free"
    ffmpeg_bin: str = "ffmpeg"
    stt_provider: str = "faster-whisper"
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_beam_size: int = 5
    whisper_best_of: int = 5
    whisper_temperature: float = 0.0
    whisper_initial_prompt: str = "Финансовый ассистент. Русская речь. Возможны категории: еда, продукты, самокат, такси, транспорт, бензин, заправка, зарплата, аванс, клиент, заказ, фриланс."
    whisper_cpp_bin: str = "whisper-cli"
    whisper_cpp_model_path: str = ""
    stt_min_confidence: float = 0.6
    telegram_mode: str = "polling"
    telegram_webhook_url: str = ""
    telegram_webhook_secret: str = ""
    # Comma-separated list of allowed CORS origins.
    # Leave empty in dev to allow all origins ("*").
    # Example: https://your-domain.com,https://t.me
    cors_origins: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
