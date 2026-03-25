"""fix sqlite user primary keys

Revision ID: 20260315_0005
Revises: 20260315_0004
Create Date: 2026-03-15 22:45:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260315_0005"
down_revision = "20260315_0004"
branch_labels = None
depends_on = None


def _get_sqlite_column_type(table_name: str, column_name: str) -> str | None:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
    for row in rows:
        if row[1] == column_name:
            return str(row[2]).upper()
    return None


def _rebuild_users_table() -> None:
    op.create_table(
        "users_new",
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
    op.execute(
        sa.text(
            """
            INSERT INTO users_new (
                id, telegram_user_id, display_name, timezone, currency,
                budget_amount, budget_start_day, reminder_morning, reminder_evening,
                streak_days, streak_last_date, last_active_at, transactions_today,
                transactions_today_date, ignored_evening_reminders, created_at, updated_at
            )
            SELECT
                id, telegram_user_id, display_name, timezone, currency,
                budget_amount, budget_start_day, reminder_morning, reminder_evening,
                streak_days, streak_last_date, last_active_at, transactions_today,
                transactions_today_date, ignored_evening_reminders, created_at, updated_at
            FROM users
            """
        )
    )
    op.drop_index(op.f("ix_users_telegram_user_id"), table_name="users")
    op.drop_table("users")
    op.rename_table("users_new", "users")
    op.create_index(op.f("ix_users_telegram_user_id"), "users", ["telegram_user_id"], unique=True)


def _rebuild_mappings_table() -> None:
    op.create_table(
        "user_category_mappings_new",
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
    op.execute(
        sa.text(
            """
            INSERT INTO user_category_mappings_new (
                id, telegram_user_id, merchant_text, category, usage_count, created_at, updated_at
            )
            SELECT
                id, telegram_user_id, merchant_text, category, usage_count, created_at, updated_at
            FROM user_category_mappings
            """
        )
    )
    op.drop_index(op.f("ix_user_category_mappings_telegram_user_id"), table_name="user_category_mappings")
    op.drop_table("user_category_mappings")
    op.rename_table("user_category_mappings_new", "user_category_mappings")
    op.create_index(
        op.f("ix_user_category_mappings_telegram_user_id"),
        "user_category_mappings",
        ["telegram_user_id"],
        unique=False,
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    if _get_sqlite_column_type("users", "id") == "BIGINT":
        _rebuild_users_table()

    if _get_sqlite_column_type("user_category_mappings", "id") == "BIGINT":
        _rebuild_mappings_table()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
