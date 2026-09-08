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

### Phase 4 — AI Employee (2026-09-05)

- LLM abstraction (`app/core/llm/`): provider-neutral `LLMProvider.generate` interface
  (ADR-005), `OpenAIProvider` (function calling; all failures mapped to structured responses),
  `MockProvider` (scripted + keyword rules — deterministic, keyless), factory with
  openai-without-key falling back to mock (ADR-019). Anthropic/Gemini stubs raise
  `NotImplementedError`.
- Tool registry (`app/tools/`, ADR-003): 13 schema-validated, permissioned tools wrapping the
  Phase 3 services; every call validates args + role server-side, classifies risk
  deterministically, and persists an `agent_actions` row (FR-14) with compact JSON-safe
  summaries — never raw chain-of-thought.
- Agents (`app/agents/`): LangGraph orchestrator (classify → route → workflow) plus Order,
  Inventory (check/low-stock), Procurement (compare + direct/low-stock-driven PO), Customer,
  Finance/Reporting, Policy (risk seam), and Verification (FR-19 re-reads state, re-checks the
  math) workflows — all registry-only data access, per-request step cap (NFR-3).
- Order/PO creation extracted from the API endpoints into `app/services/order_service.py` /
  `purchase_order_service.py` so REST and agent tool paths share one deterministic code path;
  `app/services/reporting.py` for the sales summary.
- Persistence: `agent_sessions`/`agent_tasks`/`agent_actions` models + migration
  `f2c2e0ac428e`; chat API `POST /api/agent/chat`, `GET /api/agent/sessions[/{id}]`
  (FR-11/14/15, ADR-020).
- Frontend: shared nav layout, **AI Employee chat page** (examples, structured result tables,
  recent-activity sidebar) and the deferred Phase 3 domain pages — Orders, Inventory,
  Suppliers (with product links), Purchase Orders — wired to the live API via TanStack Query.
  Fixed the pre-existing `tsc -b` build break on TypeScript 5.9 (TS6310) by splitting the
  typecheck per tsconfig.
- Tests: 125 total (42 new) — unit (providers/registry/risk), `tests/agents/` (scripted
  workflow end-to-end), and chat API integration (incl. tenant isolation of sessions and role
  denial through the agent path). Fixed a pytest-asyncio 0.24.0 crash on this Windows box (the
  redefined-event_loop introspection bug) in `tests/conftest.py`; engine disposal moved into
  the loop fixture so asyncpg teardown can never outlive its loop.
- Docs: `agents.md`/`tools.md` filled in from placeholders, `api.md`/`database.md`/
  `testing.md` updated, ADRs 017–020 added, DoD checklist updated. `.env.example` defaults
  `LLM_PROVIDER=mock` and documents `MAX_AGENT_STEPS`.
- Known limitations carried forward explicitly: workflow resume/memory is Phase 5+ (ADR-020);
  the policy engine (thresholds, approval requests) is Phase 5 (ADR-004 seam); no frontend
  automated tests yet.

### Phase 5 — Approval & Policies (2026-09-08)

- Policy engine (`app/policies/`, FR-16/FR-17, ADR-004): `business_policies` rows are stored via
  the API but evaluated **deterministically** in plain Python (`app/policies/policies.py`) —
  never by the LLM. `MONEY_THRESHOLD` computes the *projected* money impact of a proposed
  create-order / create-purchase-order write and escalates MEDIUM → HIGH when it meets the
  (smallest active) threshold; `APPROVAL_ROLES` configures which roles may decide approval
  requests (default OWNER/ADMIN). `evaluate_risk` is what the tool registry and approval
  pipeline actually call; `classify_action` remains the pure Phase 4 classifier.
- Approval workflow (FR-18): the tool registry stops HIGH-risk agent actions before execution
  and opens an `approval_requests` row (payload = the proposed arguments, never chain-of-
  thought). `POST /api/approvals/{id}/approve|reject` is the human decision path, role-gated by
  `APPROVAL_ROLES`. There is no code path for an agent (or the requester) to approve its own
  request. Purchase orders proposed at HIGH are created in `PENDING_APPROVAL` with the request
  targeting them; deciding transitions the PO to `APPROVED`/`CANCELLED` (FR-9, ADR-015).
- Unified audit log (FR-25): `audit_logs` table captures **all** state changes — every REST
  write (auth, businesses, policies, approvals) and every registry tool call appends a row via
  `app/services/audit_service.py`; read-only `GET /api/audit` for any member. Complements (does
  not replace) the agent-path `agent_actions` trail.
- API: `GET/PUT /api/policies`, `GET /api/approvals[/{id}]`, `POST .../approve|reject`,
  `GET /api/audit`. Purchase orders gained `PENDING_APPROVAL`/`APPROVED` states; a
  `PENDING_APPROVAL` PO cannot be sent until decided.
