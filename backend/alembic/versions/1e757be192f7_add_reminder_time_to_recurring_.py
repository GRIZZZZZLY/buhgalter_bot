"""add_reminder_time_to_recurring_transactions

Revision ID: 1e757be192f7
Revises: c5c0590d619d
Create Date: 2026-03-28 22:06:44.650395
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1e757be192f7'
down_revision = 'c5c0590d619d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'recurring_transactions',
        sa.Column('reminder_time', sa.String(5), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('recurring_transactions', 'reminder_time')
