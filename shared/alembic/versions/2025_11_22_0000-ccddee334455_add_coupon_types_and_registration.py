"""add_coupon_types_and_registration

Revision ID: ccddee334455
Revises: bbccdd223344
Create Date: 2025-11-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ccddee334455'
down_revision = 'bbccdd223344'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create coupontype enum
    op.execute("CREATE TYPE coupontype AS ENUM ('percentage', 'fixed_amount', 'registration', 'registration_bonus')")

    # Add coupon_type column
    op.add_column('coupons', sa.Column('coupon_type',
        postgresql.ENUM('percentage', 'fixed_amount', 'registration', 'registration_bonus', name='coupontype'),
        nullable=False,
        server_default='percentage'))

    # Add bonus_amount column
    op.add_column('coupons', sa.Column('bonus_amount', sa.Numeric(10, 2), nullable=True))

    # Add requires_registration column
    op.add_column('coupons', sa.Column('requires_registration', sa.Boolean(), nullable=False, server_default='false'))

    # Add check constraint for bonus_amount
    op.create_check_constraint('check_bonus_amount_positive', 'coupons', 'bonus_amount IS NULL OR bonus_amount > 0')

    # Make bonus_percent nullable
    op.alter_column('coupons', 'bonus_percent', nullable=True)

    # Drop old check_bonus_percent_range constraint and create new one that only applies to percentage coupons
    op.drop_constraint('check_bonus_percent_range', 'coupons', type_='check')
    op.create_check_constraint(
        'check_bonus_percent_range',
        'coupons',
        "bonus_percent IS NULL OR (coupon_type = 'percentage' AND bonus_percent > 0 AND bonus_percent <= 100)"
    )

    # Create index on coupon_type
    op.create_index('idx_coupons_coupon_type', 'coupons', ['coupon_type'])

    # Update existing coupons to set coupon_type = 'percentage'
    op.execute("UPDATE coupons SET coupon_type = 'percentage' WHERE coupon_type IS NULL")


def downgrade() -> None:
    # Drop index
    op.drop_index('idx_coupons_coupon_type', table_name='coupons')

    # Restore old check_bonus_percent_range constraint
    op.drop_constraint('check_bonus_percent_range', 'coupons', type_='check')
    op.create_check_constraint('check_bonus_percent_range', 'coupons', 'bonus_percent > 0 AND bonus_percent <= 100')

    # Restore bonus_percent to NOT NULL
    op.alter_column('coupons', 'bonus_percent', nullable=False)

    # Drop check constraint
    op.drop_constraint('check_bonus_amount_positive', 'coupons', type_='check')

    # Drop columns
    op.drop_column('coupons', 'requires_registration')
    op.drop_column('coupons', 'bonus_amount')
    op.drop_column('coupons', 'coupon_type')

    # Drop enum type
    op.execute('DROP TYPE coupontype')
