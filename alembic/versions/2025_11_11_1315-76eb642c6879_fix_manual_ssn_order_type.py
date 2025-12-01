"""fix_manual_ssn_order_type

Revision ID: 76eb642c6879
Revises: e9f8d7c6b5a4
Create Date: 2025-11-11 13:15:56.796747

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '76eb642c6879'
down_revision = 'e9f8d7c6b5a4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Fix order_type for existing manual_ssn orders.

    Orders created from manual tickets before the order_type column was added
    were assigned the default value 'reverse_ssn'. This migration corrects
    those orders by checking if items contain '"source": "manual_ticket"' and
    updating their order_type to 'manual_ssn'.
    """
    # Update orders that have manual_ticket in their items JSON
    # Using simple text search since items is JSON type
    op.execute("""
        UPDATE orders
        SET order_type = 'manual_ssn'
        WHERE order_type = 'reverse_ssn'
        AND items::text LIKE '%manual_ticket%';
    """)


def downgrade() -> None:
    """
    Revert manual_ssn orders back to reverse_ssn.

    Note: This will incorrectly classify manual ticket orders as reverse_ssn orders.
    Only use this downgrade if you need to rollback to a previous state.
    """
    op.execute("""
        UPDATE orders
        SET order_type = 'reverse_ssn'
        WHERE order_type = 'manual_ssn'
        AND items::text LIKE '%manual_ticket%';
    """)
