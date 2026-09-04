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
    "postgresql+asyncpg://ai_employee:ai_employee@localhost:5433/ai_employee_test",
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
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def _dispose_engine_at_end():
    yield
    await test_engine.dispose()


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
