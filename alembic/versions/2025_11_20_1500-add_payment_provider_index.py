"""add payment provider index

Revision ID: payment_provider_idx_001
Revises: 99aa11bb22cc
Create Date: 2025-11-20 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'payment_provider_idx_001'
down_revision = '99aa11bb22cc'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add index on payment_provider for faster filtering and add check constraint
    for valid payment providers.

    This migration is optional - the payment_provider field already exists in
    the transactions table, this just adds performance optimizations.
    """
    # Add index on payment_provider for faster filtering
    op.create_index(
        'ix_transactions_payment_provider',
        'transactions',
        ['payment_provider'],
        unique=False
    )

    # Add check constraint for valid providers (optional, for data integrity)
    # This will prevent invalid provider names from being inserted
    op.create_check_constraint(
        'check_valid_payment_provider',
        'transactions',
        "payment_provider IN ('cryptocurrencyapi', 'helket', 'ffio') OR payment_provider IS NULL"
    )


def downgrade():
    """
    Remove the index and check constraint.
    """
    # Drop the check constraint first
    op.drop_constraint('check_valid_payment_provider', 'transactions', type_='check')

    # Drop the index
    op.drop_index('ix_transactions_payment_provider', table_name='transactions')
