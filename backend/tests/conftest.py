"""
Pytest configuration and shared fixtures for RecruiteAI backend tests.

Provides:
- Async test database (creates/drops tables per session)
- Async HTTP client for API testing
- Pre-authenticated client with JWT token
- Sample data fixtures (users, jobs, resumes)
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.core.security import hash_password, create_access_token
from app.database import Base, get_db
import app.services.call_evaluation as call_evaluation_module
import app.services.realtime_bridge as realtime_bridge_module
from app.main import app
from app.models.user import User

settings = get_settings()

TEST_DATABASE_SCHEMA = "recruiteai_test"
TEST_DATABASE_URL = settings.DATABASE_URL

test_db_url = make_url(TEST_DATABASE_URL)
admin_connect_args = {}
test_connect_args = {}
if test_db_url.drivername.startswith("postgresql+asyncpg"):
    test_connect_args = {"server_settings": {"search_path": TEST_DATABASE_SCHEMA}}

admin_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    poolclass=pool.NullPool,
    connect_args=admin_connect_args,
)
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    poolclass=pool.NullPool,
    connect_args=test_connect_args,
)
test_session_factory = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """Create all test tables inside an isolated schema before tests, drop them after."""
    async with admin_engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {TEST_DATABASE_SCHEMA}"))

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    async with admin_engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {TEST_DATABASE_SCHEMA} CASCADE"))
    await test_engine.dispose()
    await admin_engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean database session for each test (with rollback)."""
    # Clear tables to prevent IntegrityErrors between tests
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
            
    async with test_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(autouse=True)
async def override_realtime_bridge_session_factory():
    """Force helper sessions to use the isolated test schema."""
    original_session_factory = realtime_bridge_module.async_session_factory
    original_evaluation_session_factory = call_evaluation_module.async_session_factory
    realtime_bridge_module.async_session_factory = test_session_factory
    call_evaluation_module.async_session_factory = test_session_factory
    yield
    realtime_bridge_module.async_session_factory = original_session_factory
    call_evaluation_module.async_session_factory = original_evaluation_session_factory


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP client that uses the test database session.
    Overrides the get_db dependency to use our test session.
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user in the database."""
    user = User(
        id=uuid.uuid4(),
        email="testuser@example.com",
        hashed_password=hash_password("TestPassword@123"),
        full_name="Test User",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user: User) -> dict:
    """Generate auth headers with a valid JWT for the test user."""
    token = create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def authenticated_client(
    client: AsyncClient, auth_headers: dict
) -> AsyncClient:
    """Client with auth headers pre-set for convenience."""
    client.headers.update(auth_headers)
    return client
