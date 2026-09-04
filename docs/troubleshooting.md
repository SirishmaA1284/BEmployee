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
