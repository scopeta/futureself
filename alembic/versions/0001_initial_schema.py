"""Initial schema: users, blueprints, sessions

Revision ID: 0001
Revises:
Create Date: 2026-04-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ANSI default (valid on SQL Server, Postgres, SQLite) — the ORM also sets these
# Python-side, so this is just a DB-level fallback.
_NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
    )

    op.create_table(
        "blueprints",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        # Named FK so later migrations can drop it by name on any dialect
        # (SQL Server auto-generates FK names otherwise).
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", name="blueprints_user_id_fkey"),
            nullable=False,
            unique=True,
        ),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
    )

    op.create_table(
        "sessions",
        sa.Column("token", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", name="sessions_user_id_fkey"),
            nullable=False,
        ),
        sa.Column("thread_id", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("blueprints")
    op.drop_table("users")
