"""add_reminder_time_to_planned_expenses

Revision ID: c5c0590d619d
Revises: 20260326_0002
Create Date: 2026-03-28 21:39:25.349201
"""
from alembic import op
import sqlalchemy as sa


revision = 'c5c0590d619d'
down_revision = '20260326_0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'planned_expenses',
        sa.Column('reminder_time', sa.String(5), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('planned_expenses', 'reminder_time')
