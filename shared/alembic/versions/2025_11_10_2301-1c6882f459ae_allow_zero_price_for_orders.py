"""allow_zero_price_for_orders

Revision ID: 1c6882f459ae
Revises: 42cdcc46da40
Create Date: 2025-11-10 23:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c6882f459ae'
down_revision: Union[str, None] = '42cdcc46da40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old constraint
    op.drop_constraint('check_total_price_positive', 'orders', type_='check')

    # Add new constraint that allows zero or positive prices
    op.create_check_constraint(
        'check_total_price_non_negative',
        'orders',
        'total_price >= 0'
    )


def downgrade() -> None:
    # Drop the new constraint
    op.drop_constraint('check_total_price_non_negative', 'orders', type_='check')

    # Re-create the old constraint
    op.create_check_constraint(
        'check_total_price_positive',
        'orders',
        'total_price > 0'
    )
