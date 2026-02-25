"""Add worker invoices and wallet fields

Revision ID: add_worker_invoices_001
Revises: add_worker_load_dist_001
Create Date: 2026-02-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_worker_invoices_001'
down_revision = 'add_worker_load_dist_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add wallet fields to users
    op.add_column('users', sa.Column('wallet_address', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('wallet_network', sa.String(20), nullable=True))

    # Create invoicestatus enum
    invoicestatus = postgresql.ENUM('pending', 'paid', name='invoicestatus', create_type=False)
    invoicestatus.create(op.get_bind(), checkfirst=True)

    # Create worker_invoices table
    op.create_table(
        'worker_invoices',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('worker_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('wallet_address', sa.String(255), nullable=False),
        sa.Column('wallet_network', sa.String(20), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'paid', name='invoicestatus', create_type=False), server_default='pending', nullable=False),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('amount > 0', name='check_invoice_amount_positive'),
    )

    # Create indexes
    op.create_index('idx_worker_invoices_worker_id', 'worker_invoices', ['worker_id'])
    op.create_index('idx_worker_invoices_status', 'worker_invoices', ['status'])
    op.create_index('idx_worker_invoices_worker_status', 'worker_invoices', ['worker_id', 'status'])
    op.create_index('idx_worker_invoices_created_at', 'worker_invoices', ['created_at'])


def downgrade() -> None:
    op.drop_table('worker_invoices')
    op.drop_column('users', 'wallet_network')
    op.drop_column('users', 'wallet_address')

    # Drop enum
    invoicestatus = postgresql.ENUM('pending', 'paid', name='invoicestatus', create_type=False)
    invoicestatus.drop(op.get_bind(), checkfirst=True)
