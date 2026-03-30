"""document telegram_persistence table (managed by PTB)

Revision ID: 20260330_0001
Revises: 1e757be192f7
Create Date: 2026-03-30 00:00:00.000000

Note: The `telegram_persistence` table is created automatically by
python-telegram-bot's SQLAlchemyPersistence via metadata.create_all().
This migration documents its existence and provides a downgrade path.
"""
from alembic import op

revision = "20260330_0001"
down_revision = "1e757be192f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Table is created by PTB's SQLAlchemyPersistence on bot startup.
    pass


def downgrade() -> None:
    op.drop_table("telegram_persistence")
