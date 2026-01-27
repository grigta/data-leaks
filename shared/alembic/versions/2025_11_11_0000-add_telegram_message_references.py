"""add_telegram_message_references

Revision ID: e9f8d7c6b5a4
Revises: 42e638ec172f
Create Date: 2025-11-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'e9f8d7c6b5a4'
down_revision = '42e638ec172f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create telegram_message_references table."""
    op.create_table('telegram_message_references',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ticket_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['manual_ssn_tickets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ticket_id', name='uq_telegram_message_references_ticket_id')
    )
    op.create_index('idx_telegram_message_references_ticket_id', 'telegram_message_references', ['ticket_id'], unique=False)
    op.create_index('idx_telegram_message_references_created_at', 'telegram_message_references', ['created_at'], unique=False)


def downgrade() -> None:
    """Drop telegram_message_references table."""
    op.drop_index('idx_telegram_message_references_created_at', table_name='telegram_message_references')
    op.drop_index('idx_telegram_message_references_ticket_id', table_name='telegram_message_references')
    op.drop_table('telegram_message_references')
