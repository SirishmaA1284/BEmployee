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
- `X-Business-Id: <uuid>` — required on every endpoint scoped to a specific business (anything
  under `/api/businesses/members` today; every business-owned domain added from Phase 3 onward
  will follow the same convention). The server resolves the caller's role for that business
  from `business_members` — it is never trusted from the client beyond "which business."

## Planned domains (not yet implemented)

`/api/products`, `/api/inventory`, `/api/customers`, `/api/orders`, `/api/invoices`,
`/api/suppliers`, `/api/purchase-orders`, `/api/reports`, `/api/agents`, `/api/approvals`,
`/api/audit`, `/api/documents`.
