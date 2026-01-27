"""add_renewal_discount_percent_to_subscription_plans

Revision ID: add_renewal_discount_001
Revises: add_subscription_001
Create Date: 2025-12-08 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_renewal_discount_001'
down_revision = 'add_subscription_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'subscription_plans',
        sa.Column('renewal_discount_percent', sa.Integer(), nullable=False, server_default='0')
    )


def downgrade() -> None:
    op.drop_column('subscription_plans', 'renewal_discount_percent')
