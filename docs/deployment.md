# Deployment

Status: the **Docker Compose path is fully exercised locally** (db + backend + worker + frontend —
see `docs/setup.md`). A **hosted deployment has not yet been performed**; this document gives
concrete, ordered steps for the intended target (architecture.md §10) and is updated as each is
actually run. Treat the hosted section as a plan, not a claim that it has been verified.

## 1. What we run

`docker compose up` brings up four services (docker-compose.yml):

| Service | Image / build | Exposes | Purpose |
|---|---|---|---|
| `db` | `pgvector/pgvector:pg16` | host `5433` | PostgreSQL + pgvector (RAG embeddings) |
| `backend` | `docker/backend.Dockerfile` | host `8000` | FastAPI (`/api/*`, `/mcp`, `/health`) |
| `worker` | `docker/worker.Dockerfile` | — | APScheduler proactive checks (ADR-007) |
| `frontend` | `docker/frontend.Dockerfile` | host `5173` | Vite dev server (dev) / static build (prod) |

## 2. Local run (the tested path)

```bash
docker compose up --build          # first run builds images
docker compose exec backend alembic upgrade head   # migrate the dev DB
docker compose exec backend python -m app.seed     # optional demo data (Phase 8)
docker compose exec -e TEST_DATABASE_URL=... backend python -m pytest  # see docs/testing.md
```

- The DB container runs `scripts/init-db.sql` on first start, which creates the `ai_employee_test`
  database too.
- The worker needs the same `DATABASE_URL`; it starts automatically with `docker compose up`.
- Health: `curl localhost:8000/health` → `{"status":"ok"}`.

## 3. Production checklist

Before any hosted deployment, the following are **not** production-ready claims (see
`docs/security.md` "MVP vs. Production Hardening"):

- Set real secrets: `DATABASE_URL`, `JWT_SECRET` (>= 32 random bytes), `OPENAI_API_KEY` (if using
  real embeddings/LLM). Never use the dev values from docker-compose.yml.
- Rate limiting is in-process (per API instance) — a multi-instance deployment needs a shared
  limiter (Redis) behind the documented scaling seam (ADR-007).
- Refresh tokens rotate server-side (`refresh_tokens` table); set `REFRESH_TOKEN_EXPIRE_DAYS`.
- Virus scanning of document uploads, WAF/anomaly detection, secrets rotation automation, and
  penetration testing remain roadmap items (security.md).

## 4. Hosted target (plan, not yet performed)

### Managed Postgres (Render / Neon / Supabase)
- Create a Postgres 16 instance with the `pgvector` extension enabled.
- Set `DATABASE_URL` to its connection string (asyncpg driver: `postgresql+asyncpg://...`).
- Run migrations from the backend container/job: `alembic upgrade head`.

### Backend + worker (Render / Railway)
- Backend: a web service built from `docker/backend.Dockerfile`, command
  `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Worker: a background service built from `docker/worker.Dockerfile` (same image, different
  entrypoint), `python -m app.worker.main`.
- Set the same env vars on both; only the backend is reachable from the internet.

### Frontend (Vercel)
- Build the static bundle (`npm run build` → `frontend/dist`).
- Set `VITE_API_BASE_URL` to the deployed backend's public URL at build time.
- SPA rewrites: route all paths to `/` (client-side routing handles the rest).

### Object storage (documents)
- The target architecture shows S3-compatible object storage for uploads; today documents are
  stored as text in Postgres (`documents.text_content`). Moving to object storage is a noted
  enhancement, not a current deployment step.

## 5. Environment variables

Documented in `.env.example` and consumed by `app/core/config.py`. Key ones:

- `DATABASE_URL`, `JWT_SECRET`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`
- `REFRESH_TOKEN_EXPIRE_DAYS` (Phase 8 refresh-token rotation)
- `LLM_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `EMBEDDING_MODEL`
- `SCHEDULER_CHECK_INTERVAL_MINUTES`, `SCHEDULER_DAILY_REPORT_HOUR`
- `CORS_ORIGINS` (the frontend origin), `VITE_API_BASE_URL`