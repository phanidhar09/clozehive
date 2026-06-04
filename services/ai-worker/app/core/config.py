"""AI worker settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CLOZEHIVE AI Worker"
    environment: str = "development"
    # ARQ uses Redis as the task broker. Point at the same Redis the rest of the
    # stack uses; a dedicated DB index (…/3) keeps job state out of the caches.
    redis_url: str = "redis://redis:6379/3"
    database_url: str = "postgresql://clozehive:clozehive@postgres:5432/clozehive"
    ai_agent_url: str = "http://ai-agent:8001"
    # ARQ re-runs a failing job up to this many times before it lands in the
    # failed set (each attempt re-invokes the task function).
    max_attempts: int = 5
    http_timeout_seconds: int = 120

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
