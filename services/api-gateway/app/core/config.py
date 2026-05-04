"""
API Gateway — Application Settings
All config is driven by environment variables. Never hardcode secrets.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py lives at services/api-gateway/app/core/config.py — 5 levels up is the project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


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
    database_url: str
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_pre_ping: bool = True
    db_pool_recycle: int = 300
    db_pool_timeout: int = 30

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    # When False, /ready and /health skip Redis (local dev without Redis).
    redis_check_on_ready: bool = True
    cache_ttl_profile: int = 300      # 5 min
    cache_ttl_closet: int = 120       # 2 min
    cache_ttl_weather: int = 3600     # 1 hour
    cache_ttl_social: int = 60        # 1 min

    # ── JWT ───────────────────────────────────────────────────────────────────
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # ── AI Agent Service ──────────────────────────────────────────────────────
    ai_agent_url: str = "http://ai-agent:8001"
    ai_timeout_seconds: int = 60
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_max_tokens: int = 1024
    openweather_api_key: str = ""
    ai_cache_enabled: bool = True
    ai_cache_ttl: int = 600
    embedding_model: str = "text-embedding-ada-002"
    openai_api_key: str = ""

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
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    frontend_url: str = "http://localhost:3000"

    # ── Firebase / Firestore ──────────────────────────────────────────────────
    # Set FIREBASE_CREDENTIALS_JSON to the full contents of your service account JSON,
    # OR set GOOGLE_APPLICATION_CREDENTIALS to the path of the JSON file,
    # OR leave blank to use Application Default Credentials (works on GCP).
    firebase_credentials_json: str = ""
    firebase_project_id: str = ""

    # ── Observability ─────────────────────────────────────────────────────────
    log_level: str = "INFO"
    enable_metrics: bool = True
    sentry_dsn: str = ""

    # ── Kafka / Redpanda ──────────────────────────────────────────────────────
    kafka_enabled: bool = True
    kafka_bootstrap_servers: str = "redpanda:9092"
    kafka_client_id: str = "clozehive-api-gateway"
    kafka_result_group_id: str = "clozehive-api-gateway-results"
    kafka_request_timeout_ms: int = 10_000

    model_config = SettingsConfigDict(
        env_file=(str(_ENV_FILE), ".env"),  # project root first, then local CWD override
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
            if len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be a strong production secret")
            if not self.allowed_origins or "localhost" in self.allowed_origins:
                raise ValueError("ALLOWED_ORIGINS must be explicit production origins")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
