# API Documentation

Live interactive OpenAPI docs: `GET /docs` (Swagger UI) once the backend is running — see
`docs/setup.md`. This file documents the same endpoints in a reviewable, versioned form,
updated as each domain ships.

All endpoints below are implemented in `backend/app/api/`. Errors use FastAPI's standard
`{"detail": "..."}` shape.

## Auth (`app/api/auth.py`)

### `POST /api/auth/register`
- Auth: none
- Body: `{ "email": str, "password": str (min 8 chars), "full_name": str }`
- 201 → `TokenResponse` (`access_token`, `user`, `businesses: []`)
- 409 if the email is already registered
- 422 if the password is shorter than 8 characters (or exceeds bcrypt's 72-byte limit)

### `POST /api/auth/login`
- Auth: none
- Body: `{ "email": str, "password": str }`
- 200 → `TokenResponse`
- 401 for wrong password *or* unknown email (deliberately identical response — no email
  enumeration via the login endpoint)

### `GET /api/auth/me`
- Auth: `Authorization: Bearer <token>`
- 200 → `{ "user": UserRead, "businesses": BusinessRead[] }`
- 401 if the token is missing, malformed, expired, or its user no longer exists/is inactive

## Businesses (`app/api/businesses.py`)

### `POST /api/businesses`
- Auth: any authenticated user
- Body: `{ "name": str, "currency": str (default "INR") }`
- 201 → `BusinessRead` — creator is automatically made `OWNER` (`business_members` row created
  in the same transaction)

### `GET /api/businesses`
- Auth: any authenticated user
- 200 → `BusinessRead[]` — only businesses the caller is a member of

### `GET /api/businesses/members`
- Auth: authenticated + a member of the active business (`X-Business-Id` header)
- 200 → `BusinessMemberRead[]` — any role can view; 403 if not a member of that business, 400
  if the header is missing/malformed

### `POST /api/businesses/members`
- Auth: `OWNER` of the active business (`X-Business-Id` header)
- Body: `{ "email": str, "role": "OWNER"|"ADMIN"|"EMPLOYEE" }`
- 201 → `BusinessMemberRead`
- 404 if no registered user has that email (no invite-by-signup flow yet — they must register
  first)
- 409 if already a member
- 403 if the caller isn't `OWNER`, or isn't a member of that business at all

## Auth header conventions used throughout

- `Authorization: Bearer <JWT>` — required on every endpoint except `/api/auth/register`,
  `/api/auth/login`, and `/health`.
- `X-Business-Id: <uuid>` — required on every business-scoped endpoint (everything below). The
  server resolves the caller's role for that business from `business_members` — it is never
  trusted from the client beyond "which business." A resource id from another business simply
  doesn't match the query filter, so it 404s rather than 403s (can't distinguish "not yours"
  from "doesn't exist") — see `backend/tests/security/test_business_domain_isolation.py`.

Role gating below follows `docs/decisions.md` ADR-016.

## Products (`app/api/products.py`)

- `POST /api/products` — OWNER/ADMIN. Body: sku, name, description?, unit, unit_price,
  cost_price?, reorder_threshold, reorder_quantity. 201 → `ProductRead`; also creates the
  product's `inventory` row (qty 0) in the same transaction. 409 on duplicate SKU.
- `GET /api/products?search=` — any role. Excludes soft-deleted products.
- `GET /api/products/{id}` — any role. 404 if not found/not yours/deleted.
- `PATCH /api/products/{id}` — OWNER/ADMIN. Partial update; `reorder_threshold`/
  `reorder_quantity` update the linked `inventory` row.
- `DELETE /api/products/{id}` — OWNER/ADMIN. Soft delete (`deleted_at`), 204.

## Inventory (`app/api/inventory.py`)

- `GET /api/inventory?low_stock_only=` — any role. Joined product+inventory view with a
  computed `is_low_stock` flag.
- `GET /api/inventory/{product_id}` — any role.
- `POST /api/inventory/{product_id}/adjust` — OWNER/ADMIN. Body: `change_quantity` (nonzero,
  ±), `note?`. 422 if the result would go negative. Every adjustment writes a `StockMovement`
  row (reason `ADJUSTMENT`) — quantity is never changed without an audit trail.

