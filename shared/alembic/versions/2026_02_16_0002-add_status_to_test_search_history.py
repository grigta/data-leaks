"""Add status column to test_search_history

Revision ID: add_status_test_search_001
Revises: add_test_search_history_001
Create Date: 2026-02-16
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_status_test_search_001'
down_revision = 'add_test_search_history_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'test_search_history',
        sa.Column('status', sa.String(20), nullable=False, server_default='done')
    )
    op.create_index('idx_test_search_history_status', 'test_search_history', ['status'])


def downgrade() -> None:
    op.drop_index('idx_test_search_history_status', table_name='test_search_history')
    op.drop_column('test_search_history', 'status')
