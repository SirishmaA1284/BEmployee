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

## ADR-013: Phase 3 is backend + tests only, no new frontend domain pages

**Decision:** Phase 3 (Core Business) implements products, inventory, customers, suppliers,
orders, invoices, and purchase orders as API + services + tests only. The frontend keeps its
Phase 2 auth/business/dashboard pages; Orders/Inventory/Suppliers/Purchase Orders pages are
built alongside the AI Employee chat interface in Phase 4, where they're most useful (seeing
what the agent did).

**Why:** The spec's own Phase 3 description (§40) lists only backend work ("with proper
tests"); frontend domain pages are listed under §18 without a phase binding. Building seven
CRUD UIs before the AI employee exists to act on them would be UI for its own sake this early —
better to spend that effort once Phase 4 needs real data to display AI actions against.

## ADR-014: Single-invoice-per-order, zero tax, sequential invoice numbering for MVP

**Decision:**
- One invoice is generated synchronously per order at creation time (`invoices.order_id` is
  unique) — no partial/split invoicing in MVP, even though `invoice_items` exists as its own
  table (mirrors `order_items` 1:1 today, ready for partial invoicing later without a schema
  change).
- `tax_amount` is stored per order/invoice but computed as `0` for MVP — no tax engine.
  `docs/requirements.md` A1 already scopes MVP to a single currency; tax logic is genuinely
  business/jurisdiction-specific and out of scope until a real requirement names a scheme.
- Invoice numbers are `INV-{business-scoped sequential count}`, computed as
  `count(existing invoices for business) + 1` inside the creating transaction. This has a known
  race condition under concurrent order creation for the same business (two simultaneous
  requests could compute the same count) — acceptable for MVP's synchronous, low-concurrency
  usage pattern; a production hardening pass would use a DB sequence or `SELECT ... FOR UPDATE`
  per business.

**Why:** Matches Rule 4 (deterministic backend calculation, never LLM) and avoids building tax/
partial-invoicing machinery nobody has asked for yet (no premature abstraction).

## ADR-015: Purchase orders implement only the non-approval lifecycle in Phase 3

**Decision:** `PurchaseOrderStatus` for Phase 3 is `DRAFT → SENT → COMPLETED`, plus
`CANCELLED`. The `PENDING_APPROVAL`/`APPROVED` states from FR-9 are added as an enum + workflow
change in Phase 5 when the policy/approval engine exists to actually gate them. Until then,
creating and sending a purchase order is restricted to `OWNER`/`ADMIN` roles (interim
safeguard, not a substitute for the real approval gate) rather than left open to `EMPLOYEE`.

