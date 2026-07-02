"""Alembic environment configuration for FutureSelf.

Reads DATABASE_URL from the environment (sync URL for migrations).
Uses the SQLAlchemy metadata from futureself.db.models.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from futureself.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url() -> str:
    """Return a sync DB URL for alembic (migrations run synchronously).

    Swaps the async driver for its sync counterpart: Azure SQL
    ``mssql+aioodbc`` → ``mssql+pyodbc`` (and legacy ``postgresql+asyncpg`` →
    ``postgresql+psycopg2``).
    """
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL env var is required for migrations.")
    return (
        url.replace("mssql+aioodbc://", "mssql+pyodbc://")
        .replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # 30s login timeout so a broken connection errors fast instead of hanging.
    connectable = create_engine(
        _sync_url(), poolclass=pool.NullPool, connect_args={"timeout": 30}
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
