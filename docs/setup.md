# Setup

## Prerequisites

- Docker Desktop (for Postgres; also runs backend/frontend if you use `docker compose up`)
- Python 3.11+ (only needed for host-based backend dev/tests, i.e. not running via Docker)
- Node 20+ / npm (only needed for host-based frontend dev, i.e. not running via Docker)

## Option A: Docker Compose (recommended, matches production topology)

```bash
cp .env.example .env         # then edit JWT_SECRET etc. for real use
docker compose up
```

This starts:
- `db` — Postgres 16 + pgvector on host port **5433** (not 5432, to avoid colliding with any
  other local Postgres — see `docs/troubleshooting.md`)
- `backend` — FastAPI on http://localhost:8000 (docs at `/docs`), hot-reloading
- `frontend` — Vite dev server on http://localhost:5173, hot-reloading

The backend container does **not** run migrations automatically (a schema migration should be a
deliberate step, not an implicit side effect of starting a container). Run them explicitly:

```bash
docker compose exec backend alembic upgrade head
```

## Option B: Host-based dev (faster iteration, used to build/test this phase)

```bash
docker compose up -d db                 # just the database
cp .env.example backend/.env            # backend reads .env from its own working directory
# edit backend/.env: DATABASE_URL should point at localhost:5433

cd backend
python -m venv .venv
./.venv/Scripts/activate                # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload           # http://localhost:8000

# separately
cd frontend
npm install
npm run dev                             # http://localhost:5173
```

## First login

There is no seed data yet (spec §30, ships in a later phase). Register a new account at
http://localhost:5173/register, then create a business from the dashboard — the creator is
automatically made `OWNER` of that business.

## Running tests

See `docs/testing.md`. Short version:

```bash
docker compose up -d db      # ai_employee_test is created automatically by scripts/init-db.sql
cd backend
alembic upgrade head                                   # migrate the dev DB
TEST_DATABASE_URL=postgresql+asyncpg://ai_employee:ai_employee@localhost:5433/ai_employee_test \
  alembic upgrade head                                  # migrate the test DB too
pytest
```
