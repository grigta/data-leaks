"""Add worker schedule and pause fields

Revision ID: add_worker_schedule_001
Revises: add_search_time_001
Create Date: 2026-02-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_worker_schedule_001'
down_revision = 'add_search_time_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('worker_paused', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('users', sa.Column('worker_schedule', sa.JSON(), nullable=True))
    op.add_column('users', sa.Column('worker_timezone', sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'worker_timezone')
    op.drop_column('users', 'worker_schedule')
    op.drop_column('users', 'worker_paused')
