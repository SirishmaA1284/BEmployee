# Testing Strategy

## Current coverage (through Phase 3)

83 backend tests, all passing against a real Postgres test database (`ai_employee_test`, see
`docs/setup.md`):
- `tests/unit/` (28): password hashing, JWT, plus Phase 3's deterministic services — pricing
  (line totals, rounding, tax=0), inventory sufficiency/low-stock math, invoice number
  formatting, supplier-offer ranking. All pure functions, no DB, no LLM.
- `tests/integration/` (45): register/login/me, business creation/membership; product CRUD +
  auto-created inventory + duplicate-SKU rejection; customer CRUD; supplier CRUD + price
  comparison ranking; inventory adjustment (incl. rejecting a negative result); the full order
  flow (stock check → decrement → invoice generation → cancel-restores-stock-and-voids-invoice);
  invoice payments (partial → full → PAID, overpayment rejected); purchase order lifecycle
  (draft → send → receive-increments-stock, price fallback to `supplier_products`, inactive-
  supplier rejection).
- `tests/security/` (10): cross-business member listing/invite blocked, role escalation
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
docker compose exec -e TEST_DATABASE_URL="postgresql+asyncpg://ai_employee:ai_employee@db:5432/ai_employee_test" backend python -m pytest -v
```

Frontend: no automated tests yet (Phase 2 shipped a minimal but real login/register/dashboard
flow, manually verified against the live backend — see `docs/decisions.md` changelog note on
why an in-session browser check wasn't possible). Frontend test tooling arrives when the UI
has enough surface area to be worth it (Phase 3+).

## Layers (per spec §29)

- **Unit tests** (`backend/tests/unit`): inventory/reorder math, pricing, policy evaluation,
  permission checks, risk classification — pure functions, no DB, no LLM.
- **Integration tests** (`backend/tests/integration`): order → inventory → invoice → audit;
  low stock → procurement → approval → purchase order. Real test database (Docker Compose test
  service), transactional rollback per test.
- **Agent tests** (`backend/tests/agents`): deterministic scenarios against the `MockProvider`
  LLM so agent graphs are tested without live API calls or nondeterminism.
- **Security tests** (`backend/tests/security`): unauthorized access, cross-business access,
  prompt injection attempts, tool argument abuse, approval bypass attempts.
- **End-to-end tests** (`frontend/tests`): critical user journeys through the UI (added once
  the frontend exists).

## Principles

- No test suite depends on a real LLM API key or network access (`MockProvider`, see
  `docs/decisions.md` ADR-005).
- Every new tool ships with at least one validation-failure test (bad args rejected
  independently of the LLM).
- Every new policy rule ships with a test proving both the "allowed" and "blocked" path.

Commands (`pytest`, `npm test`, etc.) will be documented here once the respective toolchains
are wired up in Phase 2.
