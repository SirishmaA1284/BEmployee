# Changelog

All notable changes to this project are documented here, phase by phase (see
`docs/decisions.md` §"Development Process" / roadmap).

## [Unreleased]

### Phase 1 — Analysis & Architecture (2026-09-04)

- Added `docs/requirements.md`, `docs/architecture.md`, `docs/decisions.md` covering product
  requirements, system/agent/approval/RAG/auth architecture diagrams, and the ADR log
  including MVP scope assumptions.
- Added `docs/threat-model.md` with the prompt-injection and multi-tenancy threat analysis
  that later phases implement against.
- Added placeholder docs for `setup`, `development`, `api`, `database`, `agents`, `tools`,
  `mcp`, `rag`, `security`, `authorization`, `workflows`, `testing`, `deployment`,
  `troubleshooting`, `contributing` — filled in as the corresponding phase ships.
- Scaffolded monorepo directory structure (`backend/app/{api,agents,tools,workflows,models,
  schemas,services,policies,security,rag,database,core}`, `backend/tests/{unit,integration,
  agents,security}`, `frontend/src/{pages,components,api,hooks,types,store}`, `docs/`,
  `scripts/`, `docker/`).
- Added root `README.md`, `LICENSE` (MIT), `.env.example`, `.gitignore`, and a
  `docker-compose.yml` skeleton (Postgres w/ pgvector; backend/frontend/worker services to be
  filled in during Phase 2).

No application code yet — this phase is documentation and repository structure only.

### Next: Phase 2 — Foundation

Docker services, database schema + migrations, authentication, business/user model, basic
frontend shell, API foundation.