**Why:** Adding unused enum states/workflow branches before the approval engine exists to drive
them would be dead code (Rule 6 spirit — don't build machinery nothing calls yet); this is
tracked explicitly here so Phase 5 knows to revisit both the enum and the role restriction.

## ADR-016: Role gating for Phase 3 write operations

**Decision:**
- Products, suppliers, supplier-product links, inventory adjustments, purchase orders:
  `OWNER`/`ADMIN` only for writes; any role can read.
- Customers, orders, invoice payments: any role (including `EMPLOYEE`) can write — these are
  the "routine operations" spec §4 explicitly grants employees.
- Order cancellation: `OWNER`/`ADMIN` only (reverses stock and voids a financial document —
  treated as more sensitive than creating one).

**Why:** Direct application of spec §4's Owner/Employee capability split, made concrete where
the spec is silent on a specific action; documented so Phase 5's real risk-classification layer
has a stated starting point to formalize rather than invent from scratch.

## ADR-017: LangGraph graphs are built per request; nodes return state updates, never mutate

**Decision:** The orchestrator and every workflow graph are compiled per chat request, with
the request's DB session and LLM provider closed over by the node functions. Agent state is a
plain JSON-serializable `TypedDict`. LangGraph 1.x passes nodes a shallow copy of state, so
nodes never mutate top-level keys — every update (including errors, `llm_calls`, scratch ids)
is merged via the node's return dict. Nested shared objects (e.g. `tool_results`) are the
documented exception.

**Why:** Matches ADR-002's "typed state, explicit nodes" without paying for cross-request
persistence we don't use yet (checkpointing/resume is Phase 5–6). Making the mutation rule
explicit in code (helpers return partial-state updates) turned a subtle LangGraph behavior into
a tested convention instead of a bug source.

## ADR-018: Entity extraction is a prompt-layer tool call, not a registry tool

**Decision:** Intent classification and entity extraction (customer name, product lines,
quantities, supplier name) are structured LLM calls whose single "tool" (`classify_intent`,
`extract_order`, …) is defined in `app/agents/` and validated against a Pydantic schema before
routing. These virtual tools are NOT in the registry, never touch the database, and are not
audited as agent actions — the actions that matter (searches, writes) are.

**Why:** Keeps the registry's audit trail meaningful (business-data operations only, FR-14) and
keeps extraction logic next to the prompts that use it. The LLM proposes *what* to do; ids,
prices and stock are always resolved from registry results, never invented (ADR-003/004).

## ADR-019: openai-without-key falls back to MockProvider; mock is the CI/demo default

**Decision:** `LLM_PROVIDER=mock` is the documented default (`.env.example`). Selecting
`openai` without `OPENAI_API_KEY` also returns the MockProvider instead of failing, so a fresh
clone and the test suite always run green and demos work offline. Anthropic/Gemini remain
stubs that raise `NotImplementedError`.

**Why:** ADR-005's testability requirement, applied to the whole app rather than just tests.

## ADR-020: Chat runs synchronously in-request; persistence is for inspection now, resume later

**Decision:** `POST /api/agent/chat` runs the full agent cycle within the HTTP request and
returns the reply + structured result. Sessions/tasks/actions are persisted for audit and
observability (FR-14/FR-15). Workflow *resumption* (pick up a failed task, continue a
conversation with memory) is not implemented — it lands with LangGraph checkpointing in a
later phase rather than bolting a half-designed resume path on now.

**Why:** Matches the phase scope (observability is a Phase 4 DoD item; resume/memory is not)
and avoids building resumability machinery nothing calls yet (Rule 6 spirit).

## Definition of Done (tracked here verbatim, checked off per phase)

- [x] User can register/login (Phase 2)
- [x] Business can be created (Phase 2 — creator is auto-assigned OWNER)
- [x] Products can be created (Phase 3)
- [x] Inventory works (Phase 3 — tracked via immutable `stock_movements`, not just a counter)
- [x] Customers work (Phase 3)
- [x] Orders work (Phase 3 — stock check, decrement, invoice generation, cancellation)
- [x] Invoices work (Phase 3 — auto-generated per order, payments, PAID/VOID transitions)
- [x] Suppliers work (Phase 3 — incl. price comparison ranking)
- [x] Purchase orders work (Phase 3 — draft/send/receive/cancel; approval gating is Phase 5,
  see ADR-015)
- [x] AI employee interface works (Phase 4 — `/api/agent/chat` + chat UI; MockProvider default
  so it works without an API key, OpenAI when configured)
- [x] Agent can execute an order workflow (Phase 4 — extract → resolve → create → verify →
  summarize; tests in `backend/tests/agents`)
- [x] Agent can check inventory (Phase 4)
- [x] Agent can identify low stock (Phase 4)
- [x] Agent can compare suppliers (Phase 4 — same deterministic ranking as the REST endpoint)
- [x] Agent can prepare purchase orders (Phase 4 — direct and low-stock-driven; OWNER/ADMIN
  gated via the tool registry)
- [ ] Approval workflow works
- [ ] Policies work
- [ ] Audit logs work (agent_actions audit trail exists from Phase 4; the unified
  `audit_logs` table for ALL state changes lands in Phase 5)
- [x] Agent actions are observable (Phase 4 — sessions/tasks/actions API + activity sidebar)
- [ ] RAG works for business documents
- [ ] Prompt-injection defenses exist
- [x] Multi-tenant authorization works (Phase 2 for auth/business scope, Phase 3 extended to
  every business-owned resource — resource ids from another business 404 under your own
  membership context; Phase 4 extended to agent sessions; see `backend/tests/security` +
  `tests/integration/test_agent_chat.py`)
- [x] Unit tests exist (Phase 2 — passwords, JWT; Phase 3 — pricing/inventory/invoicing/
  procurement math; Phase 4 — providers, registry, risk; extended per phase)
- [x] Integration tests exist (Phase 2 — auth/business flows; Phase 3 — every Core Business
  domain's CRUD + the order/invoice/purchase-order flows; Phase 4 — agent chat flows;
  extended per phase)
- [x] Agent tests exist (Phase 4 — scripted-MockProvider workflows in `backend/tests/agents`)
- [x] Security tests exist (Phase 2 — cross-tenant/role-escalation for auth/business; Phase 3 —
  cross-tenant resource isolation for products/orders/purchase-orders; Phase 4 — role denial
  through the agent path + session tenant isolation; extended per phase)
- [ ] Seed/demo data exists
- [x] Docker setup works (Phase 2 — `docker compose up` runs db+backend+frontend; Phase 4
  rebuilds the backend image for the new langgraph/openai dependencies)
- [ ] Documentation is complete
- [ ] README is complete
- [ ] `.env.example` exists
- [ ] Deployment instructions exist
