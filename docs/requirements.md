# Requirements

Status: living document. Updated at the end of each build phase.

## 1. Problem Statement

Small retail/wholesale businesses run on manual, repetitive operational work: checking
stock, writing up orders, chasing suppliers, reordering, and reconciling sales. Off-the-shelf
POS/inventory tools digitize records but do not *act*. This project builds an "AI employee":
an agentic system that reads business data, proposes and (within policy) executes operational
actions, asks a human for approval on anything risky, and leaves a full audit trail.

## 2. MVP Domain

Generic retail/wholesale business. Entities: products, inventory, customers, orders, order
items, suppliers, purchase orders, invoices, payments, business policies, agent
sessions/tasks/actions, approval requests, audit logs, notifications, documents (for RAG).

Explicitly out of scope for MVP: pharmacy/healthcare/finance-regulated domains, multi-currency,
multi-warehouse, tax engines beyond a flat rate, payment gateway integration (mocked),
WhatsApp/SMS integration (mocked adapter), real-time collaborative editing.

## 3. Actors

- **Owner** — full control of a business: config, policies, permissions, approvals, reports.
- **Employee** — operates within a business: routine CRUD, requests AI help, cannot change
  policies or approve high-risk actions (configurable per policy).
- **AI Employee** — not a human user/session. Operates only through the tool registry, under
  the same authorization system as a human user (scoped to one business, one set of
  permissions). Never has direct DB access.

## 4. Functional Requirements

### 4.1 Auth & Multi-tenancy
- FR-1: Email/password registration and login. Passwords hashed (bcrypt).
- FR-2: JWT-based session auth with role claims (OWNER, ADMIN, EMPLOYEE).
- FR-3: A user may belong to multiple businesses (via `business_members`), with a role per
  business.
- FR-4: Every business-owned row is scoped by `business_id`; every query is filtered by the
  authenticated user's business membership. Cross-business access must be impossible even with
  a guessed ID (authorization checked server-side, not client-side).

### 4.2 Core Business Operations
- FR-5: CRUD for products, customers, suppliers (owner/admin; employees read + limited write
  per policy).
- FR-6: Inventory tracked per product with quantity on hand, reorder threshold, reorder
  quantity; stock movements recorded (not just a mutable counter) so history is auditable.
- FR-7: Orders: create with line items, validate stock, compute totals deterministically,
  decrement inventory, generate an invoice.
- FR-8: Suppliers linked to products via `supplier_products` (price, lead time, active flag).
- FR-9: Purchase orders: draft → pending_approval → approved → sent → completed/failed
  lifecycle.
- FR-10: Invoices and payments recorded against orders.

### 4.3 AI Employee
- FR-11: Natural-language endpoint that routes a request through an orchestrator to the
  correct specialized agent/workflow.
- FR-12: Agents call only registered tools with independently validated arguments — never
  raw DB/ORM access from agent code paths.
- FR-13: Deterministic calculations (totals, reorder quantities, forecasts, policy money
  thresholds) are implemented in plain backend code, never delegated to the LLM.
- FR-14: Every agent action is persisted (`agent_actions`) with a concise reasoning summary,
  inputs/outputs summary, risk level, and status — never raw chain-of-thought.
- FR-15: Workflow state (`agent_sessions`, `agent_tasks`) is persisted so an in-progress or
  failed workflow can be inspected/resumed.

### 4.4 Policy & Approval
- FR-16: Business owners can define policies (money thresholds, supplier rules, messaging
  hours, minimum reorder quantities, etc.) stored in `business_policies` and evaluated by a
  deterministic policy engine — not by asking the LLM to "decide" if a rule applies.
- FR-17: Every proposed action is risk-classified (LOW/MEDIUM/HIGH) by backend logic (not the
  LLM). MEDIUM is configurable per business; HIGH always requires approval.
- FR-18: High-risk or policy-flagged actions create an `approval_requests` row and stop before
  execution. Approval/rejection is a human, authenticated action against that row —
  there is no code path for an agent to mark its own request approved.