## Customers (`app/api/customers.py`)

Standard CRUD (`POST`/`GET`/`GET {id}`/`PATCH {id}`/`DELETE {id}`), any role can write
(spec §4 "routine operations"). Soft delete.

## Suppliers (`app/api/suppliers.py`)

- Standard CRUD — OWNER/ADMIN only for writes, any role reads.
- `POST /api/suppliers/{id}/products` — OWNER/ADMIN. Links/updates a product's price + lead
  time for that supplier (`supplier_products`, upserted).
- `GET /api/suppliers/{id}/products` — any role.
- `GET /api/suppliers/compare?product_id=` — any role. Deterministic ranking (active first,
  then cheapest, then shortest lead time — `app/services/procurement.py`), not an LLM opinion.

## Orders (`app/api/orders.py`)

- `POST /api/orders` — any role. Body: `customer_id`, `items: [{product_id, quantity}]`
  (duplicate product lines are merged). Validates customer/products exist and are active,
  checks stock (`app/services/inventory_service.py`), computes totals
  (`app/services/pricing.py`), decrements inventory + logs `StockMovement`s, and generates an
  `Invoice` — all in one transaction. 404 unknown customer/product; 422 insufficient stock
  (no partial order is created).
- `GET /api/orders`, `GET /api/orders/{id}` — any role.
- `POST /api/orders/{id}/cancel` — OWNER/ADMIN. Restores stock, voids the invoice. 409 if
  already cancelled or if the invoice is already `PAID` (refunds aren't supported yet).

## Invoices (`app/api/invoices.py`)

- `GET /api/invoices`, `GET /api/invoices/{id}` — any role. Includes computed `amount_paid`/
  `amount_due`.
- `POST /api/invoices/{id}/payments` — any role. Body: `amount`, `method`. 422 if it would
  exceed the amount due; 409 if the invoice is `VOID`. Marks the invoice `PAID` when the
  running total exactly covers `total`.

## Purchase Orders (`app/api/purchase-orders.py`)

Writes are OWNER/ADMIN (see `docs/decisions.md` ADR-016). Since Phase 5, a purchase order may be
created directly as `DRAFT`, or — when proposed by the agent and escalated to HIGH risk by the
policy engine — in `PENDING_APPROVAL`, pending a human decision (`docs/decisions.md` ADR-015).

- `POST /api/purchase-orders` — body: `supplier_id`, `items: [{product_id, quantity,
  unit_cost?}]`. If `unit_cost` is omitted, falls back to the current `supplier_products` price
  for that supplier+product (422 if neither is available). 422 against an inactive supplier.
  Created as `DRAFT`.
- `GET /api/purchase-orders`, `GET /api/purchase-orders/{id}` — any role.
- `POST /api/purchase-orders/{id}/send` — `DRAFT → SENT`, `APPROVED → SENT`. 409 for
  `PENDING_APPROVAL` (must be decided first) or other states.
- `POST /api/purchase-orders/{id}/receive` — `SENT → COMPLETED`. Increments inventory and logs
  `StockMovement`s (reason `PURCHASE_RECEIPT`) for every line at its full ordered quantity —
  partial receipt isn't supported yet. 409 otherwise.
- `POST /api/purchase-orders/{id}/cancel` — any state except `COMPLETED`. 409 otherwise.

Lifecycle: `DRAFT`/`PENDING_APPROVAL → SENT → COMPLETED`. A `PENDING_APPROVAL` PO becomes
`APPROVED` (or `CANCELLED`) when its approval request is decided — see Approval Requests below.

## Policies (`app/api/policies.py`)

Business policies are stored here and evaluated **deterministically** by `app/policies` (FR-16,
ADR-004) — the API only stores them; it cannot influence evaluation.

- `GET /api/policies` — any role. Active and inactive policies for the business.
- `PUT /api/policies/{key}` — OWNER/ADMIN. Body: `{ "policy_type", "key", "value", "description"?,
  "is_active" }`. Creates or replaces the policy with that key (upsert).

Policy types:
- `MONEY_THRESHOLD` — `value: { "amount": decimal }`. A MEDIUM-risk money write (create order /
  create purchase order) whose projected impact ≥ this amount is escalated to HIGH (always
  requires approval). The smallest active threshold wins.
- `APPROVAL_ROLES` — `value: { "roles": ["OWNER","ADMIN",...] }`. Which roles may decide
  approval requests. Defaults to `["OWNER","ADMIN"]` when unset.

Example (po above 500 requires approval):
```
PUT /api/policies/po_threshold
{ "policy_type": "MONEY_THRESHOLD", "key": "po_threshold", "value": { "amount": "500.00" } }
```

## Approval Requests (`app/api/approvals.py`)

HIGH-risk agent actions (FR-18) create an approval request and **stop before execution**; a
human resolves it here. The decision is role-gated by the business's APPROVAL_ROLES policy
(default OWNER/ADMIN). There is no code path for an agent to approve its own request.

- `GET /api/approvals?status_filter=` — any role. Latest 100 requests, newest first.
  `status_filter` is one of `PENDING`/`APPROVED`/`REJECTED`.
- `GET /api/approvals/{id}` — any role. 404 if not found / another business's request.
- `POST /api/approvals/{id}/approve` — role must be in APPROVAL_ROLES. Body: `{ "decision_note"? }`.
  200 → the request with `status: "APPROVED"`. 403 if the caller's role can't decide; 409 if not
  `PENDING`.
- `POST /api/approvals/{id}/reject` — same as approve, sets `status: "REJECTED"`.

For a request targeting a purchase order in `PENDING_APPROVAL`, the decision drives the PO's
lifecycle: approve → `APPROVED`, reject → `CANCELLED`.

## Audit Log (`app/api/audit.py`)

Unified, append-only audit trail of all state changes (FR-25). Written by the backend on every
REST write and every registry tool call; read-only here.

- `GET /api/audit?limit=` — any role. Latest entries for the business (max 500). Each entry:
  `actor_type` (`USER`/`AGENT`), `action`, `target_type`/`target_id`, `summary`, `before`/`after`
  (JSONB snapshots where relevant), `created_at`.

## Notifications (`app/api/notifications.py`)

Proactive alerts created by the scheduler worker and the backend (FR-24, ADR-007). Read-only
here — creation happens in the worker, never via the API.

- `GET /api/notifications?type_filter=&in_app_only=&limit=` — any role. Latest notifications for
  the business (max 500), newest first. `type_filter` is one of `LOW_STOCK`/
  `FORECASTED_STOCKOUT`/`APPROVAL_PENDING`/`DAILY_REPORT`; `in_app_only` defaults to `true` (the
  MOCK_* channel rows from the A6 messaging mock are hidden by default). Each entry:
  `notification_type`, `severity` (`INFO`/`WARNING`/`CRITICAL`), `title`, `message`, `payload`
  (JSON-safe details, e.g. product/forecast values), `target_type`/`target_id`, `created_at`.

## AI Employee (`app/api/agents.py`)

Agent lifecycle per request: classify (LLM) → route → workflow (registry tools) → verify →
summarize, all persisted (`agent_sessions`, `agent_tasks`, `agent_actions` per call — FR-14/15).
The chat endpoint runs synchronously; the response carries both the natural-language reply and a
structured `result` the frontend renders.

- `POST /api/agent/chat` — any role (writes still gated per tool). Body: `{ "message": str }`.
  200 → `ChatResponse` (`session_id`, `intent`, `agent_name`, `status`, `reply`, `result`).
  Status: `COMPLETED` / `FAILED` (e.g. denied role, insufficient stock) /
  `NEEDS_CLARIFICATION` (unrecognized request).
- `GET /api/agent/sessions` — any role. Recent 50 sessions for the caller in the active
  business, newest first.
- `GET /api/agent/sessions/{id}` — any role. Session detail: tasks + every tool action with
  risk level and input/result summaries. 404 for another business's session id.

Provider selection: `LLM_PROVIDER` env var (`openai` default with a key; falls back to
`mock` — deterministic keyword/scripted responses — when no key is set; see
`docs/decisions.md` ADR-005 and `backend/app/core/llm/`).

## Planned domains (not yet implemented)

`/api/reports`, `/api/documents`.
