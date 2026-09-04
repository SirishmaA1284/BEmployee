-- Runs once on first container start (docker-entrypoint-initdb.d).
-- Enables the pgvector extension used by RAG (docs/decisions.md ADR-006).
CREATE EXTENSION IF NOT EXISTS vector;
