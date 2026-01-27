"""add_source_to_searches_and_tickets

Revision ID: eeff667788aa
Revises: ddee445566ff
Create Date: 2025-11-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'eeff667788aa'
down_revision = 'ddee445566ff'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create RequestSource enum type
    request_source_enum = postgresql.ENUM('web', 'telegram_bot', 'other', name='requestsource', create_type=True)
    request_source_enum.create(op.get_bind(), checkfirst=True)

    # Add source column to instant_ssn_searches
    op.add_column('instant_ssn_searches',
                  sa.Column('source',
                           postgresql.ENUM('web', 'telegram_bot', 'other', name='requestsource'),
                           nullable=False,
                           server_default='web'))

    # Add source column to manual_ssn_tickets
    op.add_column('manual_ssn_tickets',
                  sa.Column('source',
                           postgresql.ENUM('web', 'telegram_bot', 'other', name='requestsource'),
                           nullable=False,
                           server_default='web'))

    # Create indexes for better query performance
    op.create_index('idx_instant_ssn_searches_source', 'instant_ssn_searches', ['source'])
    op.create_index('idx_manual_ssn_tickets_source', 'manual_ssn_tickets', ['source'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_manual_ssn_tickets_source', table_name='manual_ssn_tickets')
    op.drop_index('idx_instant_ssn_searches_source', table_name='instant_ssn_searches')

    # Drop columns
    op.drop_column('manual_ssn_tickets', 'source')
    op.drop_column('instant_ssn_searches', 'source')

    # Drop enum type
    request_source_enum = postgresql.ENUM('web', 'telegram_bot', 'other', name='requestsource')
    request_source_enum.drop(op.get_bind(), checkfirst=True)
