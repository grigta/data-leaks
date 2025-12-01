"""Add admin fields to users and create coupons system

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2025-11-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'e5f6g7h8i9j0'
down_revision = 'd4e5f6g7h8i9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add admin fields to users table
    op.add_column('users',
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false')
    )
    op.add_column('users',
        sa.Column('totp_secret', sa.String(length=32), nullable=True)
    )

    # Create index on is_admin
    op.create_index('idx_users_is_admin', 'users', ['is_admin'])

    # Create coupons table
    op.create_table(
        'coupons',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('bonus_percent', sa.Integer(), nullable=False),
        sa.Column('max_uses', sa.Integer(), nullable=False),
        sa.Column('current_uses', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint('bonus_percent > 0 AND bonus_percent <= 100', name='check_bonus_percent_range'),
        sa.CheckConstraint('max_uses > 0', name='check_max_uses_positive'),
        sa.CheckConstraint('current_uses >= 0', name='check_current_uses_non_negative'),
        sa.CheckConstraint('current_uses <= max_uses', name='check_current_uses_within_limit'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )

    # Create indexes for coupons table
    # Note: idx_coupons_code removed - unique constraint on 'code' is sufficient
    op.create_index('idx_coupons_is_active', 'coupons', ['is_active'])

    # Create user_coupons junction table
    op.create_table(
        'user_coupons',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('coupon_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('applied_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['coupon_id'], ['coupons.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'coupon_id', name='uq_user_coupon')
    )

    # Create indexes for user_coupons table
    op.create_index('idx_user_coupons_user_id', 'user_coupons', ['user_id'])
    op.create_index('idx_user_coupons_coupon_id', 'user_coupons', ['coupon_id'])


def downgrade() -> None:
    # Drop user_coupons table and indexes
    op.drop_index('idx_user_coupons_coupon_id', table_name='user_coupons')
    op.drop_index('idx_user_coupons_user_id', table_name='user_coupons')
    op.drop_table('user_coupons')

    # Drop coupons table and indexes
    op.drop_index('idx_coupons_is_active', table_name='coupons')
    # Note: idx_coupons_code was not created in upgrade
    op.drop_table('coupons')

    # Remove admin fields from users table
    op.drop_index('idx_users_is_admin', table_name='users')
    op.drop_column('users', 'totp_secret')
    op.drop_column('users', 'is_admin')
