"""Add missing indexes for phone_rentals, phone_lookup_searches, and sms_rentals

Revision ID: add_missing_indexes_001
Revises: add_sms_rentals_001
Create Date: 2025-12-09
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'add_missing_indexes_001'
down_revision = 'add_sms_rentals_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Fix missing service_code index in sms_rentals (defined in model but not in migration)
    op.create_index('idx_sms_rentals_service_code', 'sms_rentals', ['service_code'], unique=False)

    # 2. Composite indexes for pagination (user_id, created_at)
    op.create_index('idx_phone_rentals_user_created', 'phone_rentals', ['user_id', 'created_at'], unique=False)
    op.create_index('idx_sms_rentals_user_created', 'sms_rentals', ['user_id', 'created_at'], unique=False)
    op.create_index('idx_phone_lookup_searches_user_created', 'phone_lookup_searches', ['user_id', 'created_at'], unique=False)

    # 3. Composite index for active rentals lookup
    op.create_index('idx_phone_rentals_user_status', 'phone_rentals', ['user_id', 'status'], unique=False)


def downgrade() -> None:
    # Drop composite indexes
    op.drop_index('idx_phone_rentals_user_status', table_name='phone_rentals')
    op.drop_index('idx_phone_lookup_searches_user_created', table_name='phone_lookup_searches')
    op.drop_index('idx_sms_rentals_user_created', table_name='sms_rentals')
    op.drop_index('idx_phone_rentals_user_created', table_name='phone_rentals')
    op.drop_index('idx_sms_rentals_service_code', table_name='sms_rentals')
