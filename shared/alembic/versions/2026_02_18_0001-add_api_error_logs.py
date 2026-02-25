"""Add api_error_logs table

Revision ID: add_api_error_logs_001
Revises: add_status_test_search_001
Create Date: 2026-02-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_api_error_logs_001'
down_revision = 'add_status_test_search_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'api_error_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('api_name', sa.String(50), nullable=False),
        sa.Column('method', sa.String(100), nullable=False),
        sa.Column('error_type', sa.String(100), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('request_params', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_api_error_logs_api_name', 'api_error_logs', ['api_name'])
    op.create_index('idx_api_error_logs_created_at', 'api_error_logs', ['created_at'])
    op.create_index('idx_api_error_logs_api_created', 'api_error_logs', ['api_name', 'created_at'])


def downgrade() -> None:
    op.drop_index('idx_api_error_logs_api_created', table_name='api_error_logs')
    op.drop_index('idx_api_error_logs_created_at', table_name='api_error_logs')
    op.drop_index('idx_api_error_logs_api_name', table_name='api_error_logs')
    op.drop_table('api_error_logs')
