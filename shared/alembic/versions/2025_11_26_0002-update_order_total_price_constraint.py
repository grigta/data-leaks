"""update_order_total_price_constraint

Revision ID: gghhii990011
Revises: ffgg778899bb
Create Date: 2025-11-26 00:02:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'gghhii990011'
down_revision = 'ffgg778899bb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Constraint was already changed in migration 1c6882f459ae (allow_zero_price_for_orders)
    # check_total_price_non_negative with >= 0 already exists
    pass


def downgrade() -> None:
    # Nothing to do - constraint was changed in earlier migration
    pass
