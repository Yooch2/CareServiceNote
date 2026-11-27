from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://csn:csn@localhost:5433/csn"

    jwt_secret: str
    jwt_ttl_hours: int = 12
    cookie_secure: bool = False

    audio_dir: Path = Path("var/audio")
    max_audio_bytes: int = 10 * 1024 * 1024
    daily_records_per_user: int = 20
    daily_records_total: int = 200

    ai_provider: Literal["fake", "local", "gemini"] = "fake"
    mlx_whisper_model: str = "mlx-community/whisper-large-v3-turbo"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_num_ctx: int = 8192
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"


settings = Settings()  # pyright: ignore[reportCallIssue]  # jwt_secret은 환경변수에서 읽음