- Models/migration: `business_policies`, `approval_requests`, `audit_logs` + enum additions
  (`purchase_order_status`: PENDING_APPROVAL/APPROVED; `agent_action_status`: PENDING) in
  migration `d2e271d74b0f`.
- Frontend: Policies page (upsert/enable MONEY_THRESHOLD and APPROVAL_ROLES), Approvals page
  (list + approve/reject with decision note, PENDING badge), PO pages reflect the new states.
  Wired via `src/api/governance.ts` + `src/types/governance.ts`.
- Tests: 140 passing total (15 new) — 6 unit (policy engine: threshold escalation, money-impact
  projection, approval-role defaults), 9 integration (policies API CRUD/role gating; approval
  workflow: HIGH-risk PO parked PENDING_APPROVAL + not sendable, approve → APPROVED → sendable,
  employee cannot approve HIGH, reject → PO CANCELLED). Frontend `npm run build` clean.
- Docs updated: `api.md` (policies/approvals/audit endpoints + PO states), `database.md`
  (Phase 5 tables + enum additions), `testing.md` (new coverage), `workflows.md` (approval-
  gated PO flow), `agents.md` (policy engine no longer future), `decisions.md` DoD checklist.
- Known limitations carried forward: approval is request-level (no multi-stage/chained approval
  yet); the audit log has no filtering UI beyond the API; no `notifications` for pending
  approvals (Phase 7).

### Phase 6 — Proactive Intelligence (2026-09-08)

- Deterministic demand forecasting (`app/services/forecasting.py`, FR-13): per-product daily
  sales series from confirmed orders, simple moving average over the trailing 14 days to
  project daily demand, and days-until-stockout = ceil(on_hand / projected_daily). At-risk =
  stockout before the fastest active supplier lead time. Pure Python math — never the LLM;
  the pure functions are unit-tested without a DB.
- APScheduler worker (`app/worker/main.py`, ADR-007/A5): a `worker` service (own Docker
  Compose container, `docker/worker.Dockerfile`) running three deterministic jobs via
  `app/services/worker_jobs.py` — low-stock scan, forecasted-stockout scan (both
  `run_scheduled_checks`, every `SCHEDULER_CHECK_INTERVAL_MINUTES`), and a daily report
  (`SCHEDULER_DAILY_REPORT_HOUR` UTC). Checks run per business; each notification dedupes per
  (type, target) within a 12h lookback so a persistent issue isn't re-flagged every tick. Any
  resulting *action* still flows through the policy/approval pipeline — the worker never
  bypasses it (FR-24).
- Notifications (FR-24, A6): `notifications` model + migration `05beb7c32bed` (types
  LOW_STOCK/FORECASTED_STOCKOUT/APPROVAL_PENDING/DAILY_REPORT; severities INFO/WARNING/
  CRITICAL). `app/services/notification_service.py` writes the IN_APP row always and a
  MOCK_* channel row for the messaging mock (no real provider credentials). Read-only
  `GET /api/notifications` (type filter, in-app-only default, tenant-scoped).
- Frontend: **Alerts page** (`/alerts`) listing notifications with severity styling and a
  type filter, wired via `src/api/governance.ts` + governance types; added to nav.
- Tests: 156 passing total (16 new) — 9 unit (forecasting math), 7 integration (worker jobs
  against seeded rows: low-stock notification + dedupe, healthy products ignored, stockout
  CRITICAL from real order history, daily report, notifications API filtering + tenant
  isolation, multi-business `run_scheduled_checks`). Frontend `npm run build` clean.
- Docs updated: `workflows.md` (proactive checks), `database.md` (notifications table +
  migration list), `api.md` (notifications endpoint), `testing.md` (new coverage),
  `.env.example` (scheduler settings), CHANGELOG.
- Known limitations carried forward: forecasting uses a flat 14-day moving average (no
  seasonality/trend); notifications have no read/unread state (read model is the frontend);
  the worker runs in-process (no distributed queue — scaling seam per ADR-007).

### Phase 7 — RAG, Documents & MCP (2026-09-08)

- Documents & RAG (FR-21/22/23, ADR-006): `documents` + `document_chunks` (pgvector, HNSW
  index) models + migration `abf9dcb55aed`. `POST /api/documents` uploads text-based files
  (content-type allow-list + 2 MiB limit, OWNER/ADMIN) and runs the deterministic pipeline in
  one transaction: `app/services/chunking.py` (paragraph + word-boundary split with exact
  source spans), `app/core/llm/embeddings.py` (provider-neutral `EmbeddingProvider` —
  OpenAI text-embedding-3-small, mock = deterministic hash vectors so tests/CI need no key),
  `app/rag/retriever.py` (business-scoped pgvector cosine similarity).
