"""
API Gateway — Application Settings
All config is driven by environment variables. Never hardcode secrets.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import logging
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py lives at services/api-gateway/app/core/config.py — 5 levels up is the project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

_CFG_LOG = logging.getLogger("clozehive.config")


def sanitize_openai_api_base(url: str) -> str:
    """Rewrite risky OpenAI-compat proxy URLs (e.g. local :4000 gateways) to the official API."""
    official = "https://api.openai.com/v1"
    raw = (url or "").strip() or official
    low = raw.lower().rstrip("/")
    risky = False
    if ":4000" in raw:
        risky = "/v1" in low or low.endswith(":4000")
    elif "localhost:4000" in low or "127.0.0.1:4000" in low:
        risky = True
    if risky:
        _CFG_LOG.warning("openai_api_base_url_reset: was %s; using api.openai.com", raw[:80])
        return official
    return raw


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
    # Run `alembic upgrade head` automatically on app startup. Intended for hosts
    # without a shell or pre-deploy hook (e.g. Render free tier). Idempotent; a
    # failure is logged, not fatal. Leave False for local dev where you run
    # migrations manually.
    run_migrations_on_startup: bool = False
    # When True, the Google OAuth callback appends the real error type+message to
    # the failed-login redirect URL (?detail=…). Use ONLY for debugging on hosts
    # without log access; turn OFF afterwards so internal errors aren't exposed.
    oauth_debug_errors: bool = False

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    # When False, /ready and /health skip Redis (local dev without Redis).
    redis_check_on_ready: bool = True
    cache_ttl_profile: int = 300      # 5 min
    cache_ttl_closet: int = 120       # 2 min
    cache_ttl_weather: int = 3600     # 1 hour
    cache_ttl_social: int = 60        # 1 min
    # Staged closet upload preview (analyze → confirm); Redis-backed session TTL.
    closet_preview_ttl_seconds: int = 3600

    # ── JWT ───────────────────────────────────────────────────────────────────
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # ── Refresh-token cookie settings ─────────────────────────────────────────
    # The refresh token is stored in an HttpOnly cookie, invisible to JavaScript.
    # In production, set COOKIE_SECURE=true and COOKIE_SAMESITE=Lax (or Strict
    # if your API and frontend share the same eTLD+1).
    cookie_secure: bool = False           # override to True in production
    cookie_samesite: str = "Lax"          # Lax | Strict | None
    cookie_domain: str = ""              # leave blank for same-origin (recommended)

    # ── AI Agent Service ──────────────────────────────────────────────────────
    ai_agent_url: str = "http://ai-agent:8001"
    # Budget for a single ai-agent read. connect timeout is always 5 s (see ai_client.py).
    ai_timeout_seconds: int = 30
    # Shared secret sent as X-Internal-Token on every api-gateway → ai-agent request.
    internal_service_token: str = ""
    openweather_api_key: str = ""
    ai_cache_enabled: bool = True
    ai_cache_ttl: int = 600
    # text-embedding-3-small: same 1536-dim output as ada-002 but ~20% better on
    # semantic retrieval benchmarks and cheaper.  Changing this requires running
    # POST /api/v1/closet/re-embed to regenerate all stored embeddings.
    embedding_model: str = "text-embedding-3-small"
    openai_api_key: str = ""
    # Base URL passed explicitly to AsyncOpenAI (SDK ignores stray OS OPENAI_BASE_URL).
    # Use for Azure/other OpenAI-compatible gateways; leave default for api.openai.com.
    openai_api_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"
    openai_max_tokens: int = 4096
    # ── Gemini AI ─────────────────────────────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash-latest"

# Closet POST /closet/analyze-preview: skip per-item BG removal + second OpenAI pass on each crop.
    # Much faster; detection metadata still comes from the first vision call. Set false for max quality.
    vision_preview_fast: bool = True

    # ── File Upload ───────────────────────────────────────────────────────────
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 10

    # ── Google Cloud Storage (persistent image storage) ───────────────────────
    # When gcs_bucket_name is set, uploads go to GCS and return public HTTPS URLs.
    # Leave blank to use local disk (development only — not persistent across deploys).
    gcs_bucket_name: str = ""
    gcs_project_id: str = ""
    # Service account JSON string. Leave empty if using gcs_credentials_file or ADC.
    gcs_credentials_json: str = ""
    # Path to service-account JSON inside the container (recommended for Docker — mount a file).
    gcs_credentials_file: str = ""

    @field_validator("gcs_credentials_json", mode="before")
    @classmethod
    def _strip_gcs_json_wrapper(cls, v: object) -> object:
        """Docker / shell quotes sometimes wrap the JSON string in extra ' or "."""
        if not isinstance(v, str):
            return v
        s = v.strip()
        if len(s) >= 2 and ((s[0] == s[-1]) and s[0] in ("'", '"')):
            return s[1:-1]
        return s

    # ── CORS ──────────────────────────────────────────────────────────────────
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    rate_limit_default: str = "100/minute"
    rate_limit_auth: str = "10/minute"
    rate_limit_ai: str = "20/minute"

    # ── OAuth ─────────────────────────────────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
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

    # ── RAG / Vector store ────────────────────────────────────────────────────
    # "pgvector" uses PostgreSQL + pgvector extension (production default).
    # "faiss"    uses an in-memory FAISS index (local dev / testing, no pgvector required).
    rag_vector_store: str = "pgvector"
    # Directory where FAISS indexes are persisted to disk (only used when rag_vector_store=faiss).
    faiss_index_dir: str = "./faiss_indexes"

    model_config = SettingsConfigDict(
        env_file=(str(_ENV_FILE), ".env"),  # project root first, then local CWD override
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
        """Heroku-style and some managed DBs supply ``postgres://`` URLs — rewrite for asyncpg."""
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
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @model_validator(mode="after")
    def _sanitize_openai_base_url_and_validate_production(self):
        """Normalize risky proxy base URLs toward the official OpenAI API."""
        self.openai_api_base_url = sanitize_openai_api_base(self.openai_api_base_url)

        if self.is_production:
            if len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be a strong production secret")
            if not self.allowed_origins or "localhost" in self.allowed_origins:
                raise ValueError("ALLOWED_ORIGINS must be explicit production origins")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
