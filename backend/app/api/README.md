# app/api

FastAPI routers, grouped by domain (auth, businesses, products, inventory, customers, orders,
invoices, suppliers, purchase-orders, reports, agents, approvals, audit, documents). Added in
Phase 2 onward. Routers depend on `app/schemas` for request/response models and `app/services`
for business logic — no direct DB/session access in route handlers.
