from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from backend/.env and process environment."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", validation_alias="APP_ENV")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_MODEL")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        validation_alias="OPENAI_EMBEDDING_MODEL",
    )
    database_url: str = Field(
        default="sqlite+aiosqlite:///./backend/data/nexusflow.db",
        validation_alias="DATABASE_URL",
    )
    memory_enabled: bool = Field(default=True, validation_alias="MEMORY_ENABLED")
    development_session_id: str = Field(
        default="development-session",
        validation_alias="DEVELOPMENT_SESSION_ID",
    )
    redis_url: str = Field(
        default="redis://127.0.0.1:6379/0",
        validation_alias="REDIS_URL",
    )
    celery_task_time_limit: int = Field(default=120, validation_alias="CELERY_TASK_TIME_LIMIT")
    celery_task_soft_time_limit: int = Field(
        default=105, validation_alias="CELERY_TASK_SOFT_TIME_LIMIT"
    )
    cors_origins: str = Field(
        default="http://127.0.0.1:5173,http://localhost:5173",
        validation_alias="CORS_ORIGINS",
    )
    auth_secret: str = Field(
        default="change-this-auth-secret-in-production",
        validation_alias="AUTH_SECRET",
    )
    auth_token_ttl: int = Field(default=86400, validation_alias="AUTH_TOKEN_TTL")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() in {"development", "test"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
