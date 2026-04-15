"""Async SQLAlchemy engine and session factory.

Usage in FastAPI:
    from futureself.db.engine import get_db

    @router.post("/endpoint")
    async def handler(db: AsyncSession = Depends(get_db)):
        ...

Environment variable:
    DATABASE_URL — async PostgreSQL URL, e.g.:
        postgresql+asyncpg://user:pass@host:5432/futureself
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_engine = None
_session_factory = None


def _get_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Example: postgresql+asyncpg://user:pass@host:5432/futureself"
        )
    return url


def init_engine() -> None:
    """Initialise the async engine. Call once at application startup."""
    global _engine, _session_factory
    _engine = create_async_engine(_get_url(), echo=False, pool_pre_ping=True)
    _session_factory = async_sessionmaker(
        _engine, expire_on_commit=False, class_=AsyncSession
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session per request."""
    if _session_factory is None:
        raise RuntimeError("Database not initialised — call init_engine() at startup.")
    async with _session_factory() as session:
        yield session
