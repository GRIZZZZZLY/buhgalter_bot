"""add_is_hidden_to_user_categories

Revision ID: 1032ed89eefc
Revises: 20260324_0008
Create Date: 2026-03-26 00:59:41.625142
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1032ed89eefc'
down_revision = '20260324_0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_categories",
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("user_categories", "is_hidden")
