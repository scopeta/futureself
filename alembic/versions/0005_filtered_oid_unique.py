"""Make ix_users_oid a filtered unique index (SQL Server multi-NULL fix)

SQL Server's plain UNIQUE index rejects more than one NULL, but anonymous users
all have oid=NULL. Recreate the index filtered to non-NULL values so multiple
anonymous users are allowed while non-NULL oids stay unique. (Postgres/SQLite
already treat NULLs as distinct; the mssql_where filter is a no-op there.)

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-02
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_users_oid", table_name="users")
    op.create_index(
        "ix_users_oid",
        "users",
        ["oid"],
        unique=True,
        mssql_where=sa.text("oid IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_oid", table_name="users")
    op.create_index("ix_users_oid", "users", ["oid"], unique=True)
