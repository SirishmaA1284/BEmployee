# AI Employee Platform for Small Businesses

An agentic backend + web app that gives a small retail/wholesale business an "AI employee": a
system that reads real business data, plans multi-step operational work (orders, inventory,
procurement, reporting), executes what it's authorized to execute, asks a human for approval on
anything risky, verifies its own results, and leaves a full audit trail.

> **Status:** early build (through Phase 3 — Core Business). This README describes the target
> system; sections not yet implemented are marked accordingly. See `CHANGELOG.md` for what has
> actually shipped, phase by phase. Working today: registration/login, businesses with
> role-based multi-tenant authorization, and full CRUD + business logic for products
> (with auto-tracked inventory), customers, suppliers (with price comparison), orders (stock
> check → decrement → invoice generation), invoices/payments, and purchase orders
> (draft → send → receive) — all via API, covered by 83 passing tests (`docs/testing.md`). No
> AI/agent layer yet (Phase 4) and no frontend pages for the Phase 3 domains yet (they land
> alongside the AI Employee UI — see `docs/decisions.md` ADR-013).

## 1. What this is

Not a chatbot wrapper. The AI employee moves through an explicit lifecycle for every request:

```text
OBSERVE → UNDERSTAND → PLAN → CHECK POLICIES → EXECUTE SAFE ACTIONS →
REQUEST APPROVAL FOR RISKY ACTIONS → VERIFY RESULT → RECORD AUDIT LOG →
UPDATE MEMORY → CONTINUE WORKFLOW
```

Example requests it's designed to handle:
- "Create an order for Rahul containing 3 coffee packets and 2 sugar bags."
- "Which products are running low?"
- "Prepare a purchase order for everything likely to run out within 7 days."
- "Which supplier gives the best price for the products we need?"
- "Why did you recommend ordering 20 units?"

## 2. Problem being solved

Off-the-shelf small-business software (POS/inventory/invoicing tools) digitizes records but
doesn't act on them — a human still has to notice low stock, compare suppliers, write the
purchase order, and chase it. This project builds the layer that acts, under explicit policy
and human-approval constraints, with everything it does auditable after the fact.

## 3. Architecture

Full diagrams (system, agent workflow, approval flow, RAG flow, auth flow, deployment target)
live in [`docs/architecture.md`](docs/architecture.md). Summary:

```text
React/TypeScript frontend
        ↓
FastAPI backend (auth, business CRUD, approvals, audit)
        ↓
Agent orchestrator (LangGraph) → specialized agents
        ↓
Tool registry (validated, permissioned, audited — the ONLY DB access path for agent code)
        ↓
PostgreSQL (+ pgvector for RAG)
```

## 4. Agent architecture

Orchestrator, Order, Inventory, Procurement, Customer, Finance/Reporting, Policy, and
Verification agents, each with one clearly defined responsibility — no agent exists "for the
sake of having multiple agents." Deterministic calculations (totals, reorder quantities,
pricing, policy thresholds) are always backend code, never an LLM. Details:
[`docs/agents.md`](docs/agents.md).

## 5. Tool architecture

The LLM never touches the database. It calls named, schema-validated tools
(`get_product`, `check_stock`, `create_order`, `compare_supplier_prices`,
`create_purchase_order`, `create_approval_request`, …); every tool independently re-validates
its arguments and the caller's permissions regardless of what the LLM asserts. Details:
[`docs/tools.md`](docs/tools.md) and rationale in [`docs/decisions.md`](docs/decisions.md)
(ADR-003).

## 6. Database architecture

PostgreSQL with `users`, `businesses`, `business_members`, `products`, `inventory`,
`customers`, `orders`, `order_items`, `invoices`, `invoice_items`, `suppliers`,
`supplier_products`, `purchase_orders`, `purchase_order_items`, `payments`,
`business_policies`, `documents`, `document_chunks` (pgvector), `agent_sessions`,
`agent_tasks`, `agent_actions`, `approval_requests`, `audit_logs`, `notifications`. Details:
[`docs/database.md`](docs/database.md).

## 7. Security

Independent backend validation of every LLM-issued tool call, deterministic policy/permission
enforcement, JWT auth with per-business roles, strict multi-tenant scoping, and an explicit
prompt-injection threat model. Details: [`docs/security.md`](docs/security.md) and
[`docs/threat-model.md`](docs/threat-model.md).

## 8. Human approval system

```text
Agent proposes action → risk classification (backend code) → policy validation →
approval required? → human reviews → approve/reject → execute if approved →
verify → audit
```

LOW risk executes automatically (read inventory, generate reports, search customers). MEDIUM
risk is configurable per business (update stock, draft purchase orders, routine messages).
HIGH risk always requires explicit human approval (place a purchase order, issue a refund,
delete records, change policy). There is no code path for an agent to approve its own request.
Details: [`docs/authorization.md`](docs/authorization.md).

## 9. Setup

Full instructions (including a host-based dev path): [`docs/setup.md`](docs/setup.md).
Quickest path:

```bash
cp .env.example .env
docker compose up
docker compose exec backend alembic upgrade head
```

Then open http://localhost:5173 (frontend) — the backend is at http://localhost:8000
(`/docs` for interactive OpenAPI). Register an account, then create a business from the
dashboard.

## 10. Environment variables

See [`.env.example`](.env.example). Copy it to `.env` and fill in real values; never commit
`.env`.

## 11. Running locally / tests / deployment

[`docs/development.md`](docs/development.md), [`docs/testing.md`](docs/testing.md) (83 backend
tests passing as of Phase 3), [`docs/deployment.md`](docs/deployment.md) (placeholder — no
deployment has been done yet).

## 12. Demo credentials

None yet — seed data ships in a later phase (spec §30). This section will list demo
owner/employee logins for the seeded demo business once available.

## 13. Example workflows

See [`docs/workflows.md`](docs/workflows.md) and the sequence diagrams in
[`docs/architecture.md`](docs/architecture.md) for the order-creation, approval, and RAG flows.

## 14. Project structure

```text
BEmployee/
├── frontend/           React + TypeScript (Vite)
│   ├── src/{pages,components,api,hooks,types,store}
│   └── tests/
├── backend/
│   ├── app/{api,agents,tools,workflows,models,schemas,
│   │         services,policies,security,rag,database,core}
│   ├── alembic/         migrations
│   └── tests/{unit,integration,agents,security}
├── docs/                architecture, agents, tools, security, threat model, etc.
├── scripts/             one-off ops scripts (DB init, seeding)
├── docker/              Dockerfiles (backend/frontend/worker)
├── docker-compose.yml
├── .env.example
└── LICENSE (MIT)
```

Rationale for this layout: [`docs/decisions.md`](docs/decisions.md) ADR-001.

## 15. Roadmap

Tracked as the phase list in [`docs/decisions.md`](docs/decisions.md) and checked off in
[`CHANGELOG.md`](CHANGELOG.md): Foundation → Core Business → AI Employee → Approval & Policies
→ Proactive Intelligence → RAG/MCP → Hardening.

## 16. License

MIT — see [`LICENSE`](LICENSE).
