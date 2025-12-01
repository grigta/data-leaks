"""add_is_viewed_to_manual_ssn_tickets

Revision ID: aec8a3af6743
Revises: aabbcc112233
Create Date: 2025-11-20 18:09:07.105932

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aec8a3af6743'
down_revision = 'aabbcc112233'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_viewed column with default False
    op.add_column('manual_ssn_tickets', sa.Column('is_viewed', sa.Boolean(), nullable=False, server_default='false'))

    # Create index for better query performance
    op.create_index('idx_manual_ssn_tickets_is_viewed', 'manual_ssn_tickets', ['is_viewed'])

    # Set all existing tickets as viewed (optional, based on business logic)
    # op.execute("UPDATE manual_ssn_tickets SET is_viewed = true")


def downgrade() -> None:
    # Drop index
    op.drop_index('idx_manual_ssn_tickets_is_viewed', table_name='manual_ssn_tickets')

    # Drop column
    op.drop_column('manual_ssn_tickets', 'is_viewed')
