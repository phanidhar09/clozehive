"""AI worker settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CLOZEHIVE AI Worker"
    environment: str = "development"
    kafka_bootstrap_servers: str = "redpanda:9092"
    kafka_group_id: str = "clozehive-ai-worker"
    kafka_client_id: str = "clozehive-ai-worker"
    database_url: str = "postgresql://clozehive:clozehive@postgres:5432/clozehive"
    ai_agent_url: str = "http://ai-agent:8001"
    max_attempts: int = 5
    http_timeout_seconds: int = 120

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
