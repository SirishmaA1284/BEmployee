# app/agents

LangGraph agents (Orchestrator, Order, Inventory, Procurement, Customer, Finance/Reporting,
Policy, Verification). Added in Phase 4. Rule: agent code never imports a DB session or ORM
model directly — it only calls functions from `app/tools`. See `docs/agents.md` and
`docs/decisions.md` ADR-002/ADR-003.
