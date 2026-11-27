from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # production이면 시작할 때 위험한 설정을 막는다 (_check_production)
    env: Literal["development", "production"] = "development"

    database_url: str = "postgresql+psycopg://csn:csn@localhost:5433/csn"

    jwt_secret: str
    jwt_ttl_hours: int = 12
    cookie_secure: bool = False

    audio_dir: Path = Path("var/audio")
    max_audio_bytes: int = 10 * 1024 * 1024
    # 음성·사진 파일 암호화 키 (Fernet). 만들기: python -m app.storage
    storage_key: str | None = None
    # 보관 기간: 확정되지 않은 기록의 음성·사진 / 확정 기록의 전사문·초안
    audio_retention_days: int = 30
    transcript_retention_days: int = 180
    max_photo_bytes: int = 5 * 1024 * 1024
    max_photos_per_record: int = 3
    daily_records_per_user: int = 20
    daily_records_total: int = 200
    daily_summaries_per_user: int = 20
    daily_summaries_total: int = 200
    # 시도 횟수 제한: 아이디별 로그인 실패, 서비스 전체 초대 코드 실패
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    invite_max_failures_per_hour: int = 30

    ai_provider: Literal["fake", "local", "gemini"] = "fake"
    mlx_whisper_model: str = "mlx-community/whisper-large-v3-turbo"
    ollama_url: str = "http://localhost:11434"
    # 분류 출력 최대 토큰 (반복 생성 방지). 보통 출력은 260~360토큰이고 M 시리즈 맥에서
    # 초당 약 12토큰이라, 1024토큰(약 85초)이면 HTTP 시간 초과(120초) 전에 끝난다.
    ollama_num_predict: int = 1024
    ollama_model: str = "qwen2.5:7b"
    ollama_num_ctx: int = 8192
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if self.env != "production":
            return self
        problems = []
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE=true 여야 합니다 (HTTPS 전용 쿠키)")
        if len(self.jwt_secret) < 32 or "change-me" in self.jwt_secret:
            problems.append("JWT_SECRET을 32자 이상 임의 문자열로 바꿔야 합니다")
        if not self.storage_key:
            problems.append("STORAGE_KEY가 필요합니다 (python -m app.storage)")
        if self.ai_provider == "fake":
            problems.append("AI_PROVIDER가 fake입니다")
        if self.ai_provider == "gemini" and not self.gemini_api_key:
            problems.append("GEMINI_API_KEY가 없습니다")
        if problems:
            raise ValueError("운영 설정 오류: " + " / ".join(problems))
        return self


settings = Settings()  # pyright: ignore[reportCallIssue]  # jwt_secret은 환경변수에서 읽음
