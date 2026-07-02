"""Add messages table (conversation transcript, decoupled from the Blueprint)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-02
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "messages",
        # Global autoincrement (IDENTITY on SQL Server) — doubles as a monotonic
        # per-user ordering key for "last N".
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", name="messages_user_id_fkey", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_messages_user_id_id", "messages", ["user_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_messages_user_id_id", table_name="messages")
    op.drop_table("messages")
