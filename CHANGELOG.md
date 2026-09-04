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

### Phase 3 — Core Business (2026-09-04)

- Models: `Product`, `Inventory`, `StockMovement` (immutable audit log of every stock change),
  `Customer`, `Supplier`, `SupplierProduct`, `Order`, `OrderItem`, `Invoice`, `InvoiceItem`,
  `Payment`, `PurchaseOrder`, `PurchaseOrderItem`. Migration `54c4b61cdb48` generated via
  `--autogenerate` and reviewed by hand.
- Deterministic services (`app/services/`, unit-tested, no DB/LLM): `pricing.py` (line totals,
  rounding, tax — always 0 for MVP), `inventory_service.py` (stock-sufficiency/low-stock
  checks), `invoicing.py` (invoice number formatting), `procurement.py` (supplier ranking:
  active-first, then cheapest, then shortest lead time).
- API: full CRUD for products (auto-creates inventory), customers, suppliers (+
  supplier-product price/lead-time links + `/compare`); inventory listing/adjustment (every
  adjustment logs a `StockMovement`); order creation (stock check → decrement → invoice
  generation, all in one transaction) and cancellation (restores stock, voids invoice); invoice
  payments (partial → full → `PAID`, overpayment rejected); purchase order lifecycle
  (draft → send → receive-increments-stock, with price fallback to `supplier_products`).
- Role gating (`docs/decisions.md` ADR-016): products/suppliers/inventory-adjustments/purchase-
  orders restricted to OWNER/ADMIN; customers/orders/payments open to any role per spec §4's
  "routine operations" grant to employees. Purchase orders implement only the non-approval
  lifecycle for now (ADR-015) — full approval gating is Phase 5.
- Tests: 83 passing total (54 new) — 13 more unit (pure deterministic-service tests), 32 more
  integration (every domain's CRUD + the order/invoice/purchase-order flows above), 3 more
  security (cross-business resource isolation for products/orders/purchase-orders, proving a
  resource id from another business 404s under your own membership context, not just that
  business-level access is blocked).
- Verified end-to-end via live HTTP calls against the running Docker stack: register → create
  business → create product → adjust stock → create order (stock decremented, invoice
  generated with correct total) → compare supplier prices → create purchase order → send →
  receive (stock incremented) — all matched expected values.
- Docs updated: `api.md` (every new endpoint), `database.md` (new tables + ERD),
  `workflows.md` (order-processing and procurement flow diagrams, filled in from placeholder),
  `troubleshooting.md` (a Windows Docker-networking quirk hit and fixed during this phase —
  host→published-port connections occasionally need `docker compose restart <service>`; worked
  around for migrations by running Alembic through the container instead of the host venv).
- Known limitations carried forward explicitly (not silently skipped): no partial invoicing, no
  partial PO receipt, no tax engine, no frontend pages for these domains yet (ADR-013 — parked
  until Phase 4 needs them to show agent activity against), invoice numbering has a known race
  condition under concurrent creation (ADR-014).

### Next: Phase 4 — AI Employee

Agent orchestrator, Order Agent, Inventory Agent, tool registry, structured outputs, agent
state — with tests.
