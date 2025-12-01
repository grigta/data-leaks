"""Add payment_address and payment_metadata fields to transactions

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2025-10-30 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6g7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add payment_metadata field (JSON) for storing IPN data
    op.add_column('transactions',
        sa.Column('payment_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True)
    )

    # Add payment_address field for crypto payment addresses
    op.add_column('transactions',
        sa.Column('payment_address', sa.String(length=255), nullable=True)
    )

    # Create index on external_transaction_id for fast lookups by txid
    op.create_index('idx_transactions_external_id', 'transactions', ['external_transaction_id'])


def downgrade() -> None:
    # Drop index
    op.drop_index('idx_transactions_external_id', table_name='transactions')

    # Drop columns
    op.drop_column('transactions', 'payment_address')
    op.drop_column('transactions', 'payment_metadata')
