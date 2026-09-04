# Troubleshooting

## Backend tests: "Event loop is closed" / AttributeError during teardown (Windows)

**Symptom:** `pytest` errors (not failures) on teardown of DB-touching tests, with an
`asyncpg`/`proactor_events.py` traceback ending in `AttributeError: 'NoneType' object has no
attribute 'send'` or `RuntimeError: Event loop is closed`.

**Cause:** `asyncpg`'s connection cleanup doesn't play well with Windows' default
`ProactorEventLoop`, and pytest-asyncio's default function-scoped event loop meant the shared
test engine's connections were opened on one loop and closed on another.

**Fix applied** in `backend/tests/conftest.py`: force `WindowsSelectorEventLoopPolicy` on
`win32`, and use a session-scoped `event_loop` fixture so the whole test session shares one
loop. This does print a pytest-asyncio deprecation warning ("Replacing the event_loop fixture
... is deprecated") — tracked as a follow-up to migrate to `@pytest.mark.asyncio(loop_scope=
"session")`-style configuration once pytest-asyncio's session-scope story stabilizes past
0.24; not fixed now because the current approach works and chasing the newer API produced no
functional improvement, only churn.

## Postgres container won't start: "port is already allocated"

**Symptom:** `docker compose up db` fails with `Bind for 0.0.0.0:5432 failed: port is already
allocated`.

**Cause:** Another project's Postgres container (or a local Postgres install) is already
bound to host port 5432.

**Fix:** This repo's `docker-compose.yml` maps the db container to host port **5433**, not
5432, specifically to avoid this. If you still hit a conflict, check
`docker ps` / `Get-NetTCPConnection -LocalPort 5433` for whatever else is using it — don't stop
containers you don't recognize without checking what they belong to first.

## Host → Docker-mapped Postgres connections fail intermittently (Windows)

**Symptom:** `alembic` (or any host-run asyncpg script) connecting to
`localhost:5433` fails with `ConnectionError: unexpected connection_lost() call` or
`asyncpg.exceptions.ConnectionDoesNotExistError: connection was closed in the middle of
operation`, even though `docker exec ai_employee_db psql ...` and connecting from *inside*
another container (e.g. `docker compose exec backend python -c "...asyncpg.connect('...@db:5432/...')"`)
both work fine.

**Cause:** Docker Desktop's Windows host↔container TCP port-forwarding occasionally gets into
a bad state for a given mapped port under sustained use — this is a Docker Desktop networking
quirk, not an application bug. Confirmed by: the DB itself answers queries fine via `docker
exec`; the backend container reaches it fine over the internal Docker network (`db:5432`); only
the *host→published-port* path (`localhost:5433`) breaks. Simple HTTP requests from the host to
other published ports (e.g. `:8000`, `:5173`) can be affected the same way and can present as
"Empty reply from server" from `curl`, or a closed-connection error from PowerShell's
`Invoke-WebRequest`, even though the process inside the container is healthy and responds fine
to a request made from inside its own container.

**Fix:**
- For one-off host-run DB scripts/migrations: run them through the container instead —
  `docker compose exec backend alembic upgrade head` (or `... alembic revision
  --autogenerate ...`) — rather than from a host Python venv. This is what Phase 3's migration
  was generated/applied with; see `docs/database.md`.
- For a stuck published port in general (HTTP or Postgres): `docker compose restart <service>`
  re-establishes the port mapping and reliably clears it — this fixed an identical symptom on
  the `backend` HTTP port during Phase 3 development.
- Don't chase this as an application bug — verify from inside the container first
  (`docker compose exec <service> python -c "..."` or similar) before assuming the app is
  broken.
