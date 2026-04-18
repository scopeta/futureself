"""SQLAlchemy ORM models for FutureSelf persistence.

Three tables:
- users        — one row per user
- blueprints   — one row per user, stores full UserBlueprint as JSONB
- sessions     — token → user_id mapping (+ Foundry thread_id for Phase 6+)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

_JSONVariant = JSON().with_variant(JSONB(), "postgresql")


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    blueprint: Mapped["Blueprint"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    sessions: Mapped[list["Session"]] = relationship(
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
    """Full UserBlueprint serialised via model_dump() — JSONB on postgres, JSON elsewhere."""
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
