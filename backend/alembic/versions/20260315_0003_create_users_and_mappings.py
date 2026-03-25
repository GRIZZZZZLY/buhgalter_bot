"""create users and user_category_mappings tables

Revision ID: 20260315_0003
Revises: 20260314_0002
Create Date: 2026-03-15 15:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260315_0003"
down_revision = "20260314_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("timezone", sa.String(length=50), nullable=False, server_default="Europe/Moscow"),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="RUB"),
        sa.Column("budget_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("budget_start_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reminder_morning", sa.String(length=5), nullable=True, server_default="09:00"),
        sa.Column("reminder_evening", sa.String(length=5), nullable=True, server_default="21:00"),
        sa.Column("streak_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("streak_last_date", sa.String(length=10), nullable=True),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transactions_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transactions_today_date", sa.String(length=10), nullable=True),
        sa.Column("ignored_evening_reminders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_telegram_user_id"), "users", ["telegram_user_id"], unique=True)

    op.create_table(
        "user_category_mappings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("merchant_text", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id", "merchant_text", name="uq_user_merchant"),
    )
    op.create_index(op.f("ix_user_category_mappings_telegram_user_id"), "user_category_mappings", ["telegram_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_category_mappings_telegram_user_id"), table_name="user_category_mappings")
    op.drop_table("user_category_mappings")
    op.drop_index(op.f("ix_users_telegram_user_id"), table_name="users")
    op.drop_table("users")
