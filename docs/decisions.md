# Architecture Decision Log

Format: short ADRs. Newest at bottom. Numbering is sequential, not per-phase.

## ADR-001: Monorepo layout follows the brief's suggested structure

**Decision:** Use `frontend/`, `backend/app/{api,agents,tools,workflows,models,schemas,
services,policies,security,rag,database,core}`, `backend/tests/`, `docs/`, `scripts/`,
`docker/` as proposed in the spec, with no additional top-level services.

**Why:** The brief explicitly allows deviation if documented, but the proposed structure
already matches the layered architecture (API → agents → tools → data) we need, and avoids
inventing structure for its own sake (Rule 7/8).

## ADR-002: LangGraph for agent orchestration, one graph per workflow

**Decision:** Each multi-step workflow (order creation, low-stock → procurement, daily report)
is a LangGraph `StateGraph` with explicit nodes per agent step and typed state. The
Orchestrator Agent is the entry graph that routes to sub-graphs/nodes based on classified
intent (not free-form LLM improvisation of control flow).

**Why:** Requirement is "genuine agentic behavior" with deterministic, auditable state
transitions — not an open-ended ReAct loop. LangGraph gives us inspectable state and resumability
for `agent_sessions`/`agent_tasks` persistence.

## ADR-003: Tools are the only DB access path reachable from agent/LLM code

**Decision:** Agent modules (`backend/app/agents/`) never import SQLAlchemy sessions or
models directly. They only call functions from `backend/app/tools/`, which internally use
`backend/app/services/` for business logic and `backend/app/database/` for persistence. Tool
functions independently validate all arguments (existence, ownership by the caller's
`business_id`, type/range) regardless of what the LLM's structured output claims.

**Why:** Rule 3 ("Do not allow the LLM to directly modify the database") and Rule 11
("independently validated by backend code") are non-negotiable. Structural enforcement (not
just code review) is the only reliable way to guarantee this over time.

## ADR-004: Deterministic risk classification and policy evaluation, not LLM judgment

**Decision:** `backend/app/policies/` contains plain Python rule evaluation (money thresholds,
supplier-active checks, quantity minimums, messaging-hour windows) operating on structured
inputs. The LLM may *propose* an action and a natural-language justification, but whether it
requires approval is decided by this deterministic layer, which cannot be short-circuited by
prompt content.

**Why:** Section 10/23 requirements — approval and safety rules must not depend on LLM
interpretation.

## ADR-005: LLM provider = OpenAI default, others as adapters, Mock for tests

**Decision:** `backend/app/core/llm/` defines `LLMProvider` (async `complete`/`structured_call`
interface). `OpenAIProvider` is the default and the only one wired to a real SDK at MVP launch.
`AnthropicProvider` and `GeminiProvider` are implemented against the same interface but may be
thin/stubbed until credentials are available. `MockProvider` returns deterministic canned
responses and is used in all automated tests and CI so the suite never depends on a live API
key or network access.

**Why:** User's explicit choice (OpenAI default) + Rule "cheaper models for simple tasks,
stronger for complex reasoning" + NFR-5 testability without API costs/network flakiness.

## ADR-006: pgvector instead of a standalone vector database

**Decision:** RAG uses the `vector` extension on the same PostgreSQL instance
(`document_chunks.embedding vector(n)`), not a separate Chroma/Qdrant/Pinecone service.

**Why:** User's explicit choice; also matches Rule 8 (don't add tech to look impressive) and
Rule 7 (no unnecessary services) — MVP document volume does not need a dedicated vector DB.

## ADR-007: APScheduler in-process worker instead of Celery/Redis

**Decision:** Proactive/background jobs (low-stock scan, daily report, follow-up detection)
run via APScheduler inside a single `worker` service (own Docker Compose container, same
codebase as the API) rather than adopting a task queue + broker.

**Why:** MVP scale doesn't need distributed task queuing; introducing Redis/Celery is exactly
the kind of "technology added to look impressive" the brief warns against (Rule 8). The
worker calls the same orchestrator/agent code the API does, so scaling to a real queue later is
a swap of the trigger mechanism, not a rewrite. This is a documented scaling seam, not a
production-hardening claim.

## ADR-008: JWT auth, no session store, roles = OWNER/ADMIN/EMPLOYEE

**Decision:** Stateless JWT (short-lived access token; refresh handled by re-login for MVP —
no refresh-token rotation yet). Role is stored per `(user_id, business_id)` in
`business_members`, not globally on `users`, since one user can hold different roles in
different businesses.

**Why:** Matches multi-tenancy requirement (Section 21) directly; refresh-token rotation is
flagged as a Phase 8/production-hardening item, not MVP-blocking.

## ADR-009: Soft delete only where historical references exist

**Decision:** `deleted_at` nullable timestamp on `products`, `customers`, `suppliers` (referenced
by historical orders/POs/invoices). Draft-only rows with no cross-references
(e.g. an unsent purchase order draft) use hard delete.

**Why:** Preserves referential integrity of historical financial/inventory records (a deleted
product must still render correctly on a 3-month-old invoice) without soft-deleting everything
by default, which would complicate every query with a `deleted_at IS NULL` filter for no
benefit.

## ADR-010: MCP is designed now, minimally implemented later (Phase 7)

**Decision:** Tool schemas (Phase 4) are written in a provider-neutral shape from the start
(name/description/JSON-schema input/output) so they can be re-exposed via an MCP server without
redesign. The actual MCP server process ships in Phase 7 and exposes a deliberately small,
read-mostly subset (e.g. `get_sales_report`, `search_products`) — not the full internal tool
registry — to keep the external attack surface small.

**Why:** Section 8 explicitly says not to add MCP "because it's trendy," and Rule 9/10 (every
action auditable, high-risk actions need approval) means any externally-triggered write must
still flow through the same approval pipeline — which argues for starting read-only.

## ADR-011: License = MIT

**Decision:** Root `LICENSE` is MIT.

**Why:** No stated constraint from the user; MIT is the least-friction default for a portfolio/
demo-style MVP repository.

## ADR-012: Single currency, single location for MVP

**Decision:** `orders`/`invoices`/`purchase_orders` store amounts in a single business-level
currency (default INR/₹, configurable per business as a string code for future use).
`inventory` is keyed by `(business_id, product_id)` with no warehouse/location dimension.

**Why:** Matches assumption A1/A2 in `docs/requirements.md`; multi-location is a documented
roadmap item, not implemented speculatively (Rule "don't design for hypothetical future
requirements").

## Definition of Done (tracked here verbatim, checked off per phase)

- [ ] User can register/login
- [ ] Business can be created
- [ ] Products can be created
- [ ] Inventory works
- [ ] Customers work
- [ ] Orders work
- [ ] Invoices work
- [ ] Suppliers work
- [ ] Purchase orders work
- [ ] AI employee interface works
- [ ] Agent can execute an order workflow
- [ ] Agent can check inventory
- [ ] Agent can identify low stock
- [ ] Agent can compare suppliers
- [ ] Agent can prepare purchase orders
- [ ] Approval workflow works
- [ ] Policies work
- [ ] Audit logs work
- [ ] Agent actions are observable
- [ ] RAG works for business documents
- [ ] Prompt-injection defenses exist
- [ ] Multi-tenant authorization works
- [ ] Unit tests exist
- [ ] Integration tests exist
- [ ] Agent tests exist
- [ ] Security tests exist
- [ ] Seed/demo data exists
- [ ] Docker setup works
- [ ] Documentation is complete
- [ ] README is complete
- [ ] `.env.example` exists
- [ ] Deployment instructions exist
