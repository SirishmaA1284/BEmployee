-- Runs once on first container start (docker-entrypoint-initdb.d).
-- Enables the pgvector extension used by RAG (docs/decisions.md ADR-006).
CREATE EXTENSION IF NOT EXISTS vector;

-- Separate database for the automated test suite (backend/tests), so tests
-- never run against dev data.
CREATE DATABASE ai_employee_test OWNER ai_employee;

\c ai_employee_test
CREATE EXTENSION IF NOT EXISTS vector;
