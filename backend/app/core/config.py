from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_NAME: str = "GEO Flow Agent V2"
    APP_VERSION: str = "2.3.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Security
    SECRET_KEY: str = "geo-flow-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./geoflow_test.db"
    SYNC_DATABASE_URL: str = "sqlite:///./geoflow_test_sync.db"
    DATABASE_ECHO: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # AI / LLM
    DEFAULT_LLM_API_URL: Optional[str] = None
    DEFAULT_LLM_MODEL: str = "gpt-4o"
    DEFAULT_LLM_API_KEY: Optional[str] = None

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    CORS_ALLOW_ORIGIN_REGEX: Optional[str] = None

    # Business
    DEFAULT_SAMPLE_SIZE: int = 5
    CONFIDENCE_LEVEL_THRESHOLD_HIGH: float = 10.0  # Wilson half-width <= 10%
    CONFIDENCE_LEVEL_THRESHOLD_MEDIUM: float = 20.0  # Wilson half-width <= 20%
    BUDGET_WARNING_PERCENT: int = 80
    BUDGET_BLOCK_PERCENT: int = 100


@lru_cache()
def get_settings() -> Settings:
    return Settings()
