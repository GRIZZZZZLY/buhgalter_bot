"""create savings_goals table

Revision ID: 20260330_0004
Revises: 20260330_0003
Create Date: 2026-03-30
"""
from alembic import op
import sqlalchemy as sa

revision = "20260330_0004"
down_revision = "20260330_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "savings_goals",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False, index=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("target_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("current_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("deadline", sa.Date, nullable=True),
        sa.Column("auto_percent", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("savings_goals")