- FR-19: After execution, a verification step re-reads the affected state and confirms it
  matches the intended outcome; failed verification marks the action `failed` and surfaces it.

### 4.5 Explainability & Memory
- FR-20: "Why did you recommend X" returns a structured evidence object (inputs, thresholds,
  computed values, chosen option and why), not a prose chain-of-thought dump.
- FR-21: Structured memory = the relational database. Unstructured memory = uploaded business
  documents, chunked and embedded (pgvector) for retrieval-augmented generation.
- FR-22: RAG answers cite which document(s) informed them.
- FR-23: Retrieved document content is treated as untrusted data; it cannot redefine agent
  instructions or bypass tool/policy checks (see `docs/threat-model.md`).

### 4.6 Proactive Intelligence
- FR-24: A scheduler (not an uncontrolled LLM loop) periodically runs deterministic checks:
  low stock, forecasted stockouts, pending follow-ups, daily report generation. Any resulting
  *action* (e.g. a purchase order) still goes through the same policy/approval pipeline as a
  user-triggered one.

### 4.7 Audit & Observability
- FR-25: Every state-changing action (human or AI) writes an `audit_logs` row: actor, action,
  target, business, timestamp, before/after summary where relevant.
- FR-26: Structured logs carry request IDs and, for agent work, workflow/session IDs.

## 5. Non-Functional Requirements

- NFR-1 (Security): No LLM-issued tool call executes without independent backend
  validation of arguments and permissions. See `docs/threat-model.md`.
- NFR-2 (Reliability): Order/invoice/inventory writes are transactional; duplicate submissions
  are idempotent (client-supplied idempotency key or natural dedup window).
- NFR-3 (Cost control): Agent loops have a max iteration count, max tool calls, and timeout;
  no unbounded LLM loops.
- NFR-4 (Portability): LLM provider is swappable via configuration, not code changes, through
  an `LLMProvider` abstraction.
- NFR-5 (Testability): Deterministic business logic (pricing, reorder math, policy evaluation,
  risk classification) is unit-testable without any LLM call.
- NFR-6 (Auditability): No feature is considered done without an audit trail and, where it
  changes DB state, a test.
- NFR-7 (Extensibility): Domain is generic-retail today; schema/tool design must not encode
  retail-only assumptions in a way that blocks adding a second business type later.

## 6. Key Assumptions (MVP scope decisions)

These resolve ambiguities in the source spec. Each is elaborated with rationale in
`docs/decisions.md`.

- A1: Single currency (INR, ₹) for MVP; currency stored as a column for future multi-currency.
- A2: One "location"/warehouse per business for MVP; `inventory` keyed by `(business_id,
  product_id)` — not per-warehouse.
- A3: LLM provider defaults to OpenAI (per user decision), with Anthropic/Gemini adapters
  stubbed behind the same interface, and a deterministic MockProvider used in tests/CI so the
  suite runs without API keys.
- A4: Vector store is pgvector inside the existing PostgreSQL instance (no separate vector DB
  service), per user decision.
- A5: Background/scheduled jobs run via APScheduler inside a dedicated worker process — no
  message broker (Celery/Redis) introduced for MVP; documented as a scaling seam.
- A6: WhatsApp/SMS/email customer messaging is a mock adapter that logs the "sent" message and
  records it as a notification; no real provider credentials required to run the MVP.
- A7: MCP exposure of tools is designed but only a minimal read-only MCP server ships in the
  MVP (Phase 7); the core app never depends on MCP being reachable.
- A8: Soft delete via `deleted_at` on business-owned entities that can be referenced by
  historical records (products, customers, suppliers); hard delete only for draft-only rows.

## 7. Definition of Done

Tracked verbatim from the project brief in `docs/decisions.md` §"Definition of Done", checked
off phase by phase in this file's changelog and in `CHANGELOG.md`.
