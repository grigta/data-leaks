"""Add transactions table for billing

Revision ID: a1b2c3d4e5f6
Revises: 9686e6db3d3c
Create Date: 2025-10-30 01:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '9686e6db3d3c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create transactions table (enum types will be created automatically)
    op.create_table(
        'transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('payment_method', postgresql.ENUM('crypto', 'card', 'bank_transfer', name='paymentmethod', create_type=True), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'paid', 'expired', 'failed', name='transactionstatus', create_type=True), nullable=False),
        sa.Column('payment_provider', sa.String(length=100), nullable=True),
        sa.Column('external_transaction_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint('amount > 0', name='check_amount_positive'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('idx_transactions_user_id', 'transactions', ['user_id'])
    op.create_index('idx_transactions_status', 'transactions', ['status'])
    op.create_index('idx_transactions_created_at', 'transactions', ['created_at'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_transactions_created_at', table_name='transactions')
    op.drop_index('idx_transactions_status', table_name='transactions')
    op.drop_index('idx_transactions_user_id', table_name='transactions')

    # Drop table
    op.drop_table('transactions')

    # Drop enum types
    op.execute('DROP TYPE paymentmethod')
    op.execute('DROP TYPE transactionstatus')
