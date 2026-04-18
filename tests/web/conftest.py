"""Fixtures for FastAPI route tests.

Sets up an in-memory SQLite database shared across async sessions (StaticPool +
single connection) so the tests exercise the real persistence layer.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from futureself.db import engine as engine_module
from futureself.db.engine import get_db
from futureself.db.models import Base


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[object]:
    """In-memory SQLite async engine. Uses StaticPool so every session shares
    the same underlying connection (required for ``:memory:`` SQLite)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(db_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def db(db_session_factory) -> AsyncIterator[AsyncSession]:
    """Direct DB session for unit tests of the persistence layer."""
    async with db_session_factory() as session:
        yield session


@pytest.fixture
def app(monkeypatch, db_session_factory) -> FastAPI:
    """FastAPI app with its DB dependency bound to the in-memory test engine.

    ``init_engine()`` is replaced with a no-op so ``create_app()`` doesn't
    clobber the test engine globals. ``get_db`` is then overridden to yield
    sessions from the test factory.
    """
    monkeypatch.setattr(engine_module, "init_engine", lambda: None)

    from futureself.web.app import create_app  # noqa: PLC0415

    application = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with db_session_factory() as session:
            yield session

    application.dependency_overrides[get_db] = _override_get_db
    return application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
