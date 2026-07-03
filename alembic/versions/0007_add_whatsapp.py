"""Add WhatsApp channel columns (phone + link code)

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-03
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(length=32), nullable=True))
    op.add_column(
        "users", sa.Column("whatsapp_link_code", sa.String(length=12), nullable=True)
    )
    # Filtered unique index (SQL Server multi-NULL fix; no-op filter elsewhere).
    op.create_index(
        "ix_users_phone",
        "users",
        ["phone"],
        unique=True,
        mssql_where=sa.text("phone IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_column("users", "whatsapp_link_code")
    op.drop_column("users", "phone")
