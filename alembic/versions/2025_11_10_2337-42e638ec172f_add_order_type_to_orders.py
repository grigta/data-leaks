"""add_order_type_to_orders

Revision ID: 42e638ec172f
Revises: 1c6882f459ae
Create Date: 2025-11-10 23:37:58.022477

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '42e638ec172f'
down_revision = '1c6882f459ae'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the ordertype enum
    ordertype_enum = postgresql.ENUM('reverse_ssn', 'instant_ssn', 'manual_ssn', name='ordertype')
    ordertype_enum.create(op.get_bind())

    # Add order_type column with default value 'reverse_ssn'
    op.add_column('orders', sa.Column('order_type', ordertype_enum, nullable=False, server_default='reverse_ssn'))

    # Create indexes
    op.create_index('idx_orders_order_type', 'orders', ['order_type'], unique=False)
    op.create_index('idx_orders_user_type', 'orders', ['user_id', 'order_type'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_orders_user_type', table_name='orders')
    op.drop_index('idx_orders_order_type', table_name='orders')

    # Drop the column
    op.drop_column('orders', 'order_type')

    # Drop the enum type
    ordertype_enum = postgresql.ENUM('reverse_ssn', 'instant_ssn', 'manual_ssn', name='ordertype')
    ordertype_enum.drop(op.get_bind())
