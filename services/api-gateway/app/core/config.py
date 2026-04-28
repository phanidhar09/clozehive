"""
API Gateway — Application Settings
All config is driven by environment variables. Never hardcode secrets.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────────────────────
    app_name: str = "CLOZEHIVE API"
    app_version: str = "2.0.0"
    environment: str = "development"  # development | staging | production
    debug: bool = False

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000

    # ── Database (PostgreSQL + asyncpg) ───────────────────────────────────────
    database_url: str = "postgresql+asyncpg://clozehive:clozehive@localhost:5432/clozehive"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_pre_ping: bool = True

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_profile: int = 300      # 5 min
    cache_ttl_closet: int = 120       # 2 min
    cache_ttl_weather: int = 3600     # 1 hour
    cache_ttl_social: int = 60        # 1 min

    # ── JWT ───────────────────────────────────────────────────────────────────
    jwt_secret: str = "CHANGE_ME_TO_A_RANDOM_64_CHAR_SECRET"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # ── AI Agent Service ──────────────────────────────────────────────────────
    ai_agent_url: str = "http://ai-agent:8001"
    ai_timeout_seconds: int = 60

    # ── File Upload ───────────────────────────────────────────────────────────
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 10

    # ── CORS ──────────────────────────────────────────────────────────────────
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    rate_limit_default: str = "100/minute"
    rate_limit_auth: str = "10/minute"
    rate_limit_ai: str = "20/minute"

    # ── OAuth ─────────────────────────────────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    oauth_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"

    # ── Observability ─────────────────────────────────────────────────────────
    log_level: str = "INFO"
    enable_metrics: bool = True
    sentry_dsn: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
        """Render (and Heroku) supply ``postgres://`` URLs — rewrite to the async driver."""
        if not isinstance(v, str):
            return v
        if v.startswith("postgres://"):
            return "postgresql+asyncpg://" + v[len("postgres://"):]
        if v.startswith("postgresql://") and "+asyncpg" not in v:
            return "postgresql+asyncpg://" + v[len("postgresql://"):]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @model_validator(mode="after")
    def _validate_production_config(self):
        if self.is_production:
            unsafe_secrets = {
                "CHANGE_ME_TO_A_RANDOM_64_CHAR_SECRET",
                "dev_secret_change_in_production_please",
            }
            if self.jwt_secret in unsafe_secrets or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be a strong production secret")
            if not self.allowed_origins or "localhost" in self.allowed_origins:
                raise ValueError("ALLOWED_ORIGINS must be explicit production origins")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
