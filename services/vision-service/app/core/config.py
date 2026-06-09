"""
Vision Service — Application Settings
All config is driven by environment variables. Never hardcode secrets.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py lives at services/vision-service/app/core/config.py
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    # ── Database (PostgreSQL + asyncpg) ───────────────────────────────────────
    database_url: str
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle: int = 300

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/2"
    closet_preview_ttl_seconds: int = 3600

    # ── JWT ───────────────────────────────────────────────────────────────────
    jwt_secret: str
    jwt_algorithm: str = "HS256"

    # ── OpenAI ────────────────────────────────────────────────────────────────
    openai_api_key: str = ""
    openai_api_base_url: str = "https://api.openai.com/v1"
    # text-embedding-3-small: same 1536-dim output as ada-002 but cheaper and
    # better recall. MUST match the model used by api-gateway / closet-service,
    # since all three write/read the same closet_items.embedding vector space.
    embedding_model: str = "text-embedding-3-small"
    openai_model: str = "gpt-4o"

    # ── Gemini AI ─────────────────────────────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash-latest"

    # ── Google Cloud Storage ──────────────────────────────────────────────────
    gcs_bucket_name: str = ""
    gcs_project_id: str = ""
    gcs_credentials_json: str = ""
    gcs_credentials_file: str = ""

    @field_validator("gcs_credentials_json", mode="before")
    @classmethod
    def _strip_gcs_json_wrapper(cls, v: object) -> object:
        if not isinstance(v, str):
            return v
        s = v.strip()
        if len(s) >= 2 and ((s[0] == s[-1]) and s[0] in ("'", '"')):
            return s[1:-1]
        return s

    # ── Internal service auth ──────────────────────────────────────────────────
    internal_service_token: str = ""

    # ── App ───────────────────────────────────────────────────────────────────
    environment: str = "development"
    debug: bool = False
    uploads_dir: str = "./uploads"

    model_config = SettingsConfigDict(
        env_file=(str(_ENV_FILE), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
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
    def gcs_enabled(self) -> bool:
        return bool(self.gcs_bucket_name)

    @property
    def upload_path(self) -> Path:
        p = Path(self.uploads_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()
