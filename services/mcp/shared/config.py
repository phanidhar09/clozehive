"""Shared MCP config — updated for services/mcp/ layout and new ports."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"

    llm_provider: str = "openai"

    # New ports (services/mcp layout)
    weather_host: str = "0.0.0.0"
    weather_port: int = 8010

    vision_host: str = "0.0.0.0"
    vision_port: int = 8011

    outfit_host: str = "0.0.0.0"
    outfit_port: int = 8012

    packing_host: str = "0.0.0.0"
    packing_port: int = 8013

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def weather_sse_url(self) -> str:
        return f"http://mcp-weather:{self.weather_port}/sse"

    @property
    def outfit_sse_url(self) -> str:
        return f"http://mcp-outfit:{self.outfit_port}/sse"

    @property
    def packing_sse_url(self) -> str:
        return f"http://mcp-packing:{self.packing_port}/sse"

    @property
    def vision_sse_url(self) -> str:
        return f"http://mcp-vision:{self.vision_port}/sse"


@lru_cache
def get_settings() -> Settings:
    return Settings()
