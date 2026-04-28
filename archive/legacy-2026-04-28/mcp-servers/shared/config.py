"""
Shared configuration for all MCP servers.
Loaded once via lru_cache — import get_settings() everywhere.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Locate the repo root .env (two levels up from mcp-servers/shared/)
_REPO_ROOT = Path(__file__).parent.parent.parent
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    # ── LLM ──────────────────────────────────────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-haiku-20240307"

    llm_provider: str = "openai"  # openai | anthropic

    # ── Database ──────────────────────────────────────────────────────────
    sqlite_db_path: str = str(_REPO_ROOT / "backend" / "data" / "closetiq.db")

    # ── MCP Server ports ──────────────────────────────────────────────────
    vision_host: str = "0.0.0.0"
    vision_port: int = 8001

    outfit_host: str = "0.0.0.0"
    outfit_port: int = 8002

    packing_host: str = "0.0.0.0"
    packing_port: int = 8003

    weather_host: str = "0.0.0.0"
    weather_port: int = 8004

    # ── Gateway ───────────────────────────────────────────────────────────
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8005

    # ── CORS ──────────────────────────────────────────────────────────────
    allowed_origins: str = "http://localhost:3000,http://localhost:3002,http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def vision_sse_url(self) -> str:
        return f"http://localhost:{self.vision_port}/sse"

    @property
    def outfit_sse_url(self) -> str:
        return f"http://localhost:{self.outfit_port}/sse"

    @property
    def packing_sse_url(self) -> str:
        return f"http://localhost:{self.packing_port}/sse"

    @property
    def weather_sse_url(self) -> str:
        return f"http://localhost:{self.weather_port}/sse"


@lru_cache
def get_settings() -> Settings:
    return Settings()
