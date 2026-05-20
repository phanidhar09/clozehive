"""Shared SlowAPI limiter configuration."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

settings = get_settings()

# Use in-memory storage to avoid consuming Redis connections on the free tier.
# Redis-backed rate limiting requires a dedicated connection slot per worker
# which exhausts the Valkey free-tier limit (20 connections) immediately.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_default],
    storage_uri="memory://",
)