- Cited, grounded answers (`app/rag/answer.py`): retrieved top-k chunks are wrapped in a
  delimited `<business_documents>` untrusted block before the LLM reasons over them (FR-23,
  threat-model T1); answers cite source documents (FR-22). Surfaced via `POST
  /api/documents/query`, the AI Employee chat intent `ASK_DOCUMENTS` (RAG agent workflow,
  `app/agents/workflows/rag.py`), and the frontend **Documents** page (`/documents` —
  upload/list/delete + "Ask your documents" with cited sources).
- Minimal read-only MCP server (`app/mcp/server.py`, ADR-010/A7): JSON-RPC 2.0 over HTTP at
  `POST /mcp`, same JWT + X-Business-Id auth/business scoping as the REST API. Exposes only a
  small read-only tool subset (`tools/list`/`tools/call`); calls run through the registry so
  validation, role checks, and the audit trail all apply; each call records a session/task.
- Tests: 174 passing total (18 new) — 8 unit (chunking spans/hard-split, mock embedding
  determinism/dim), 10 integration (upload → chunks, content-type/empty/role validation,
  list/detail/delete, business-scoped retrieval isolation, RAG query answer + sources, MCP
  tools/list subset, tools/call through registry, write-tool + bad-auth rejection). Frontend
  `npm run build` clean.
- Docs updated: `rag.md` + `mcp.md` filled from placeholders, `api.md` (documents/RAG/MCP),
  `database.md` (Phase 7 tables + migration), `testing.md`, `security.md` (file-upload
  validation now implemented), `workflows.md` (document Q&A flow), `agents.md` (RAG workflow),
  `decisions.md` DoD (RAG, prompt-injection, MCP) + `README.md`, `.env.example`
  (`EMBEDDING_MODEL`), CHANGELOG.
- Known limitations carried forward: binary document formats (PDF/DOCX) need extraction tooling
  (out of MVP scope, docs/security.md); embeddings require an OpenAI key for *real* semantic
  search (mock is keyword-free deterministic vectors); RAG answers are single-shot (no
  multi-turn document conversation).

### Phase 8 — Hardening & Polish (2026-09-08)

- **Rate limiting** (`app/security/rate_limit.py`): in-process per-IP fixed-window limits on
  `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh` (10/10/30 per 60s) and
  `/api/agent/chat` (20 per 60s); 429 on overflow. `reset_rate_limits()` wired into the test
  conftest so tests start with a clean budget. Per-instance — a distributed limiter is a
  documented scaling seam.
- **Refresh-token rotation** (`app/models/refresh_token.py`, `app/services/
  refresh_token_service.py`, migration `b1244bf28ccb`): opaque tokens stored as SHA-256 hashes
  only; `POST /api/auth/refresh` validates + rotates (revoke old, issue new) so a replayed/
  leaked token is rejected on second use; `POST /api/auth/logout` revokes. Register/login now
  return `refresh_token`; frontend stores it and refreshes/revokes accordingly.
- **Seed/demo data** (`python -m app.seed`): creates a demo business — owner, 5 products +
  inventory (incl. a low-stock item the worker/alerts find), 3 customers, 3 suppliers with
  price links, a paid order + invoice, a draft PO, and a document for RAG. Idempotent.
- **Frontend lint + tests**: added `eslint.config.js` (flat config, `@typescript-eslint` +
  react-hooks + browser globals) — `npm run lint` previously failed with no config; now 0
  errors. Added Vitest + Testing Library (`npm test`): token-storage helpers and AlertsPage
  render/empty states. `npm run build` clean.
- **Structured logging (FR-26)**: `app/core/logging.py` — key=value formatter; the http
  middleware logs every request with `request_id`; agent runs log `session_id`/`task_id`/
  `intent`/`status`.
- **Deployment + docs**: `deployment.md` filled in (verified local Docker-Compose path + a
  documented hosted plan for Postgres/backend+worker/frontend); `security.md` updated (controls
  now implemented vs. roadmap); `api.md` (refresh/logout + rate limits), `database.md`
  (`refresh_tokens` + migration), `testing.md` (181 backend + 4 frontend), `decisions.md` DoD
  (all checked through Phase 8), `threat-model.md` re-read against the built system (T1–T6
  verified), README + CHANGELOG.
- Tests: **181 backend** (7 new hardening: rotation/replay/logout/hashed-storage, 429 on
  register + refresh, reset) + **4 frontend**. Frontend build + lint + test all green.

Phase 8 completes the MVP scope. All `docs/decisions.md` Definition-of-Done items are checked.
Remaining roadmap (not MVP): distributed rate limiter, virus scanning, WAF/anomaly detection,
secrets rotation automation, penetration testing, multi-instance hosting (docs/security.md).

## [Unreleased]
