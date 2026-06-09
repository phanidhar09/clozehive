"""AI Agent Service — settings."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_AI_CFG_LOG = logging.getLogger("clozehive.ai_agent.config")


def _sanitize_openai_api_base(url: str) -> str:
    official = "https://api.openai.com/v1"
    raw = (url or "").strip() or official
    low = raw.lower().rstrip("/")
    risky = False
    if ":4000" in raw:
        risky = "/v1" in low or low.endswith(":4000")
    elif "localhost:4000" in low or "127.0.0.1:4000" in low:
        risky = True
    if risky:
        _AI_CFG_LOG.warning("openai_api_base_url_reset: was %s; using api.openai.com", raw[:80])
        return official
    return raw


class Settings(BaseSettings):
    # App
    app_name: str = "CLOZEHIVE AI Agent"
    app_version: str = "2.0.0"
    environment: str = "development"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8001

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # OpenWeather — when set, the weather tool returns live forecasts and falls
    # back to static climate profiles only on error / out-of-range dates.
    openweather_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    # Passed explicitly into clients so OS OPENAI_BASE_URL cannot hijack calls.
    openai_api_base_url: str = "https://api.openai.com/v1"

    # Redis
    redis_url: str = "redis://redis:6379/1"
    cache_ttl_agent: int = 300  # 5 min

    # Vector search
    vector_store: Literal["disabled", "pgvector", "qdrant"] = "pgvector"
    database_url: str = "postgresql://clozehive:clozehive@postgres:5432/clozehive"
    vector_search_limit: int = 8
    vector_score_threshold: float = 0.78

    # Persistent per-user style memory — durable preference facts ("dislikes
    # yellow", "prefers smart-casual") retrieved on every chat so FANI remembers
    # the user across sessions. Extraction runs in the background after a reply.
    style_memory_enabled: bool = True
    style_memory_retrieve_limit: int = 6
    style_memory_score_threshold: float = 0.45  # broad: preferences need only loose relevance
    style_memory_dedup_threshold: float = 0.90  # >= this similarity = near-duplicate, skip insert
    style_memory_max_per_user: int = 100
    style_memory_extract_model: str = "gpt-4o-mini"

    # Agent config
    agent_max_iterations: int = 10
    agent_timeout_seconds: int = 60
    agent_temperature: float = 0.7

    # Retry
    retry_max_attempts: int = 3
    retry_min_wait: float = 1.0
    retry_max_wait: float = 8.0

    # Shared secret expected in X-Internal-Token header from api-gateway.
    # Empty string = token check disabled (development default).
    internal_service_token: str = ""

    # CORS (API gateway only should call this)
    allowed_origins: str = "http://api-gateway:8000,http://localhost:8000"

    # Observability
    enable_metrics: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def _sanitize_openai_base_url(self):
        self.openai_api_base_url = _sanitize_openai_api_base(self.openai_api_base_url)
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def has_valid_openai_key(self) -> bool:
        key = self.openai_api_key.strip()
        return key.startswith("sk-") and key not in {"sk-your-openai-key", "sk-test"}



@lru_cache
def get_settings() -> Settings:
    return Settings()
