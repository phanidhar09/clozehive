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
    # Refresh endpoint gets its own (tighter) limit — avoids token-grinding attacks.
    RATE_LIMIT_REFRESH: str = "30/minute"

    # ── Google OAuth ─────────────────────────────────────────────────────────
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # ── Account lockout (brute-force protection) ─────────────────────────────
    # After MAX_LOGIN_ATTEMPTS consecutive failures the account is locked for
    # LOCKOUT_DURATION_MINUTES minutes.  Both values are tunable per environment.
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 15

    # ── CSRF ─────────────────────────────────────────────────────────────────
    # The Double-Submit Cookie pattern: we set an opaque cookie and require the
    # same value in an X-CSRF-Token request header for state-mutating requests.
    CSRF_SECRET: str = ""          # Falls back to SECRET_KEY when empty
    CSRF_COOKIE_NAME: str = "csrftoken"
    CSRF_HEADER_NAME: str = "x-csrf-token"
    # State-mutating HTTP methods that require a valid CSRF token.
    CSRF_SAFE_METHODS: frozenset = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

    # ── Cookie security ───────────────────────────────────────────────────────
    # Set COOKIE_SECURE=true in production (HTTPS only).
    COOKIE_SECURE: bool = False       # override with COOKIE_SECURE=true in prod
    COOKIE_SAMESITE: str = "lax"      # 'strict' | 'lax' | 'none'
    COOKIE_DOMAIN: str = ""           # leave empty for same-domain

    # ── Cache TTLs (seconds) ─────────────────────────────────────────────────
    CACHE_TTL_PROFILE: int = 300
    CACHE_TTL_CLOSET: int = 120
    CACHE_TTL_WEATHER: int = 600

    # ── Helpers ──────────────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def effective_csrf_secret(self) -> str:
        """Use the dedicated CSRF secret when set; fall back to SECRET_KEY."""
        return self.CSRF_SECRET or self.SECRET_KEY


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton — import this everywhere instead of Settings()."""
    return Settings()


settings = get_settings()
