"""create voice logs

Revision ID: 20260314_0002
Revises: 20260314_0001
Create Date: 2026-03-14 09:05:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260314_0002"
down_revision = "20260314_0001"
branch_labels = None
depends_on = None


voice_log_status = sa.Enum("pending", "confirmed", "cancelled", "failed", name="voice_log_status", native_enum=False)


def upgrade() -> None:
    voice_log_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "voice_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("file_id", sa.String(length=255), nullable=True),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("parser_confidence", sa.Float(), nullable=True),
        sa.Column("parser_status", sa.String(length=50), nullable=True),
        sa.Column("status", voice_log_status, nullable=False),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_voice_logs_telegram_user_id"), "voice_logs", ["telegram_user_id"], unique=False)
    op.create_index(op.f("ix_voice_logs_telegram_message_id"), "voice_logs", ["telegram_message_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_voice_logs_telegram_message_id"), table_name="voice_logs")
    op.drop_index(op.f("ix_voice_logs_telegram_user_id"), table_name="voice_logs")
    op.drop_table("voice_logs")
    voice_log_status.drop(op.get_bind(), checkfirst=True)
