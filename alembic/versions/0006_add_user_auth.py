"""Add email/password columns for email-based login

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-03
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=320), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    # Filtered unique index (SQL Server multi-NULL fix; no-op filter elsewhere).
    op.create_index(
        "ix_users_email",
        "users",
        ["email"],
        unique=True,
        mssql_where=sa.text("email IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
