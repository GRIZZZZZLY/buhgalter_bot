"""create user_categories table

Revision ID: 20260324_0008
Revises: 20260316_0007
Create Date: 2026-03-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260324_0008"
down_revision = "4eca3d9c29c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("name_ru", sa.String(length=100), nullable=False),
        sa.Column("emoji", sa.String(length=10), nullable=False),
        sa.Column("type", sa.String(length=10), nullable=False),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id", "slug", name="uq_user_category_slug"),
    )
    op.create_index(
        op.f("ix_user_categories_telegram_user_id"),
        "user_categories",
        ["telegram_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_user_categories_telegram_user_id"),
        table_name="user_categories",
    )
    op.drop_table("user_categories")
