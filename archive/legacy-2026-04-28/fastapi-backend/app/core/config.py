"""
Application configuration — single source of truth.
All values are read from environment variables (or .env file).
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_NAME: str = "CLOZEHIVE API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str  # required — no default

    # ── Server ───────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str         # postgresql+asyncpg://...
    SYNC_DATABASE_URL: str    # postgresql+psycopg2://... (Alembic)

    # ── Redis ────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── JWT ──────────────────────────────────────────────────────────────────
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ALGORITHM: str = "HS256"

    # ── CORS ─────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    # ── AI Service ───────────────────────────────────────────────────────────
    AI_SERVICE_URL: str = "http://localhost:8001"
    OPENAI_API_KEY: str = ""

    # ── Rate Limiting ────────────────────────────────────────────────────────
    RATE_LIMIT_DEFAULT: str = "100/minute"
    RATE_LIMIT_AUTH: str = "10/minute"

    # ── Google OAuth ─────────────────────────────────────────────────────────
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # ── Cache TTLs (seconds) ─────────────────────────────────────────────────
    CACHE_TTL_PROFILE: int = 300
    CACHE_TTL_CLOSET: int = 120
    CACHE_TTL_WEATHER: int = 600

    # ── Helpers ──────────────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton — import this everywhere instead of Settings()."""
    return Settings()


settings = get_settings()
