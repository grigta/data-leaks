"""Add currency and network fields to transactions

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2025-10-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd4e5f6g7h8i9'
down_revision = 'b2c3d4e5f6g7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add currency field for storing cryptocurrency code (USDT, BTC, ETH, BNB, LTC)
    op.add_column('transactions',
        sa.Column('currency', sa.String(length=20), nullable=True)
    )

    # Add network field for storing blockchain network (TRC20, ERC20, BSC, MAINNET)
    op.add_column('transactions',
        sa.Column('network', sa.String(length=20), nullable=True)
    )

    # Create index on currency for efficient filtering
    op.create_index('idx_transactions_currency', 'transactions', ['currency'])


def downgrade() -> None:
    # Drop index
    op.drop_index('idx_transactions_currency', table_name='transactions')

    # Drop columns
    op.drop_column('transactions', 'network')
    op.drop_column('transactions', 'currency')
