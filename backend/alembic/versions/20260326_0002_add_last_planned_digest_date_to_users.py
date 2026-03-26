"""add last_planned_digest_date to users

Revision ID: 20260326_0002
Revises: 1032ed89eefc
Create Date: 2026-03-26 20:12:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260326_0002"
down_revision = "1032ed89eefc"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("users", "last_planned_digest_date"):
        op.add_column(
            "users",
            sa.Column("last_planned_digest_date", sa.String(length=10), nullable=True),
        )


def downgrade() -> None:
    if _has_column("users", "last_planned_digest_date"):
        op.drop_column("users", "last_planned_digest_date")
