"""Add phone lookup tables

Revision ID: add_phone_lookup_001
Revises: 9f689bdfe298
Create Date: 2025-12-08 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_phone_lookup_001'
down_revision = '9f689bdfe298'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create PhoneRentalStatus enum
    phonerentalstatus_enum = postgresql.ENUM(
        'active', 'expired', 'cancelled', 'finished',
        name='phonerentalstatus',
        create_type=False
    )
    phonerentalstatus_enum.create(op.get_bind(), checkfirst=True)

    # Add phone_lookup to OrderType enum
    op.execute("ALTER TYPE ordertype ADD VALUE IF NOT EXISTS 'phone_lookup'")

    # Create phone_rentals table
    op.create_table('phone_rentals',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('daisysms_id', sa.String(50), nullable=False),
        sa.Column('phone_number', sa.String(20), nullable=False),
        sa.Column('service_code', sa.String(50), nullable=False),
        sa.Column('service_name', sa.String(100), nullable=False),
        sa.Column('status', postgresql.ENUM('active', 'expired', 'cancelled', 'finished', name='phonerentalstatus', create_type=False), nullable=False, server_default='active'),
        sa.Column('auto_renew', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('searchbug_data', sa.JSON(), nullable=True),
        sa.Column('ssn_found', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('ssn_data', sa.JSON(), nullable=True),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('renewed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_phone_rentals_user_id', 'phone_rentals', ['user_id'], unique=False)
    op.create_index('idx_phone_rentals_daisysms_id', 'phone_rentals', ['daisysms_id'], unique=False)
    op.create_index('idx_phone_rentals_status', 'phone_rentals', ['status'], unique=False)
    op.create_index('idx_phone_rentals_created_at', 'phone_rentals', ['created_at'], unique=False)
    op.create_index('idx_phone_rentals_service_code', 'phone_rentals', ['service_code'], unique=False)

    # Create phone_lookup_searches table
    op.create_table('phone_lookup_searches',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('rental_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('service_code', sa.String(50), nullable=False),
        sa.Column('phone_number', sa.String(20), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('ssn_found', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('user_charged', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0.00'),
        sa.Column('source', postgresql.ENUM('web', 'telegram_bot', 'other', name='requestsource', create_type=False), nullable=False, server_default='web'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint('user_charged >= 0', name='check_phone_lookup_user_charged_non_negative'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['rental_id'], ['phone_rentals.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_phone_lookup_searches_user_id', 'phone_lookup_searches', ['user_id'], unique=False)
    op.create_index('idx_phone_lookup_searches_rental_id', 'phone_lookup_searches', ['rental_id'], unique=False)
    op.create_index('idx_phone_lookup_searches_service_code', 'phone_lookup_searches', ['service_code'], unique=False)
    op.create_index('idx_phone_lookup_searches_created_at', 'phone_lookup_searches', ['created_at'], unique=False)
    op.create_index('idx_phone_lookup_searches_ssn_found', 'phone_lookup_searches', ['ssn_found'], unique=False)


def downgrade() -> None:
    # Drop phone_lookup_searches table and indexes
    op.drop_index('idx_phone_lookup_searches_ssn_found', table_name='phone_lookup_searches')
    op.drop_index('idx_phone_lookup_searches_created_at', table_name='phone_lookup_searches')
    op.drop_index('idx_phone_lookup_searches_service_code', table_name='phone_lookup_searches')
    op.drop_index('idx_phone_lookup_searches_rental_id', table_name='phone_lookup_searches')
    op.drop_index('idx_phone_lookup_searches_user_id', table_name='phone_lookup_searches')
    op.drop_table('phone_lookup_searches')

    # Drop phone_rentals table and indexes
    op.drop_index('idx_phone_rentals_service_code', table_name='phone_rentals')
    op.drop_index('idx_phone_rentals_created_at', table_name='phone_rentals')
    op.drop_index('idx_phone_rentals_status', table_name='phone_rentals')
    op.drop_index('idx_phone_rentals_daisysms_id', table_name='phone_rentals')
    op.drop_index('idx_phone_rentals_user_id', table_name='phone_rentals')
    op.drop_table('phone_rentals')

    # Drop PhoneRentalStatus enum
    phonerentalstatus_enum = postgresql.ENUM(
        'active', 'expired', 'cancelled', 'finished',
        name='phonerentalstatus'
    )
    phonerentalstatus_enum.drop(op.get_bind(), checkfirst=True)

    # Note: Cannot easily remove 'phone_lookup' from OrderType enum in PostgreSQL
    # This would require recreating the enum type and all columns using it
