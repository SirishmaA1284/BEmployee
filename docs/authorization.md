# Authorization

Status: design-level now; implemented in Phase 2, extended per-domain in later phases.

## Roles

- `OWNER` — full control of a business (see spec §4).
- `ADMIN` — same as owner minus a small set of owner-only actions (billing/business deletion,
  TBD as those features are built).
- `EMPLOYEE` — routine operations only; cannot edit policies, cannot approve HIGH-risk actions.

## Model

- A user's role is per `(user_id, business_id)` via `business_members`, not global.
- Every authenticated request resolves an active `business_id` (from a header or the JWT's
  business claim) and the caller's role for that business before any handler logic runs.
- The AI Employee always acts within the requesting user's role/business context — see
  `docs/threat-model.md` T5. It has no standing permissions beyond that user.
- Approval authority for HIGH-risk actions defaults to `OWNER`/`ADMIN`; whether `EMPLOYEE` can
  approve MEDIUM-risk actions is a per-business policy setting (`business_policies`), not
  hardcoded.
- Multi-stage (chained) approval (Phase 9): an `APPROVAL_STAGES` policy (`{"stages": N}`)
  makes HIGH-risk requests require N sequential approvals. Stages resolve in order and
  consecutive stages must be decided by **different** people — the same user approving two
  stages in a row is rejected with 409. Roles per stage are copied from `APPROVAL_ROLES` at
  request creation, so later policy edits never change an open request.

## Enforcement Points

1. FastAPI dependency resolves `current_user` + `current_business` + `role` from the JWT.
2. A route-level permission check (decorator/dependency) rejects insufficient roles before the
   handler body runs.
3. Every query is filtered by the resolved `business_id` — never a client-supplied one.
4. Tool functions re-check permission independently of the calling agent's assumptions (defense
   in depth — see `docs/decisions.md` ADR-003).

## Testing

Cross-business and cross-role access attempts are covered in `backend/tests/security`
(Phase 8, seeded incrementally as each domain ships).
