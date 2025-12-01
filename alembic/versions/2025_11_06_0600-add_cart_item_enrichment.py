"""Add enrichment metadata to CartItem

Revision ID: cart_enrichment_001
Revises: e5f6g7h8i9j0
Create Date: 2025-11-06 06:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'cart_enrichment_001'
down_revision = 'e5f6g7h8i9j0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add enrichment metadata columns to cart_items
    op.add_column('cart_items', sa.Column('enrichment_attempted', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('cart_items', sa.Column('enrichment_success', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('cart_items', sa.Column('enrichment_cost', sa.Numeric(10, 2), nullable=True))
    op.add_column('cart_items', sa.Column('enrichment_timestamp', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Remove enrichment metadata columns from cart_items
    op.drop_column('cart_items', 'enrichment_timestamp')
    op.drop_column('cart_items', 'enrichment_cost')
    op.drop_column('cart_items', 'enrichment_success')
    op.drop_column('cart_items', 'enrichment_attempted')
