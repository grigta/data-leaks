"""add_is_viewed_to_orders

Revision ID: 9686e6db3d3c
Revises: 3972d4a2cc0c
Create Date: 2025-10-29 16:34:46.931017

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9686e6db3d3c'
down_revision = '3972d4a2cc0c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_viewed column with default False
    op.add_column('orders', sa.Column('is_viewed', sa.Boolean(), nullable=False, server_default='false'))

    # Create index for faster queries
    op.create_index('idx_orders_is_viewed', 'orders', ['is_viewed'])

    # Mark all existing orders as viewed to avoid confusion
    op.execute("UPDATE orders SET is_viewed = true")


def downgrade() -> None:
    # Drop index
    op.drop_index('idx_orders_is_viewed', table_name='orders')

    # Drop column
    op.drop_column('orders', 'is_viewed')
