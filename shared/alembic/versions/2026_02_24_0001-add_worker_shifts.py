"""Add worker shifts table and worker_status field

Revision ID: add_worker_shifts_001
Revises: add_worker_schedule_001
Create Date: 2026-02-24

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_worker_shifts_001'
down_revision = 'add_worker_schedule_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # New table: worker_shifts
    op.create_table(
        'worker_shifts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('worker_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('pause_duration_seconds', sa.Integer(), server_default='0', nullable=False),
        sa.Column('paused_at', sa.DateTime(), nullable=True),
        sa.Column('tickets_completed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('tickets_rejected', sa.Integer(), server_default='0', nullable=False),
    )
    op.create_index('idx_worker_shifts_worker_id', 'worker_shifts', ['worker_id'])
    op.create_index('idx_worker_shifts_started_at', 'worker_shifts', ['started_at'])
    op.create_index('idx_worker_shifts_worker_started', 'worker_shifts', ['worker_id', 'started_at'])
    op.create_index('idx_worker_shifts_ended_at', 'worker_shifts', ['ended_at'])

    # New column: users.worker_status
    op.add_column('users', sa.Column('worker_status', sa.String(20), server_default='idle', nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'worker_status')
    op.drop_index('idx_worker_shifts_ended_at', table_name='worker_shifts')
    op.drop_index('idx_worker_shifts_worker_started', table_name='worker_shifts')
    op.drop_index('idx_worker_shifts_started_at', table_name='worker_shifts')
    op.drop_index('idx_worker_shifts_worker_id', table_name='worker_shifts')
    op.drop_table('worker_shifts')
