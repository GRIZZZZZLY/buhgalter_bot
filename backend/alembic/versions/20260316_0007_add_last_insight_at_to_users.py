"""add last_insight_at to users

Revision ID: 20260316_0007
Revises: 20260315_0006
Create Date: 2026-03-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260316_0007"
down_revision = "20260315_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_insight_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "last_insight_at")
