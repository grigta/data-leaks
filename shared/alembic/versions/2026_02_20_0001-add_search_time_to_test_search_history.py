"""add search_time to test_search_history

Revision ID: add_search_time_001
Revises: add_worker_invoices_001
Create Date: 2026-02-20

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_search_time_001'
down_revision = 'add_worker_invoices_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('test_search_history', sa.Column('search_time', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('test_search_history', 'search_time')
