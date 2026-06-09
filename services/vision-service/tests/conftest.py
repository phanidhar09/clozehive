"""Shared fixtures for vision-service tests — no network, no OpenAI, no Postgres.

Settings requires DATABASE_URL and JWT_SECRET; set placeholders before any
app import so get_settings() (lru_cached) never sees real credentials.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://ci:ci@localhost/ci")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-at-least-32-characters-long")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("ENVIRONMENT", "development")
