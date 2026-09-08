# MCP (Model Context Protocol)

Status: minimal read-only MCP server shipped in Phase 7 per `docs/decisions.md` ADR-010 (A7).
The core application does not depend on MCP being reachable — it is an optional external
surface for clients (e.g. an external agent/assistant) to ask the AI Employee read-only
questions.

## Transport

JSON-RPC 2.0 over HTTP, one endpoint: `POST /mcp`.

Authentication is the same as the REST API — no new surface:
- `Authorization: Bearer <JWT>`
- `X-Business-Id: <uuid>`

The server resolves the caller's role from `business_members` server-side, exactly like every
other endpoint; an external client is scoped to its own business and cannot touch another's.

## Methods

### `tools/list`

Returns the exposed tool subset (schemas reused verbatim from the internal registry — they are
already provider-neutral, ADR-010):

```json
{"jsonrpc":"2.0","method":"tools/list","id":1}
```

### `tools/call`

Calls one read-only tool through the same registry, so validation, role checks, and the audit
trail all apply (ADR-003). Each call records an `agent_session`/`agent_task`/`agent_action` so
external activity is observable:

```json
{"jsonrpc":"2.0","method":"tools/call",
 "params":{"name":"get_sales_report","arguments":{}},"id":2}
```

## Exposed subset (read-only by design, ADR-010)

`get_sales_report`, `search_products`, `check_stock`, `list_low_stock`,
`compare_supplier_prices`, `list_orders`, `list_purchase_orders`.

No write tools are exposed. High-risk actions cannot be triggered externally; any future write
exposure must flow through the same policy/approval pipeline (docs/decisions.md ADR-010).

## Example transcript

Request:
```json
{"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_sales_report","arguments":{}},"id":3}
```
Response:
```json
{"jsonrpc":"2.0","id":3,"result":{"ok":true,"data":{"order_count":12,"gross_sales":"12500.00", ...}}}
```