"""create category_budgets table

Revision ID: 20260315_0004
Revises: 20260315_0003
Create Date: 2026-03-15 16:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260315_0004"
down_revision = "20260315_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "category_budgets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id", "category", name="uq_user_category_budget"),
    )
    op.create_index(op.f("ix_category_budgets_telegram_user_id"), "category_budgets", ["telegram_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_category_budgets_telegram_user_id"), table_name="category_budgets")
    op.drop_table("category_budgets")
