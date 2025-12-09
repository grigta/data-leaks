"""Add SMS rentals table and sms_code to phone_rentals

Revision ID: add_sms_rentals_001
Revises: add_renewal_discount_001
Create Date: 2025-12-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_sms_rentals_001'
down_revision = 'add_renewal_discount_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add sms_code column to phone_rentals
    op.add_column('phone_rentals', sa.Column('sms_code', sa.String(20), nullable=True))

    # Create sms_rentals table
    op.create_table(
        'sms_rentals',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('daisysms_id', sa.String(50), nullable=False),
        sa.Column('phone_number', sa.String(20), nullable=False),
        sa.Column('service_code', sa.String(50), nullable=False),
        sa.Column('service_name', sa.String(100), nullable=False),
        sa.Column('status', postgresql.ENUM('active', 'code_received', 'finished', 'cancelled', 'expired', name='phonerentalstatus', create_type=False), nullable=False, server_default='active'),
        sa.Column('base_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('user_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('refunded', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('sms_code', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('code_received_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    # Create indexes for sms_rentals
    op.create_index('idx_sms_rentals_user_id', 'sms_rentals', ['user_id'])
    op.create_index('idx_sms_rentals_status', 'sms_rentals', ['status'])
    op.create_index('idx_sms_rentals_daisysms_id', 'sms_rentals', ['daisysms_id'])
    op.create_index('idx_sms_rentals_created_at', 'sms_rentals', ['created_at'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_sms_rentals_created_at', table_name='sms_rentals')
    op.drop_index('idx_sms_rentals_daisysms_id', table_name='sms_rentals')
    op.drop_index('idx_sms_rentals_status', table_name='sms_rentals')
    op.drop_index('idx_sms_rentals_user_id', table_name='sms_rentals')

    # Drop table
    op.drop_table('sms_rentals')

    # Drop column from phone_rentals
    op.drop_column('phone_rentals', 'sms_code')
