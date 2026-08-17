"""Shared fixtures: a real PostgreSQL test database (created and dropped once
per test session), transactional rollback isolation between tests, and an
async test client.

Deliberately NOT SQLite - the whole point of the Postgres migration was
parity between dev/test and prod.
"""

import time
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
import redis.asyncio as redis
from alembic.config import Config as AlembicConfig
from fastapi_users.db import SQLAlchemyUserDatabase
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

import app.cache as cache_module
from alembic import command
from app.app import app
from app.config import settings
from app.db import get_async_session
from app.users import UserManager


@pytest_asyncio.fixture(autouse=True)
async def _fresh_redis_client(monkeypatch):
    """app/cache.py's redis_client is a module-level singleton, created once
    for the lifetime of the (one, long-running) real app process. pytest-
    asyncio gives each test function its own fresh event loop by default,
    and redis-py's async connections are bound to the loop they were opened
    on - reusing the module-level client across tests means test 2 tries to
    use a connection whose loop test 1 already closed ("Event loop is
    closed"). Swapping in a fresh client per test, bound to that test's own
    loop, sidesteps it; the cache helper functions in app/cache.py look up
    `redis_client` from their module's globals at call time, so patching it
    here is enough - no need to touch every call site."""
    client = redis.from_url(settings.redis_url, decode_responses=True)
    await client.flushdb()  # otherwise a stale feed/post cache key from a
    # previous test - same version, same page - could get served to this one
    monkeypatch.setattr(cache_module, "redis_client", client)
    yield
    await client.aclose()


def _test_database_url() -> str:
    url = make_url(settings.database_url)
    test_db_name = (url.database or "photoshare") + "_pytest"
    return str(url.set(database=test_db_name))


@pytest.fixture(scope="session")
def test_db_url() -> str:
    return _test_database_url()


def _retry_on_operational_error(fn, attempts: int = 15, delay_seconds: float = 2.0):
    """A fresh postgres:16-alpine container has occasionally rejected
    connections made shortly after startup with a spurious "password
    authentication failed" - reproduced locally against the same image with
    identical credentials (confirmed via container logs: pg_hba.conf matched
    the correct scram-sha-256 rule and still rejected a password that an
    otherwise-identical connection accepted seconds later), so it's a
    transient auth/startup race rather than a real credentials bug. It has
    shown up on two independent connections in this fixture - the sync admin
    engine's DROP/CREATE DATABASE, and Alembic's own internal async engine
    during `command.upgrade()` - so this wraps both rather than just one.
    Costs nothing when the connection is fine on the first try (the common
    case) and absorbs the flake when it isn't."""
    last_error: OperationalError | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except OperationalError as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(delay_seconds)
    raise last_error


@pytest.fixture(scope="session")
def _test_database(test_db_url: str) -> Generator[None, None, None]:
    """Create the test database fresh, run every Alembic migration against
    it, then drop it once the whole session is done.

    Deliberately synchronous (a plain psycopg connection, not the app's async
    engine): this fixture - and the alembic upgrade it runs, which itself
    calls asyncio.run() internally - must NOT execute inside an already-
    running event loop. pytest-asyncio starts one for async fixtures/tests,
    and asyncio.run() cannot be nested inside a running loop. DDL admin work
    doesn't need to be async anyway."""
    target = make_url(test_db_url)
    admin_url: URL = target.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with _retry_on_operational_error(admin_engine.connect) as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{target.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin_engine.dispose()

    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.attributes["sqlalchemy_url"] = test_db_url
    _retry_on_operational_error(lambda: command.upgrade(alembic_cfg, "head"))

    yield

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with _retry_on_operational_error(admin_engine.connect) as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{target.database}" WITH (FORCE)'))
    admin_engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def engine(test_db_url: str, _test_database: None) -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(test_db_url, pool_pre_ping=True)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture()
async def db_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """One test = one outer transaction that's always rolled back at the end,
    even though the route handlers under test call session.commit(). SQLAlchemy's
    join_transaction_mode="create_savepoint" wraps each of those commits in a
    SAVEPOINT instead of really ending the outer transaction."""
    connection = await engine.connect()
    outer_transaction = await connection.begin()
    TestSession = async_sessionmaker(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    session = TestSession()

    yield session

    await session.close()
    await outer_transaction.rollback()
    await connection.close()


@pytest_asyncio.fixture()
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async client whose requests all run inside db_session's rolled-back
    transaction. Use this for anything that shouldn't leave data behind."""

    async def _override_get_async_session():
        yield db_session

    app.dependency_overrides[get_async_session] = _override_get_async_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def register_user(client: AsyncClient, email: str, password: str = "testpass123") -> dict:
    res = await client.post("/auth/register", json={"email": email, "password": password})
    res.raise_for_status()
    return res.json()


async def login(client: AsyncClient, email: str, password: str = "testpass123") -> dict[str, str]:
    """fastapi-users' login route is an OAuth2 password flow - form-encoded,
    not JSON, and the field is called "username" even though it's an email."""
    res = await client.post("/auth/jwt/login", data={"username": email, "password": password})
    res.raise_for_status()
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class _TokenCapture:
    """Stands in for the real email delivery this app doesn't have -
    UserManager's on_after_* hooks are how fastapi-users hands you the
    verification/reset token to put in an email; here we just capture it."""

    def __init__(self):
        self.token: str | None = None

    async def on_after_request_verify(self, user, token, request=None):
        self.token = token

    async def on_after_forgot_password(self, user, token, request=None):
        self.token = token


@pytest_asyncio.fixture()
def user_manager_factory(db_session: AsyncSession):
    """Returns an async factory that builds a UserManager bound to this
    test's db_session, with its on_after_* hooks capturing tokens instead of
    printing them."""
    from app.db import User

    def _make():
        user_db = SQLAlchemyUserDatabase(db_session, User)
        manager = UserManager(user_db)
        capture = _TokenCapture()
        manager.on_after_request_verify = capture.on_after_request_verify
        manager.on_after_forgot_password = capture.on_after_forgot_password
        return manager, capture

    return _make
