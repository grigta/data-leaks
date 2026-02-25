"""Add search_mode column to users table

Revision ID: add_search_mode_users_001
Revises: add_searchbug_cache_001
Create Date: 2026-02-13
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_search_mode_users_001'
down_revision = 'add_searchbug_cache_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('search_mode', sa.String(20), nullable=True, server_default='auto'))


def downgrade() -> None:
    op.drop_column('users', 'search_mode')
