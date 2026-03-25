"""create recurring_transactions table

Revision ID: 20260315_0006
Revises: 20260315_0005
Create Date: 2026-03-15 23:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260315_0006"
down_revision = "20260315_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recurring_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("transaction_type", sa.String(length=10), nullable=False, server_default="expense"),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("frequency", sa.String(length=10), nullable=False, server_default="monthly"),
        sa.Column("day_value", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("next_run_date", sa.String(length=10), nullable=False),
        sa.Column("reminder_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recurring_transactions_telegram_user_id"),
        "recurring_transactions",
        ["telegram_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_recurring_transactions_telegram_user_id"), table_name="recurring_transactions")
    op.drop_table("recurring_transactions")
