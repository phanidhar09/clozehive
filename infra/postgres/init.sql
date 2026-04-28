-- PostgreSQL initialisation — runs once when the container is first created.
-- Alembic handles all actual table creation; this just sets up extensions.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- ILIKE index support for user search
CREATE EXTENSION IF NOT EXISTS "vector";    -- pgvector semantic search
