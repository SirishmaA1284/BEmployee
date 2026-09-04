# app/services

Deterministic business logic (pricing, totals, reorder math, forecasting, supplier comparison,
report generation) used by both the plain CRUD API and the tool layer. Never delegated to the
LLM — see `docs/decisions.md` ADR-003/spec Rule 4. Added in Phase 3 onward.
