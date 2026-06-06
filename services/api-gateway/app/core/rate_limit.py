"""Shared SlowAPI limiter configuration.

Two limiters:

  limiter      — in-memory, used for non-critical API routes.  Per-worker so
                 the effective cap is (limit × worker_count), but free-tier
                 Redis only has ~20 connections and we can't burn them all on
                 every endpoint.

  auth_limiter — Redis-backed, used ONLY for the highest-risk auth endpoints
                 (login, signup, forgot-password, OAuth).  These are the ones
                 that matter for brute-force / credential-stuffing attacks.
                 Uses a dedicated pool capped at 3 connections so it can't
                 exhaust the Valkey free tier.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

settings = get_settings()

# Default in-memory limiter — cheap, per-worker.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_default],
    storage_uri="memory://",
)

# Redis-backed limiter for auth endpoints — truly global across all workers.
# Falls back to memory if Redis is unavailable so auth still works.
try:
    auth_limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[settings.rate_limit_auth],
        storage_uri=f"{settings.effective_redis_state_url}?max_connections=3",
    )
except Exception:
    # If Redis URL is invalid or unavailable at import time, fall back to
    # the memory limiter so the app still starts.
    auth_limiter = limiter
