"""Add users.oid (Entra ID object id) for authenticated users

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-24
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("oid", sa.String(length=64), nullable=True))
    op.create_index("ix_users_oid", "users", ["oid"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_oid", table_name="users")
    op.drop_column("users", "oid")
