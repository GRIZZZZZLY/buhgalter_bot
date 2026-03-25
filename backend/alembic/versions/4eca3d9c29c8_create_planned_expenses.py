"""create_planned_expenses

Revision ID: 4eca3d9c29c8
Revises: 20260316_0007
Create Date: 2026-03-24 00:16:58.533521
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4eca3d9c29c8'
down_revision = '20260316_0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'planned_expenses',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=False, index=True),
        sa.Column('title', sa.String(100), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('planned_date', sa.Date(), nullable=False),
        sa.Column('source', sa.String(20), nullable=False, server_default='manual'),
        sa.Column('recurring_transaction_id', sa.Integer(), sa.ForeignKey('recurring_transactions.id'), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('reminder_sent_date', sa.String(10), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('planned_expenses')
