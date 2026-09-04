# API Documentation

Status: placeholder — populated incrementally as each API domain ships (Phase 2+). Live
OpenAPI/Swagger docs will be served at `/docs` (FastAPI default) once the backend exists.

Planned structure per endpoint: method + path, auth requirement, required role, request
example, response example, error responses, and which audit event (if any) it produces.

Planned domains: `/api/auth`, `/api/businesses`, `/api/products`, `/api/inventory`,
`/api/customers`, `/api/orders`, `/api/invoices`, `/api/suppliers`, `/api/purchase-orders`,
`/api/reports`, `/api/agents`, `/api/approvals`, `/api/audit`, `/api/documents`.
