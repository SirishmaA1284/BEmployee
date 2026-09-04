# Testing Strategy

Status: design-level now; commands and coverage details added as each phase ships tests.

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
