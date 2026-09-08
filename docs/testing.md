# Testing Strategy

## Current coverage (through Phase 7)

174 backend tests, all passing against a real Postgres test database (`ai_employee_test`, see
`docs/setup.md`):

- `tests/unit/` (73): password hashing, JWT, deterministic services — pricing (line totals,
  rounding, tax=0), inventory sufficiency/low-stock math, invoice number formatting,
  supplier-offer ranking; plus Phase 4: LLM provider interface + MockProvider (scripted and
  keyword rules) + provider factory selection/fallbacks, the tool registry contract
  (validation, role enforcement, structured errors, audit recording, compact JSON-safe
  summaries), and the deterministic risk classifier (read= LOW, writes = MEDIUM, PO gating to
  OWNER/ADMIN); plus Phase 5: the policy engine (money-threshold escalation, approval-roles
  defaults, projected money impact); plus Phase 6: forecasting math (moving-average demand,
  stockout projection, at-risk flags — pure functions, no DB); plus Phase 7: deterministic
  chunking (paragraph split, hard-split, exact source spans) and mock embedding (fixed-dim,
  deterministic, differs per text).
- `tests/integration/` (83): register/login/me, business creation/membership; product CRUD +
  auto-created inventory + duplicate-SKU rejection; customer CRUD; supplier CRUD + price
  comparison ranking; inventory adjustment (incl. rejecting a negative result); the full order
  flow (stock check → decrement → invoice generation → cancel-restores-stock-and-voids-invoice);
  invoice payments (partial → full → PAID, overpayment rejected); purchase order lifecycle
  (draft → send → receive-increments-stock, price fallback to `supplier_products`, inactive-
  supplier rejection); plus the **agent chat API**: full order via chat (with persisted
  session/task/actions audit trail and stock decremented), low-stock, supplier comparison,
  sales report + product search, unknown-request clarification, employee role denial on PO
  creation via chat (no PO left behind), sessions list/detail, and session tenant isolation
  across businesses; plus Phase 5: the policies API (upsert/list, role gating) and the full
  approval workflow — a money-threshold-escalated PO is created in `PENDING_APPROVAL` with a
  `HIGH` approval request and is **not** sent, approving it transitions the PO to `APPROVED`
  (then sendable), an employee cannot approve a `HIGH` request, and rejecting it leaves the PO
  `CANCELLED`; plus Phase 6: the worker jobs against seeded rows — low-stock scan creates
  `LOW_STOCK` notifications and dedupes within the lookback window, healthy products are
  ignored, the forecasted-stockout scan flags an at-risk product as `CRITICAL` (with real
  order history seeded), the daily report notification, notifications API filtering +
  tenant isolation across businesses, and `run_scheduled_checks` covering every business; plus
  Phase 7: document upload (chunks created from paragraphs, content-type + empty-file
  validation, OWNER/ADMIN gating), list/detail/delete, business-scoped retrieval (a chunk from
  another business can never match), RAG query returning a grounded answer + cited sources, and
  the MCP server — `tools/list` exposes only the read-only subset (no writes), `tools/call`
  runs a read tool through the registry with the audit trail, write tools and bad auth are
  rejected.
- `tests/agents/` (9): full LangGraph workflows driven by a scripted `MockProvider` against the
  real test database — order end-to-end (extract → resolve → create → verify → summarize),
  unknown-product error path, low-stock, supplier ranking, direct + low-stock-driven purchase
  orders (incl. verification re-reads), sales report, UNKNOWN→clarify routing, and the
  per-request LLM step cap.
- `tests/security/` (9): cross-business member listing/invite blocked, role escalation
  blocked, malformed/missing `X-Business-Id` rejected, unauthenticated requests rejected,
  cross-business resource isolation for products/orders/purchase-orders (a resource id from
  Business A 404s under Business B's membership context, not just business-level access is
  blocked). See `docs/threat-model.md` T4/T5.

Run with (from `backend/`, venv active, `db` container up and both databases migrated):
```bash
pytest -v
```

If host→Docker Postgres connections are flaky (see `docs/troubleshooting.md`), run the suite
through the backend container instead:
```bash
docker compose exec backend pip install -r requirements-dev.txt   # once
docker compose exec -e TEST_DATABASE_URL="postgresql+asyncpg://postgres:Chinki@db:5432/ai_employee_test" backend python -m pytest -v
```

Frontend: no automated tests yet; type-checking and production build (`npm run build`) gate
every change, and the Phase 4/5 pages were verified by building. Manual in-browser click-through
still needs a human pass at http://localhost:5173.

## Layers (per spec §29)

- **Unit tests** (`backend/tests/unit`): inventory/reorder math, pricing, policy evaluation,
  permission checks, risk classification, LLM provider behavior — pure functions, no DB, no
  LLM network calls.
- **Integration tests** (`backend/tests/integration`): order → inventory → invoice → audit;
  low stock → procurement → purchase order; the agent chat API end-to-end. Real test database,
  tables truncated before every test.
- **Agent tests** (`backend/tests/agents`): deterministic scenarios against the `MockProvider`
  LLM so agent graphs are tested without live API calls or nondeterminism.
- **Security tests** (`backend/tests/security`): unauthorized access, cross-business access,
  role denial through the agent path, tool argument abuse, approval bypass attempts (Phase 5).
- **End-to-end tests** (`frontend/tests`): critical user journeys through the UI (added once
  the frontend has automated test tooling).

## Principles

- No test suite depends on a real LLM API key or network access (`MockProvider`, see
  `docs/decisions.md` ADR-005). The provider factory falls back to mock when `openai` is
  configured without a key, so a fresh clone runs green.
- Every tool ships with at least one validation-failure test (bad args rejected independently
  of the LLM) and every state-changing workflow ships with a verification assertion.
- Every new policy rule ships with a test proving both the "allowed" and "blocked" path.

Windows note: the conftest uses a session-scoped event loop (asyncpg pool + Windows
compatibility) and marks it as pytest-asyncio-owned to avoid a 0.24.0 introspection bug — see
`backend/tests/conftest.py` comments.