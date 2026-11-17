-- Phase 0 database bootstrap.
-- Extensions needed by later phases are enabled here so Alembic migrations
-- and integration tests can rely on them from the first run.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
