"""Add searchbug_cache table for caching SearchBug API responses

Revision ID: add_searchbug_cache_001
Revises: add_missing_indexes_001
Create Date: 2026-02-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_searchbug_cache_001'
down_revision = 'add_missing_indexes_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'searchbug_cache',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('cache_key', sa.String(500), nullable=False, unique=True),
        sa.Column('search_params', postgresql.JSON(), nullable=False),
        sa.Column('response_data', postgresql.JSON(), nullable=False),
        sa.Column('data_found', sa.Boolean(), nullable=False, default=False),
        sa.Column('hit_count', sa.Integer(), nullable=False, default=0),
        sa.Column('last_hit_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
    )

    # Indexes
    op.create_index('idx_searchbug_cache_key', 'searchbug_cache', ['cache_key'], unique=True)
    op.create_index('idx_searchbug_cache_expires', 'searchbug_cache', ['expires_at'])
    op.create_index('idx_searchbug_cache_data_found', 'searchbug_cache', ['data_found'])
    op.create_index('idx_searchbug_cache_created', 'searchbug_cache', ['created_at'])


def downgrade() -> None:
    op.drop_index('idx_searchbug_cache_created', table_name='searchbug_cache')
    op.drop_index('idx_searchbug_cache_data_found', table_name='searchbug_cache')
    op.drop_index('idx_searchbug_cache_expires', table_name='searchbug_cache')
    op.drop_index('idx_searchbug_cache_key', table_name='searchbug_cache')
    op.drop_table('searchbug_cache')
