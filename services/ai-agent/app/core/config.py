"""AI Agent Service — settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    openai_embedding_model: str = "text-embedding-3-small"

    # MCP Server URLs (SSE)
    mcp_weather_url: str = "http://mcp-weather:8010/sse"
    mcp_vision_url: str = "http://mcp-vision:8011/sse"
    mcp_outfit_url: str = "http://mcp-outfit:8012/sse"
    mcp_packing_url: str = "http://mcp-packing:8013/sse"

    # Redis
    redis_url: str = "redis://redis:6379/1"
    cache_ttl_agent: int = 300  # 5 min

    # Vector search
    vector_store: Literal["disabled", "pgvector", "qdrant"] = "pgvector"
    database_url: str = "postgresql://clozehive:clozehive@postgres:5432/clozehive"
    vector_search_limit: int = 8
    vector_score_threshold: float = 0.78

    # Agent config
    agent_max_iterations: int = 10
    agent_timeout_seconds: int = 60
    agent_temperature: float = 0.7

    # Retry
    retry_max_attempts: int = 3
    retry_min_wait: float = 1.0
    retry_max_wait: float = 8.0

    # CORS (API gateway only should call this)
    allowed_origins: str = "http://api-gateway:8000,http://localhost:8000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def mcp_server_config(self) -> dict:
        return {
            "weather": {"transport": "sse", "url": self.mcp_weather_url},
            "vision":  {"transport": "sse", "url": self.mcp_vision_url},
            "outfit":  {"transport": "sse", "url": self.mcp_outfit_url},
            "packing": {"transport": "sse", "url": self.mcp_packing_url},
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
