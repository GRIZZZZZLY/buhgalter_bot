"""create transactions

Revision ID: 20260314_0001
Revises: None
Create Date: 2026-03-14 08:55:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260314_0001"
down_revision = None
branch_labels = None
depends_on = None


transaction_type = sa.Enum("income", "expense", name="transaction_type", native_enum=False)
transaction_source = sa.Enum("text", "voice", name="transaction_source", native_enum=False)


def upgrade() -> None:
    transaction_type.create(op.get_bind(), checkfirst=True)
    transaction_source.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("type", transaction_type, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("source", transaction_source, nullable=False),
        sa.Column("raw_input", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_transactions_telegram_user_id"), "transactions", ["telegram_user_id"], unique=False)



def downgrade() -> None:
    op.drop_index(op.f("ix_transactions_telegram_user_id"), table_name="transactions")
    op.drop_table("transactions")
    transaction_source.drop(op.get_bind(), checkfirst=True)
    transaction_type.drop(op.get_bind(), checkfirst=True)
