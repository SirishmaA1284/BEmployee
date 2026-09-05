# Agents

Phase 4 ships the orchestrator and the specialized agents that power the AI Employee. Every
agent is a LangGraph `StateGraph` with typed state (`app/agents/state.py`), built per request
with the request's DB session and LLM provider closed over. Nodes are explicit steps — control
flow is a graph, never free-form LLM improvisation (ADR-002).

**Hard rule (ADR-003):** agent code never imports a DB session or ORM model for data access. It
calls registry tools only; the registry validates, permission-checks, and audits every call.

## 1. Orchestrator (`app/agents/orchestrator.py`)

Entry point: `run_agent(provider, db, business_id, user_id, role, task_id, message)`.

- **classify** node — one bounded structured LLM call (`classify_intent`) validated against
  `AgentIntent`; anything missing/invalid routes to UNKNOWN/clarify.
- **route** — a conditional edge maps the validated intent to the matching workflow subgraph.
- **clarify** — asks for a clearer request (and never clobbers an already-produced reply).

The orchestrator also enforces NFR-3: a per-request `llm_calls` counter capped at
`MAX_AGENT_STEPS` (default 10) before any provider call.

## 2. Workflows

| Workflow | Intent(s) | Nodes | Tools used |
|---|---|---|---|
| Order (`workflows/order.py`) | CREATE_ORDER | extract → resolve → create → verify → summarize | search_customers, search_products, create_order, get_order (verification) |
| Inventory (`workflows/inventory.py`) | LOW_STOCK, CHECK_INVENTORY | extract → check (or check only) | list_low_stock, check_stock |
| Procurement (`workflows/procurement.py`) | COMPARE_SUPPLIERS | extract → compare | search_products, compare_supplier_prices |
| Procurement (`workflows/procurement.py`) | CREATE_PURCHASE_ORDER | extract → plan → create → verify → summarize | search_suppliers, search_products, list_low_stock, compare_supplier_prices, create_purchase_order, list_purchase_orders |
| Customer (`workflows/customer.py`) | SEARCH_PRODUCTS, SEARCH_CUSTOMERS | extract → search | search_products / search_customers |
| Finance (`workflows/finance.py`) | SALES_REPORT | report | get_sales_report |

Notes:

- **extract** nodes are prompt-layer only: the LLM turns natural language into a validated
  Pydantic structure (`OrderExtraction`, `PurchaseOrderExtraction`, …). It never touches data.
- **resolve/plan** nodes map extracted names to real ids via registry tools and never guess.
- **create** nodes call the registry, which runs the same deterministic services the REST API
  uses (`app/services/order_service.py`, `purchase_order_service.py`) — provably the same code
  path a human uses.
- **verify** nodes (Verification Agent, `app/agents/verification.py`, FR-19) re-read the written
  state through the registry and re-check the math (line totals, header totals, invoice
  presence, DRAFT status). Failed verification fails the task; it never silently passes.
- **summarize** nodes narrate only values returned by tools — the LLM never produces numbers.

The CREATE_PURCHASE_ORDER workflow has two deterministic branches: items specified in the
request (resolve supplier + products), or *low-stock-driven procurement* when the user asks for
"everything likely to run out" — it lists low-stock products, ranks suppliers per product,
picks the supplier that wins the most products (ties broken by name), and drafts a PO at that
supplier's on-file prices.

## 3. Policy Agent (seam)

Risk classification is applied structurally on every registry call (`classify_action`,
`app/policies/risk.py`, ADR-004): reads are LOW, state-changing writes are MEDIUM, and
`create_purchase_order` is additionally restricted to OWNER/ADMIN. The full policy engine
(business_policies, thresholds, approval requests) lands in Phase 5 behind the same function.

## 4. What agents never do

- No direct SQLAlchemy usage (ADR-003, enforced by convention + tests).
- No LLM-computed money/stock/ranking math (Rule 4 — services own that).
- No unbounded loops (per-request step cap).
- No approval of their own actions (approval is human-only; the code path doesn't exist).

See `docs/architecture.md` §2 for the order-creation sequence diagram.