"""
API Gateway — Application Settings
All config is driven by environment variables. Never hardcode secrets.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# libpq query params that the asyncpg driver rejects — SSL is supplied via
# connect_args (see db/session.py), so strip these from managed URLs (Neon,
# Supabase, …) which append e.g. ``?sslmode=require&channel_binding=require``.
_ASYNCPG_INCOMPATIBLE_DB_PARAMS = {"sslmode", "ssl", "channel_binding", "gssencmode"}

# config.py lives at services/api-gateway/app/core/config.py — 5 levels up is the project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

_CFG_LOG = logging.getLogger("clozehive.config")


def normalise_db_url(v: str) -> str:
    """Rewrite ``postgres://`` / bare ``postgresql://`` URLs to the asyncpg driver
    and strip libpq query params (``sslmode``, ``channel_binding``, …) that asyncpg
    rejects. Lets a managed connection string (Neon, Supabase, Render) be used
    as-is; SSL is applied via connect_args in db/session.py."""
    if not isinstance(v, str):
        return v
    if v.startswith("postgres://"):
        v = "postgresql+asyncpg://" + v[len("postgres://") :]
    elif v.startswith("postgresql://") and "+asyncpg" not in v:
        v = "postgresql+asyncpg://" + v[len("postgresql://") :]
    # Drop asyncpg-incompatible query params (e.g. Neon's ?sslmode=require).
    if "?" in v and any(p in v.lower() for p in _ASYNCPG_INCOMPATIBLE_DB_PARAMS):
        parsed = urlparse(v)
        kept = [
            (k, val)
            for k, val in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in _ASYNCPG_INCOMPATIBLE_DB_PARAMS
        ]
        v = urlunparse(parsed._replace(query=urlencode(kept)))
    return v


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

    # The wardrobe/intelligence domain routers default to OFF in production as a
    # safety interlock (a leftover from the retired closet-service split). The
    # gateway is now the sole owner of those prefixes, so production MUST set
    # SERVE_MIGRATED_DOMAIN_ROUTES=true (see render.yaml) or closet/outfits/ai
    # 404. They mount automatically in dev/test. Set this flag explicitly to
    # override the env-based default.
    serve_migrated_domain_routes: bool | None = None

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    # Graceful-shutdown drain window. On shutdown, /ready flips to 503 and the
    # process waits this many seconds before tearing down connections, giving the
    # load balancer time to stop routing so in-flight requests aren't cut off.
    # 0 = no added delay (current behaviour). Set to ~5 behind an autoscaler/LB.
    shutdown_drain_seconds: int = 0

    # ── Database (PostgreSQL + asyncpg) ───────────────────────────────────────
    database_url: str
    # Optional read-replica URL. Read-only endpoints (closet list, analytics)
    # are routed here to take load off the primary. Blank → reuse database_url,
    # so single-DB setups are unchanged. Replica reads are eventually consistent;
    # only route endpoints that tolerate slight staleness.
    database_read_url: str = ""
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
    # When startup migrations fail:
    # - true  => crash startup (fail-fast, safest for production)
    # - false => keep process alive but /ready reports 503
    fail_on_startup_migration_error: bool = False
    # When True, the Google OAuth callback appends the real error type+message to
    # the failed-login redirect URL (?detail=…). Use ONLY for debugging on hosts
    # without log access; turn OFF afterwards so internal errors aren't exposed.
    oauth_debug_errors: bool = False

    # ── Redis (separated by purpose) ──────────────────────────────────────────
    # Clozehive uses Redis for two jobs that scale and fail differently:
    #   • cache — ephemeral, safe to evict (allkeys-lru).
    #   • state — OAuth CSRF state, refresh tokens, rate-limit counters. These
    #             MUST NOT be evicted (noeviction); evicting them silently breaks
    #             logins and rate limiting under memory pressure.
    # In production point each at its own instance. Both fall back to
    # redis_url, so a single-Redis dev / free-tier setup keeps working unchanged.
    redis_url: str = "redis://localhost:6379/0"
    # Dedicated cache Redis (allkeys-lru). Blank → use redis_url.
    redis_cache_url: str = ""
    # Dedicated state Redis (noeviction). Blank → use redis_url.
    redis_state_url: str = ""
    # When False, /ready and /health skip Redis (local dev without Redis).
    redis_check_on_ready: bool = True
    cache_ttl_profile: int = 300  # 5 min
    cache_ttl_closet: int = 120  # 2 min
    cache_ttl_weather: int = 3600  # 1 hour
    cache_ttl_social: int = 60  # 1 min
    # Staged closet upload preview (analyze → confirm); Redis-backed session TTL.
    closet_preview_ttl_seconds: int = 3600

    # ── HTTP caching ──────────────────────────────────────────────────────────
    # Emit ETag + serve 304 Not Modified for cacheable JSON GETs (closet, profile,
    # analytics, outfits). Disable to turn off conditional-GET handling.
    http_cache_validation: bool = True
    # Cache-Control for those endpoints: browsers/CDN serve from cache for
    # max-age seconds, then may serve stale for swr seconds while revalidating.
    http_cache_max_age: int = 30
    http_cache_swr: int = 300
    # Redis soft-TTL fraction: when a cached entry is older than this fraction of
    # its TTL, serve it but trigger a background refresh (Redis-layer SWR).
    cache_soft_ttl_ratio: float = 0.8

    # ── JWT ───────────────────────────────────────────────────────────────────
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # ── Refresh-token cookie settings ─────────────────────────────────────────
    # The refresh token is stored in an HttpOnly cookie, invisible to JavaScript.
    # In production, set COOKIE_SECURE=true and COOKIE_SAMESITE=Lax (or Strict
    # if your API and frontend share the same eTLD+1).
    cookie_secure: bool = False  # override to True in production
    cookie_samesite: str = "Lax"  # Lax | Strict | None
    cookie_domain: str = ""  # leave blank for same-origin (recommended)

    # ── Internal service auth ─────────────────────────────────────────────────
    # Shared secret sent as X-Internal-Token on internal calls (e.g. user-data
    # purge). Used by internal-auth + account-purge. (The ai-agent/ai-worker
    # services this once talked to were retired — all AI runs in-process now.)
    internal_service_token: str = ""
    # Legacy: base URL of the retired closet-service. Empty by default so the
    # account-purge fan-out is a clean no-op — the gateway owns closet data in
    # its own DB and CASCADE-deletes it on account removal. Kept only so an
    # external closet store can be re-pointed here if one is ever reintroduced.
    closet_service_url: str = ""
    openweather_api_key: str = ""
    # Tavily web search — powers live destination dress guidelines (and later
    # festival/venue lookups). Empty key disables the web-intelligence layer;
    # every feature degrades to its static/LLM-infer fallback.
    tavily_api_key: str = ""
    # "Shop with FANI" URL paste: when a pasted product page exposes no OG/JSON-LD
    # image, we fall back to a rendered screenshot fed through the vision pipeline.
    # This is a URL template into any stateless screenshot service (e.g.
    # "https://image.thum.io/get/width/1200/{url}") — {url} is replaced with the
    # URL-encoded page. Empty = screenshot fallback disabled (no scraper infra
    # required); the feature still works whenever OG/JSON-LD metadata is present.
    product_screenshot_url_template: str = ""
    ai_cache_enabled: bool = True
    ai_cache_ttl: int = 600
    # Semantic response cache for the gated FANI chat paths: serves a prior
    # grounded response when a new turn's RAG-query embedding is near-identical
    # (cosine >= threshold) AND the closet/profile/weather context is unchanged.
    # Only clean responses (no validation errors, no claim-audit violations,
    # no images, shallow history) are ever stored — see app/core/semantic_cache.py.
    semantic_cache_enabled: bool = True
    # High-precision threshold: near-duplicate questions only. Lowering this
    # trades correctness for hit-rate; measure with semantic_cache_hit logs first.
    semantic_cache_threshold: float = 0.95
    semantic_cache_ttl: int = 3600  # 1 h — weather/trends drift beyond that
    semantic_cache_max_entries: int = 20  # per-user LRU window
    # text-embedding-3-small: same 1536-dim output as ada-002 but ~20% better on
    # semantic retrieval benchmarks and cheaper.  Changing this requires running
    # POST /api/v1/closet/re-embed to regenerate all stored embeddings.
    embedding_model: str = "text-embedding-3-small"
    openai_api_key: str = ""
    # Base URL passed explicitly to AsyncOpenAI (SDK ignores stray OS OPENAI_BASE_URL).
    # Use for Azure/other OpenAI-compatible gateways; leave default for api.openai.com.
    openai_api_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"
    # Cheap/fast tier used by the model router for low-complexity turns
    # (chit-chat, factual Q&A, single simple outfit). See model_router.py.
    openai_model_small: str = "gpt-4o-mini"
    # When True, the model router runs a cheap LLM micro-classifier to break ties
    # for turns whose deterministic complexity score lands in the ambiguous band.
    model_router_arbiter_enabled: bool = True
    # Hard ceiling on the arbiter call. Grey-zone turns must not add a full
    # serial chat hop — on timeout we keep the deterministic decision.
    model_router_arbiter_timeout_ms: int = 400
    openai_max_tokens: int = 4096
    # ── Gemini AI ─────────────────────────────────────────────────────────────
    gemini_api_key: str = ""
    # 2.5 Flash: stronger fashion/attribute reasoning than 1.5 with comparable latency,
    # and native structured-output (response_schema) support. Override via env if needed.
    gemini_model: str = "gemini-2.5-flash"

    # Closet POST /closet/analyze-preview: skip per-item BG removal + second OpenAI pass on each crop.
    # Much faster; detection metadata still comes from the first vision call. Set false for max quality.
    vision_preview_fast: bool = True

    # ── Vision model tiering ──────────────────────────────────────────────────
    # Detection (bounding boxes + rough classify — Gemini Flash is primary, this
    # is the OpenAI fallback) and quick single-item categorization don't need
    # the flagship model; the rich enrichment pass (analyze_for_bulk: fit,
    # material texture, product screenshots) stays on `openai_model`.
    vision_detection_model: str = "gpt-4o-mini"
    # Keep detection at high detail: bbox precision degrades hard at low
    # resolution — the cost lever here is the model, not the tiles.
    vision_detection_detail: Literal["auto", "low", "high"] = "high"
    vision_analysis_model: str = "gpt-4o-mini"

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
    # CDN origin in front of the public GCS bucket (e.g. https://cdn.clozehive.com).
    # When set, public image URLs are rewritten from storage.googleapis.com to this
    # host so reads hit the CDN edge instead of the origin bucket. Blank = no CDN
    # (serve straight from GCS). Only applies to the public-bucket path, not signed URLs.
    cdn_base_url: str = ""
    # Purge the CDN edge when an image is deleted, so a stale cached copy isn't
    # served after the origin blob is gone. Default off (no behaviour change).
    # Sends an HTTP PURGE to the object's CDN URL (Fastly/Varnish/nginx-cache);
    # for Cloudflare-style providers, set cdn_purge_webhook to a small forwarder.
    cdn_purge_enabled: bool = False
    cdn_purge_webhook: str = ""
    # When True, the bucket is treated as PRIVATE: stored image URLs are converted
    # to short-lived V4 signed URLs at read-time (only the app's service account
    # can mint them). Flip the bucket to private + remove allUsers before enabling.
    gcs_signed_urls: bool = False
    # Lifetime of a generated signed URL. Keep modest; clients re-fetch on expiry.
    gcs_signed_url_ttl_seconds: int = 3600

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

    # ── Email delivery ────────────────────────────────────────────────────────
    # Provider for transactional email (password reset, etc.):
    #   • console — log instead of sending (default; local dev without Docker).
    #   • smtp    — SMTP relay. In Docker dev this is Mailpit (UI at :8025),
    #               which catches all mail so nothing ever leaves your machine.
    #   • resend  — Resend HTTP API (production). Requires RESEND_API_KEY and a
    #               verified sending domain for EMAIL_FROM.
    email_provider: str = "console"
    email_from: str = "Clozehive <no-reply@clozehive.local>"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False  # implicit TLS (port 465)
    smtp_starttls: bool = False  # STARTTLS upgrade (port 587)
    resend_api_key: str = ""

    # ── Firebase / Firestore ──────────────────────────────────────────────────
    # Set FIREBASE_CREDENTIALS_JSON to the full contents of your service account JSON,
    # OR set GOOGLE_APPLICATION_CREDENTIALS to the path of the JSON file,
    # OR leave blank to use Application Default Credentials (works on GCP).
    firebase_credentials_json: str = ""
    firebase_project_id: str = ""

    # ── Observability ─────────────────────────────────────────────────────────
    log_level: str = "INFO"
    # Expose Prometheus /metrics and instrument HTTP + custom business metrics.
    enable_metrics: bool = True
    # Sentry error tracking. Blank = disabled (logs a warning in production).
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.1
    # PostHog product + LLM analytics. Blank api key = disabled (no-op). Emits
    # `$ai_generation` events (token/cost/latency per turn) — metadata only, no
    # prompt content. Host defaults to PostHog Cloud US.
    posthog_api_key: str = ""
    posthog_host: str = "https://us.i.posthog.com"
    # Distributed tracing (OpenTelemetry). Enable + point OTEL_EXPORTER_OTLP_ENDPOINT
    # at a collector (Tempo/Jaeger/Honeycomb). Default off = no tracing overhead.
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "api-gateway"
    # Fraction of traces sampled (1.0 = all). Lower in high-traffic production.
    otel_traces_sample_rate: float = 1.0

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
        return normalise_db_url(v)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def mount_migrated_routes(self) -> bool:
        """Whether the gateway should still mount the closet-service-owned domain
        routers (closet, outfits, trips, ai, ai-chat, analytics, rag, …).

        Explicit override wins; otherwise default to off in production only.
        """
        if self.serve_migrated_domain_routes is not None:
            return self.serve_migrated_domain_routes
        return not self.is_production

    @property
    def effective_database_read_url(self) -> str:
        """Read-replica URL (normalised for asyncpg). Falls back to database_url."""
        raw = self.database_read_url or self.database_url
        return normalise_db_url(raw)

    @property
    def has_read_replica(self) -> bool:
        """True only when a distinct replica URL is configured."""
        return bool(self.database_read_url) and self.database_read_url != self.database_url

    @property
    def effective_redis_cache_url(self) -> str:
        """Cache Redis (evictable). Falls back to the shared redis_url."""
        return self.redis_cache_url or self.redis_url

    @property
    def effective_redis_state_url(self) -> str:
        """State Redis for OAuth/refresh tokens/rate limits (non-evictable).
        Falls back to the shared redis_url."""
        return self.redis_state_url or self.redis_url

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
            # Internal-service calls (account deletion, cross-service auth) are
            # silently skipped when the token is empty, leaving stale data in
            # closet-service.  Require it in production so operators notice.
            if not self.internal_service_token:
                raise ValueError(
                    "INTERNAL_SERVICE_TOKEN must be set in production. "
                    'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
                )
            # Email: "console" silently breaks password reset for real users; a
            # misconfigured resend key fails every send. Warn loudly rather than
            # crash so a missing email key can't take the whole API down.
            if self.email_provider == "console":
                _CFG_LOG.warning(
                    "EMAIL_PROVIDER=console in production — password-reset emails "
                    "will NOT be delivered. Set EMAIL_PROVIDER=resend + RESEND_API_KEY."
                )
            elif self.email_provider == "resend" and not self.resend_api_key:
                _CFG_LOG.warning("EMAIL_PROVIDER=resend but RESEND_API_KEY is empty — all email sends will fail.")
            # The refresh-token cookie must be HTTPS-only in production, otherwise
            # a network attacker on an http:// page can intercept it.
            if not self.cookie_secure:
                raise ValueError(
                    "COOKIE_SECURE must be true in production so the refresh-token cookie is only sent over HTTPS."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
