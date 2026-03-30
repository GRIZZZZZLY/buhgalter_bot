"""create events table

Revision ID: 20260330_0003
Revises: 20260330_0001
Create Date: 2026-03-30 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "20260330_0003"
down_revision = "20260330_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("source", sa.String(16), nullable=True),
        sa.Column("meta", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_user_id", "events", ["user_id"])
    op.create_index("ix_events_event_type", "events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_events_event_type", table_name="events")
    op.drop_index("ix_events_user_id", table_name="events")
    op.drop_table("events")
