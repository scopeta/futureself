"""SQLAlchemy ORM models for FutureSelf persistence.

Four tables:
- users        — one row per user
- blueprints   — one row per user, stores the durable UserBlueprint as JSON
- sessions     — token → user_id mapping (+ Foundry thread_id for Phase 6+)
- messages     — append-only conversation transcript (one row per turn)

Backed by Azure SQL Database (dialect-agnostic types; tests run on SQLite).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# JSON maps to NVARCHAR(MAX) on SQL Server, JSON on SQLite/Postgres — one type,
# every dialect. (The store is a single serialized UserBlueprint per row.)
_JSONVariant = JSON()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    """One row per user."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    oid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """Entra ID `oid` claim (immutable per-user key). NULL for anonymous users."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    # Unique on oid, but only for non-NULL values: SQL Server rejects multiple
    # NULLs in a plain UNIQUE index (unlike Postgres/SQLite), and anonymous users
    # all have oid=NULL. The mssql_where filter is ignored on other dialects,
    # which already treat NULLs as distinct.
    __table_args__ = (
        Index("ix_users_oid", "oid", unique=True, mssql_where=text("oid IS NOT NULL")),
    )

    blueprint: Mapped["Blueprint"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Blueprint(Base):
    """Persisted UserBlueprint — one row per user, updated after every turn."""

    __tablename__ = "blueprints"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    data: Mapped[dict] = mapped_column(_JSONVariant, nullable=False, default=dict)
    """Durable UserBlueprint serialised via model_dump() (domain state only —
    no transcript). Stored as JSON (NVARCHAR(MAX) on SQL Server)."""
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="blueprint")


class Session(Base):
    """Bearer token → user mapping.

    thread_id is reserved for Foundry Agent Service (Phase 6+).
    """

    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    thread_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Foundry Agent Service thread ID — populated when migrating to Agent Service."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="sessions")


class Message(Base):
    """One conversation turn — append-only transcript, decoupled from the Blueprint.

    ``id`` is a global autoincrement (IDENTITY on SQL Server, rowid on SQLite), so
    it doubles as a monotonic per-user ordering key: "last N for a user" is
    ``WHERE user_id = ? ORDER BY id DESC LIMIT N``.
    """

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    """``"user"`` or ``"assistant"``."""
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_messages_user_id_id", "user_id", "id"),)
