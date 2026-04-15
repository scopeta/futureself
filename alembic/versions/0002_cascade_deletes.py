"""Add ON DELETE CASCADE to blueprints and sessions foreign keys

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-15
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # blueprints.user_id → users.id
    op.drop_constraint("blueprints_user_id_fkey", "blueprints", type_="foreignkey")
    op.create_foreign_key(
        "blueprints_user_id_fkey",
        "blueprints", "users",
        ["user_id"], ["id"],
        ondelete="CASCADE",
    )

    # sessions.user_id → users.id
    op.drop_constraint("sessions_user_id_fkey", "sessions", type_="foreignkey")
    op.create_foreign_key(
        "sessions_user_id_fkey",
        "sessions", "users",
        ["user_id"], ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("blueprints_user_id_fkey", "blueprints", type_="foreignkey")
    op.create_foreign_key(
        "blueprints_user_id_fkey",
        "blueprints", "users",
        ["user_id"], ["id"],
    )

    op.drop_constraint("sessions_user_id_fkey", "sessions", type_="foreignkey")
    op.create_foreign_key(
        "sessions_user_id_fkey",
        "sessions", "users",
        ["user_id"], ["id"],
    )
