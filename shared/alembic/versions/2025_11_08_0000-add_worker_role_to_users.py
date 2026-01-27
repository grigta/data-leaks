"""Add worker_role field to users table

Revision ID: worker_role_001
Revises: news_table_001
Create Date: 2025-11-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'worker_role_001'
down_revision = 'news_table_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add worker_role field to users table
    op.add_column('users',
        sa.Column('worker_role', sa.Boolean(), nullable=False, server_default='false')
    )

    # Create index on worker_role
    op.create_index('idx_users_worker_role', 'users', ['worker_role'])


def downgrade() -> None:
    # Remove index on worker_role
    op.drop_index('idx_users_worker_role', table_name='users')

    # Remove worker_role field from users table
    op.drop_column('users', 'worker_role')
