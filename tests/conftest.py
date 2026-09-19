"""Shared test fixtures, database configuration, and mock clients."""

import os

# Set test environment variables before importing app modules
os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["RATE_LIMIT_PER_MINUTE"] = "5"
os.environ["RATE_LIMIT_REDIS_FAILURE_POLICY"] = "fail_open"
os.environ["OPENAI_API_KEY"] = "sk-test-openai-key-12345"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-anthropic-key-12345"
os.environ["WEBHOOK_SECRET"] = "test-secret-key-that-is-at-least-32-chars-long"
os.environ["LOG_LEVEL"] = "DEBUG"

from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.dependencies import get_db, get_redis
from app.core.config import Settings, get_settings
from app.core.security import extract_key_prefix, generate_raw_api_key, hash_api_key
from app.db.base import Base
from app.main import app
from app.models.api_key import ApiKey

# Clear settings cache so new os.environ is picked up
get_settings.cache_clear()


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Return test configuration with test keys and in-memory SQLite."""
    return Settings(
        app_env="development",
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/1",
        rate_limit_per_minute=5,
        rate_limit_redis_failure_policy="fail_open",
        openai_api_key="sk-test-openai-key-12345",
        anthropic_api_key="sk-ant-test-anthropic-key-12345",
        webhook_secret="test-secret-key-that-is-at-least-32-chars-long",
        log_level="DEBUG",
    )


@pytest.fixture(autouse=True)
def override_settings(test_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure all components receive test settings throughout test executions."""
    import app.core.config as config_module

    monkeypatch.setattr(config_module, "get_settings", lambda: test_settings)


@pytest_asyncio.fixture
async def test_engine(test_settings: Settings) -> AsyncGenerator[AsyncEngine, None]:
    """Create an async SQLite in-memory engine for test isolation."""
    engine = create_async_engine(
        test_settings.database_url,
        connect_args={"check_same_thread": False},
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an active database session for a single test."""
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def test_redis() -> AsyncGenerator[FakeRedis, None]:
    """Provide an in-memory FakeRedis client."""
    fake_redis = FakeRedis(decode_responses=True)
    yield fake_redis
    await fake_redis.flushall()
    await fake_redis.close()


@pytest_asyncio.fixture
async def test_api_key(test_session: AsyncSession) -> tuple[ApiKey, str]:
    """Generate and persist a valid test API key, returning (model, raw_key)."""
    raw_key = generate_raw_api_key()
    key_hash = hash_api_key(raw_key)
    prefix = extract_key_prefix(raw_key)

    key_model = ApiKey(
        client_name="Test Suite Client",
        key_hash=key_hash,
        key_prefix=prefix,
        is_active=True,
        rate_limit_per_minute=5,
    )
    test_session.add(key_model)
    await test_session.commit()
    await test_session.refresh(key_model)

    return key_model, raw_key


@pytest_asyncio.fixture
async def async_client(
    test_session: AsyncSession,
    test_redis: FakeRedis,
    test_settings: Settings,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide an HTTPX AsyncClient configured with app dependency overrides."""
    app.dependency_overrides[get_db] = lambda: test_session
    app.dependency_overrides[get_redis] = lambda: test_redis
    app.dependency_overrides[get_settings] = lambda: test_settings

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()
