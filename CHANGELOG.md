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

### Phase 2 — Foundation (2026-09-04)

- Backend: FastAPI app (`backend/app/main.py`) with CORS, request-ID middleware, `/health`.
- Database: async SQLAlchemy 2.0 (`asyncpg`) engine/session, `Base`/`UUIDPrimaryKeyMixin`/
  `TimestampMixin`. Models: `User`, `Business`, `BusinessMember` (+ `BusinessRole` enum:
  OWNER/ADMIN/EMPLOYEE, one role per user per business).
- Migrations: Alembic wired up (async env.py); initial migration generated via
  `--autogenerate` against a real Postgres instance, reviewed, and applied.
- Auth: `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`. bcrypt password
  hashing (72-byte-limit-aware), PyJWT access tokens. Login/register responses are
  identical-shaped on failure to avoid email enumeration.
- Businesses: `POST /api/businesses` (creator auto-assigned OWNER), `GET /api/businesses`,
  `GET/POST /api/businesses/members` (invite existing users; OWNER-only).
- Authorization: `get_current_user`, `get_current_membership` (resolves role from
  `X-Business-Id` header + server-side `business_members` lookup — never client-asserted),
  `require_role(...)` dependency factory. Every business-scoped query filters by the
  server-resolved `business_id`.
- Tests: 29 passing against a real Postgres test database (`ai_employee_test`) — 15 unit
  (password hashing, JWT), 13 integration (auth + business flows), 6 security/multi-tenancy
  (cross-business access blocked, role escalation blocked, missing/malformed business header
  rejected, unauthenticated requests rejected). See `docs/testing.md`.
- Docker: `docker-compose.yml` now brings up `db` (Postgres+pgvector, remapped to host port
  5433 to avoid colliding with other local Postgres instances — see
  `docs/troubleshooting.md`), `backend`, and `frontend`, each with a `Dockerfile` under
  `docker/`. Verified end-to-end: built and ran all three containers, confirmed `/health` and
  the frontend dev server respond on the host, and confirmed `docker compose exec backend
  alembic upgrade head` works as documented.
- Frontend: React + TypeScript + Vite + Tailwind + React Router + TanStack Query. Real
  (not placeholder) login, register, and dashboard pages wired to the live backend — register/
  login, JWT stored client-side, create-business form, business switcher
  (`X-Business-Id` sent on every request). Verified against the live backend via direct API
  calls and `npm run build` (type-checks and builds cleanly); a real in-browser click-through
  could not be done this session because the Claude-in-Chrome extension wasn't connected — flagged
  for the user to spot-check at http://localhost:5173.
- Docs updated with real (not placeholder) content: `setup.md`, `development.md`, `api.md`,
  `database.md`, `testing.md`, `troubleshooting.md`; `decisions.md` Definition-of-Done
  checklist updated for what's actually done.

### Next: Phase 3 — Core Business

Products, inventory, customers, orders, invoices, suppliers, purchase orders — with tests.
