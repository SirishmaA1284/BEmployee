# Contributing

## Process

- Every architectural decision that deviates from `docs/requirements.md`/`docs/architecture.md`
  is logged as a new ADR in `docs/decisions.md` — don't silently diverge.
- Every feature ships with tests at the appropriate layer(s); see `docs/testing.md`.
- No LLM-reachable code path may access the database directly; all data access goes through
  `backend/app/tools/` (see `docs/decisions.md` ADR-003).
- Update `CHANGELOG.md` and the relevant `docs/*.md` file(s) in the same change that adds the
  feature, not as a follow-up.

## Commit style

Small, focused commits per phase/feature. Migrations are never hand-edited after being merged
to `main` — a schema change is a new migration.
