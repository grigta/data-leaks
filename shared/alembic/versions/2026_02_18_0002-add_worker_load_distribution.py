"""Add worker load distribution settings

Revision ID: add_worker_load_dist_001
Revises: add_api_error_logs_001
Create Date: 2026-02-18
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_worker_load_dist_001'
down_revision = 'add_api_error_logs_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add load_percentage to users (nullable, only used for workers)
    op.add_column('users', sa.Column('load_percentage', sa.Integer(), nullable=True))

    # Create app_settings table for global settings like distribution_mode
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(100), primary_key=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # Insert default distribution mode
    op.execute(
        "INSERT INTO app_settings (key, value) VALUES ('worker_distribution_mode', 'even')"
    )


def downgrade() -> None:
    op.drop_table('app_settings')
    op.drop_column('users', 'load_percentage')
