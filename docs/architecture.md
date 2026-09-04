# Architecture

## 1. System Overview

```mermaid
flowchart TB
    subgraph Client
        FE[React + TypeScript Frontend]
    end

    subgraph API["FastAPI Backend"]
        AUTH[Auth / RBAC]
        BIZAPI["Business APIs\n(products, inventory, orders, invoices, suppliers, POs)"]
        AGENTAPI[Agent API]
        APPROVALAPI[Approvals API]
        AUDITAPI[Audit API]
    end

    subgraph Agents["Agent Layer (LangGraph)"]
        ORCH[Orchestrator Agent]
        ORDER[Order Agent]
        INV[Inventory Agent]
        PROC[Procurement Agent]
        CUST[Customer Agent]
        FIN[Finance/Reporting Agent]
        POLICY[Policy Agent]
        VERIFY[Verification Agent]
    end

    subgraph Tools["Tool Registry (validated, permissioned)"]
        T[get_product / search_products / check_stock / update_inventory /\n create_order / create_invoice / compare_supplier_prices /\n create_purchase_order / get_sales_report / send_customer_message /\n create_approval_request / get_business_policy / create_audit_event]
    end

    subgraph Data
        PG[(PostgreSQL\n+ pgvector)]
        RAGSVC[RAG Retriever]
    end

    subgraph BG["Background Worker"]
        SCHED[APScheduler\nlow-stock scan, daily report, follow-ups]
    end

    FE --> API
    AUTH --> BIZAPI
    AGENTAPI --> ORCH
    ORCH --> ORDER & INV & PROC & CUST & FIN & POLICY
    ORDER & INV & PROC & CUST & FIN --> VERIFY
    ORDER & INV & PROC & CUST & FIN --> T
    POLICY --> T
    T --> PG
    RAGSVC --> PG
    ORCH -.retrieval.-> RAGSVC
    BIZAPI --> PG
    APPROVALAPI --> PG
    AUDITAPI --> PG
    SCHED --> ORCH
    T -->|writes| AUDITAPI
```

Layering rule: the LLM never talks to the database. Agents call named tools; tools validate
input against a Pydantic schema, re-check permissions and business policy independently of
whatever the LLM claims, execute against the ORM, verify, and write an audit event. This is
enforced structurally (tools are the *only* thing agent code imports for data access — no
`Session` object is ever passed into agent/LLM-reachable code).

## 2. Agent Workflow (order creation, representative)

```mermaid
sequenceDiagram
    participant U as Owner
    participant O as Orchestrator
    participant OA as Order Agent
    participant PL as Policy Agent
    participant T as Tools
    participant V as Verification Agent
    participant DB as Postgres

    U->>O: "Create an order for Rahul: 3 coffee, 2 sugar"
    O->>OA: delegate(order_intent)
    OA->>T: search_customer("Rahul")
    T->>DB: query
    DB-->>T: customer row
    OA->>T: search_products(["coffee","sugar"])
    T->>DB: query
    OA->>T: check_stock(product_ids)
    T->>DB: query
    OA->>OA: compute totals (deterministic)
    OA->>PL: evaluate(order_total, policies)
    PL-->>OA: risk=LOW (under threshold)
    OA->>T: create_order(...)
    T->>DB: insert order + items (txn)
    OA->>T: create_invoice(order_id)
    OA->>T: update_inventory(...)
    OA->>V: verify(order_id)
    V->>DB: re-read state
    V-->>OA: verified
    OA->>T: create_audit_event(...)
    OA-->>O: result summary
    O-->>U: "Order #1042 created, invoice #INV-1042 generated."
```

## 3. Approval Flow

```mermaid
flowchart LR
    A[Agent proposes action] --> B[Risk classification\n(backend code)]
    B --> C{Policy check}
    C -->|violates hard rule| R[Reject, log, explain]
    C -->|LOW risk, no rule hit| E[Execute]
    C -->|MEDIUM/HIGH or\npolicy requires approval| AP[Create approval_request]
    AP --> H[Human reviews in UI]
    H -->|Approve| E
    H -->|Reject| RJ[Mark rejected, log]
    E --> V[Verify result]
    V -->|ok| L[Audit log: success]
    V -->|mismatch| F[Mark failed, surface to user, audit log]
```

## 4. RAG Flow

