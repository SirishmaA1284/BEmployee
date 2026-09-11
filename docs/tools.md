# Tools

The tool registry (`app/tools/`) is the **only** path agent/LLM code has to touch business
data (ADR-003). API endpoints never use it; they call the same services directly. That split
is structural: the registry is the only bridge between agent code and data, and it audits every
crossing.

## 1. Contract (`app/tools/base.py`)

Every tool is a `ToolSpec`:

- `name`, `description` — what the LLM sees (provider-neutral shape, ADR-010, reusable by the
  Phase 7 MCP server without redesign).
- `input_schema` — a Pydantic model; the registry validates arguments against it on every call
  regardless of what the LLM claims.
- `risk_level` — LOW (reads) / MEDIUM (state-changing writes), decided in code (ADR-004), not
  by the model.
- `required_roles` — server-resolved role from `business_members`; `None` = any member.
- `handler` — `(db, business_id, user_id, validated_args) -> dict`.

Handlers never trust ids from the model: every query is filtered by the registry-passed
`business_id`, and existence checks are re-done server-side.

## 2. Registry (`app/tools/registry.py`)

`ToolRegistry.call(...)` is the single execution path:

1. look up the tool (unknown tool → structured error),
2. validate arguments against the Pydantic schema,
3. check the caller's role,
4. classify the risk (deterministic),
5. execute the handler,
6. **persist an `agent_actions` row** (FR-14): tool name, SUCCESS/FAILED status, risk level,
   and compact input/result summaries — never raw chain-of-thought, never unbounded dumps
   (`_compact` truncates long strings/lists and JSON-safes UUID/Decimal values).

Errors are returned as `{"ok": false, "error": ...}` structured results — never raised into the
LLM loop.

## 3. Catalog (`app/tools/catalog.py` — 14 tools)

| Tool | Risk | Roles | Purpose |
|---|---|---|---|
| `search_products` | LOW | any | name/SKU search |
| `get_product` | LOW | any | product + stock detail |
| `search_customers` | LOW | any | customer search |
| `create_customer` | MEDIUM | any | find-or-create a customer (deduped by name/phone/email — never duplicates) |
| `check_stock` | LOW | any | inventory levels (+ low-stock filter) |
| `list_low_stock` | LOW | any | products at/below reorder threshold |
| `compare_supplier_prices` | LOW | any | ranked supplier offers for a product (same ranking as the REST `/compare` endpoint) |
| `search_suppliers` | LOW | any | supplier search |
| `create_order` | MEDIUM | any | stock check → decrement → invoice, one transaction |
| `list_orders` | LOW | any | recent orders |
| `get_order` | LOW | any | one order |
| `create_purchase_order` | MEDIUM | OWNER/ADMIN | draft PO (on-file prices unless overridden) |
| `list_purchase_orders` | LOW | any | recent POs |
| `get_sales_report` | LOW | any | deterministic sales summary |

## 4. Design rule

Tools are thin adapters: validate → delegate to `app/services/` for deterministic business
logic or plain scoped reads. If a workflow needs a new capability, it gets a new registered
tool — never an agent bypassing the registry (see `docs/agents.md` §4).