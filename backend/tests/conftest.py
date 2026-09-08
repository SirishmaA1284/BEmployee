import asyncio
import os
import sys
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# asyncpg's connection teardown interacts badly with Windows' default
# ProactorEventLoop (spurious "Event loop is closed" errors during pool
# cleanup). The selector loop doesn't have this issue and is sufficient for
# the TCP-only workload here.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Point at a dedicated test database, never the dev one, so running the suite
# can never touch real data. Overridable via TEST_DATABASE_URL for CI.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:Chinki@localhost:5433/ai_employee_test",
)

test_engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestSessionLocal = async_sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)


@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop so the module-level test_engine's asyncpg
    connections are always opened and closed on the same loop; a fresh loop
    per test (pytest-asyncio's default) breaks asyncpg's connection pool.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    # pytest-asyncio 0.24.0's hookwrapper inspects the redefined event_loop
    # fixture to emit a deprecation warning; `inspect.getsourcelines` fails
    # with OSError when the fixture module is loaded through pytest's
    # assertion-rewriting loader. Marking the loop as pytest-asyncio's own
    # skips that broken path — the loop is deliberately ours.
    setattr(loop, "__original_fixture_loop", True)
    yield loop
    # Dispose the engine on THIS loop before it closes, regardless of other
    # session-scoped fixtures' teardown order (asyncpg pool cleanup must
    # never outlive its event loop).
    loop.run_until_complete(test_engine.dispose())
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def _dispose_engine_at_end():
    # Kept as a no-op placeholder: engine disposal happens in `event_loop`
    # teardown so it is ordered before loop close deterministically.
    yield


@pytest.fixture(autouse=True)
async def _clean_tables() -> AsyncGenerator[None, None]:
    """Truncates all app tables before every test so tests never depend on
    ordering or leftover state from a previous test. Runs against
    ai_employee_test only (see TEST_DATABASE_URL above).
    """
    async with test_engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE TABLE business_members, businesses, users RESTART IDENTITY CASCADE;")
        )
    yield


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """An httpx AsyncClient wired to the FastAPI app with its DB dependency
    overridden to use the test database instead of whatever DATABASE_URL is
    configured for dev/prod.
    """
    from app.database.session import get_db
    from app.main import app

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def business(client: AsyncClient) -> dict:
    """Registers an OWNER and creates a business for them. Shared by every
    Phase 3+ domain's tests so each test file doesn't re-implement this
    boilerplate. Returns owner_headers pre-populated with both the auth
    token and the X-Business-Id header every business-scoped endpoint needs.
    """
    register = await client.post(
        "/api/auth/register",
        json={"email": "owner@example.com", "password": "a-strong-password", "full_name": "Owner"},
    )
    owner_token = register.json()["access_token"]

    create = await client.post(
        "/api/businesses",
        json={"name": "Test Business", "currency": "INR"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    business_id = create.json()["id"]

    return {
        "business_id": business_id,
        "owner_token": owner_token,
        "owner_headers": {"Authorization": f"Bearer {owner_token}", "X-Business-Id": business_id},
    }


@pytest.fixture
async def employee_headers(client: AsyncClient, business: dict) -> dict:
    """Registers a second user and has the owner invite them as EMPLOYEE
    into `business`. Returns headers for that employee.
    """
    register = await client.post(
        "/api/auth/register",
        json={"email": "employee@example.com", "password": "a-strong-password", "full_name": "Employee"},
    )
    employee_token = register.json()["access_token"]

    await client.post(
        "/api/businesses/members",
        json={"email": "employee@example.com", "role": "EMPLOYEE"},
        headers=business["owner_headers"],
    )

    return {"Authorization": f"Bearer {employee_token}", "X-Business-Id": business["business_id"]}
