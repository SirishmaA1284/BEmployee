# Testing Strategy

## Current coverage (Phase 2)

29 backend tests, all passing against a real Postgres test database (`ai_employee_test`, see
`docs/setup.md`):
- `tests/unit/` (15): password hashing (bcrypt round-trip, salting, length limits), JWT
  (round-trip, expiry, tampering, wrong-secret rejection).
- `tests/integration/` (13): register/login/me flows including duplicate-email and
  wrong-password rejection; business creation (creator → OWNER), listing, member invite.
- `tests/security/` (6): cross-business member listing/invite blocked (403), employee cannot
  invite (role escalation blocked), missing/malformed `X-Business-Id` rejected (400),
  unauthenticated requests rejected (401). See `docs/threat-model.md` T4/T5.

Run with (from `backend/`, venv active, `db` container up and both databases migrated):
```bash
pytest -v
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
