from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "File Deduplication & Storage Optimization API"
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "mysql+pymysql://dedup:dedup_password@localhost:3306/dedup_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    SECRET_KEY: str = "change-this-secret-key-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    UPLOAD_DIR: str = "./storage/uploads"
    MAX_UPLOAD_SIZE_MB: int = 500
    HASH_CHUNK_SIZE: int = 1024 * 1024  # 1 MiB streaming chunks

    # Comma separated lists (kept as strings so .env parsing stays simple)
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    BLOCKED_EXTENSIONS: str = "exe,bat,cmd,com,scr,msi,dll,sh,ps1,vbs,jar,apk"

    CELERY_TASK_ALWAYS_EAGER: bool = False

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def blocked_extensions_set(self) -> set[str]:
        return {e.strip().lower().lstrip(".") for e in self.BLOCKED_EXTENSIONS.split(",") if e.strip()}

    @property
    def upload_root(self) -> Path:
        return Path(self.UPLOAD_DIR).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