```mermaid
flowchart LR
    Q[User question] --> D{Needs business docs?}
    D -->|no| AG[Agent reasons on structured data only]
    D -->|yes| EMB[Embed query]
    EMB --> SIM[pgvector similarity search\nover document_chunks, business-scoped]
    SIM --> CTX[Top-k chunks, tagged as UNTRUSTED DATA]
    CTX --> AG2[Agent reasons: context is data, not instructions]
    AG2 --> TOOLS[Tool calls if needed]
    TOOLS --> ANS[Answer + cited source documents]
```

Untrusted-context handling: retrieved chunks are wrapped in a delimited, clearly-labeled block
in the prompt and the system prompt explicitly states that content inside that block is data to
reason about, never an instruction. See `docs/threat-model.md`.

## 5. Auth Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant DB as Postgres

    C->>API: POST /api/auth/login {email, password}
    API->>DB: fetch user by email
    API->>API: verify bcrypt hash
    API->>DB: fetch business_members for user
    API-->>C: JWT {sub=user_id, businesses:[{id,role}]}
    C->>API: GET /api/products (Authorization: Bearer ...)
    API->>API: decode JWT, resolve active business_id from header/claim
    API->>API: check role has permission for route
    API->>DB: query scoped by business_id
    API-->>C: data
```

## 6. Technology Stack & Rationale

| Concern | Choice | Why |
|---|---|---|
| Backend framework | FastAPI (Python 3.11+) | async, Pydantic-native validation, OpenAPI for free |
| ORM/migrations | SQLAlchemy 2.0 + Alembic | mature, explicit, works well with async + Postgres |
| DB | PostgreSQL 16 | relational integrity for financial/inventory data; `pgvector` extension covers RAG without a second service |
| Agent orchestration | LangGraph | explicit state machine per workflow, not a black-box loop; matches "deterministic business operations" requirement |
| LLM abstraction | Custom `LLMProvider` interface | avoid lock-in; `OpenAIProvider` default (per product decision), `AnthropicProvider`/`GeminiProvider` stubs, `MockProvider` for tests |
| Auth | JWT (short-lived) + bcrypt | stateless, standard, easy to scope per business |
| Scheduler | APScheduler in a worker process | proactive checks without adopting a broker (Celery/Redis) for MVP scale |
| Frontend | React + TypeScript + Vite | fast dev loop, typed, ecosystem fit |
| Styling | Tailwind CSS | fast to build an operational (non-chat-only) UI |
| Data fetching | TanStack Query | caching/invalidation for dashboard-style UI |
| Vector store | pgvector | one database to operate instead of two; adequate at MVP scale |
| Containerization | Docker Compose | `docker compose up` starts db + backend + frontend + worker |

## 7. Multi-Tenancy Model

Every business-owned table has a `business_id` FK. All repository/service functions accept an
authenticated `business_id` derived from the JWT + `business_members` lookup — never a raw
value trusted from client input. Row-level scoping is enforced in a shared query base
(`app/database/scoped_query.py`, added in Phase 2) so individual endpoints cannot forget the
filter. Cross-tenant access is covered by dedicated security tests (`backend/tests/security`).

## 8. Tool Layer Contract

Every tool (Phase 4) is a Python callable registered with:
- `name`, `description` (used in the LLM tool-calling schema)
- Pydantic `input_schema` / `output_schema`
- `required_permission` (role/business-scoped)
- `risk_level` (LOW/MEDIUM/HIGH, used by the Policy Agent — not decided by the LLM)
- Independent validation of every argument (types, existence, business ownership) regardless of
  what the LLM asserts
- Structured error results (never raise raw exceptions into the LLM loop)
- An audit write on every state-changing call

## 9. Directory Structure

See root `README.md` §Project Structure. Rationale for deviations from the brief's suggested
layout (if any) are logged in `docs/decisions.md`.

## 10. Deployment Target (documented, not yet provisioned)

```mermaid
flowchart LR
    FE[Frontend: Vercel] -->|HTTPS| BE[Backend: Render/Railway]
    BE --> DB[(Managed Postgres w/ pgvector\ne.g. Render/Neon/Supabase)]
    WK[Worker: Render/Railway background service] --> DB
    BE --> LLM[LLM Provider API]
    BE --> STORE[S3-compatible object storage\n(document uploads)]
```

MVP runs entirely via `docker compose up` locally; the above is the intended path to a hosted
deployment and is *not* claimed to be production-hardened until `docs/deployment.md` says so.
