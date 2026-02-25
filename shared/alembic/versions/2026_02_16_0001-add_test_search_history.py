"""Add test_search_history table

Revision ID: add_test_search_history_001
Revises: add_search_mode_users_001
Create Date: 2026-02-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_test_search_history_001'
down_revision = 'add_search_mode_users_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'test_search_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('input_fullname', sa.String(200), nullable=False),
        sa.Column('input_address', sa.String(500), nullable=False),
        sa.Column('result_fullname', sa.String(200), nullable=False),
        sa.Column('result_address', sa.String(500), nullable=False),
        sa.Column('ssn', sa.String(11), nullable=False),
        sa.Column('dob', sa.String(20), nullable=True),
        sa.Column('found', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_test_search_history_user_id', 'test_search_history', ['user_id'])
    op.create_index('idx_test_search_history_created_at', 'test_search_history', ['created_at'])
    op.create_index('idx_test_search_history_user_created', 'test_search_history', ['user_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('idx_test_search_history_user_created', table_name='test_search_history')
    op.drop_index('idx_test_search_history_created_at', table_name='test_search_history')
    op.drop_index('idx_test_search_history_user_id', table_name='test_search_history')
    op.drop_table('test_search_history')
