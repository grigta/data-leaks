"""add_order_id_to_manual_ssn_tickets

Revision ID: ffgg778899bb
Revises: eeff667788aa
Create Date: 2025-11-26 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ffgg778899bb'
down_revision = 'ffgg778899aa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add order_id column to manual_ssn_tickets
    op.add_column('manual_ssn_tickets',
                  sa.Column('order_id',
                           postgresql.UUID(as_uuid=True),
                           nullable=True))

    # Create foreign key constraint
    op.create_foreign_key(
        'fk_manual_ssn_tickets_order_id',
        'manual_ssn_tickets', 'orders',
        ['order_id'], ['id'],
        ondelete='SET NULL'
    )

    # Create index for better query performance
    op.create_index('idx_manual_ssn_tickets_order_id', 'manual_ssn_tickets', ['order_id'])


def downgrade() -> None:
    # Drop index
    op.drop_index('idx_manual_ssn_tickets_order_id', table_name='manual_ssn_tickets')

    # Drop foreign key constraint
    op.drop_constraint('fk_manual_ssn_tickets_order_id', 'manual_ssn_tickets', type_='foreignkey')

    # Drop column
    op.drop_column('manual_ssn_tickets', 'order_id')
