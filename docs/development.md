# Development

## Backend layout (what exists so far)

- `app/core/config.py` — `Settings` (pydantic-settings), read from `.env`.
- `app/database/` — async SQLAlchemy engine/session (`session.py`), declarative `Base` +
  `UUIDPrimaryKeyMixin`/`TimestampMixin` (`base.py`).
- `app/models/` — `User`, `Business`, `BusinessMember` (+ `BusinessRole` enum). All imported in
  `app/models/__init__.py` so Alembic autogenerate sees the full schema.
- `app/schemas/` — Pydantic request/response models.
- `app/security/` — `passwords.py` (bcrypt), `jwt.py` (PyJWT), `dependencies.py`
  (`get_current_user`, `get_current_membership`, `require_role`).
- `app/api/` — `auth.py` (`/api/auth/*`), `businesses.py` (`/api/businesses*`).
- `app/main.py` — FastAPI app factory, CORS, request-id middleware, router registration.

## Adding a new API route

1. Add/extend a Pydantic schema in `app/schemas/`.
2. Add the route in the relevant `app/api/<domain>.py` router (create one if the domain is
   new), using `Depends(get_current_user)` or `Depends(get_current_membership)` /
   `Depends(require_role(...))` for auth — never skip these.
3. Any DB write query must filter by the resolved `business_id` from the membership dependency,
   never a client-supplied one.
4. Add tests: at minimum one happy-path integration test and one security test proving
   cross-business/insufficient-role access is rejected (see `backend/tests/security/`).

## Database migrations

```bash
cd backend
alembic revision --autogenerate -m "add products table"
# review the generated file under alembic/versions/ before applying — autogenerate is a
# starting point, not ground truth (it won't catch every constraint change correctly)
alembic upgrade head
```

Never hand-edit a migration that has already been merged to `main` — write a new one instead
(`docs/contributing.md`).

## Running things locally

See `docs/setup.md` for the full Docker vs. host-based instructions.

Backend dev server: `uvicorn app.main:app --reload` (from `backend/`, with `.venv` active).
Frontend dev server: `npm run dev` (from `frontend/`).

## Environment variables

Read via `app/core/config.py` (`Settings`, pydantic-settings). Backend looks for `.env` in its
own working directory — when running host-based (not via Docker), that means `backend/.env`,
copied/adapted from the root `.env.example`. When running via `docker compose up`, the backend
container's environment variables are set directly in `docker-compose.yml` instead (no `.env`
file needed inside the container for local dev).

## Known local-dev quirk (Windows + asyncpg + pytest)

See `docs/troubleshooting.md` — the test suite forces the Windows selector event loop policy
and a session-scoped pytest event loop to avoid a spurious teardown error. This is
test-infrastructure-only; it doesn't affect the app itself (uvicorn runs its own loop).
