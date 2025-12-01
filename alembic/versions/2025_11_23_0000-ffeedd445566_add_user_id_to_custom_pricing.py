"""add_user_id_to_custom_pricing

Revision ID: ffeedd445566
Revises: ccddee334455
Create Date: 2025-11-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ffeedd445566'
down_revision = 'ccddee334455'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add user_id column
    op.add_column('custom_pricing', sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True))

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_custom_pricing_user_id_users',
        'custom_pricing',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # Make access_code nullable
    op.alter_column('custom_pricing', 'access_code', nullable=True)

    # Add check constraint to ensure at least one identifier is provided
    op.create_check_constraint(
        'check_custom_pricing_identifier_required',
        'custom_pricing',
        '(access_code IS NOT NULL) OR (user_id IS NOT NULL)'
    )

    # Add index on user_id
    op.create_index('idx_custom_pricing_user_id', 'custom_pricing', ['user_id'])

    # Add unique constraint for user_id + service_name
    op.create_unique_constraint(
        'uq_custom_pricing_user_service',
        'custom_pricing',
        ['user_id', 'service_name']
    )


def downgrade() -> None:
    # Drop unique constraint
    op.drop_constraint('uq_custom_pricing_user_service', 'custom_pricing', type_='unique')

    # Drop index
    op.drop_index('idx_custom_pricing_user_id', 'custom_pricing')

    # Drop check constraint
    op.drop_constraint('check_custom_pricing_identifier_required', 'custom_pricing', type_='check')

    # Restore access_code to non-nullable
    op.alter_column('custom_pricing', 'access_code', nullable=False)

    # Drop foreign key constraint
    op.drop_constraint('fk_custom_pricing_user_id_users', 'custom_pricing', type_='foreignkey')

    # Drop user_id column
    op.drop_column('custom_pricing', 'user_id')
