"""Add test polygon tables

Revision ID: add_test_polygon_001
Revises: add_worker_shifts_001
Create Date: 2026-02-24

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_test_polygon_001'
down_revision = 'add_worker_shifts_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # test_polygons
    op.create_table(
        'test_polygons',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_test_polygons_created_by', 'test_polygons', ['created_by'])
    op.create_index('idx_test_polygons_created_at', 'test_polygons', ['created_at'])

    # test_polygon_records
    op.create_table(
        'test_polygon_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('test_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('test_polygons.id', ondelete='CASCADE'), nullable=False),
        sa.Column('fullname', sa.String(200), nullable=False),
        sa.Column('address', sa.String(500), nullable=False),
        sa.Column('expected_ssn', sa.String(11), nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
    )
    op.create_index('idx_test_polygon_records_test_id', 'test_polygon_records', ['test_id'])

    # test_polygon_runs
    op.create_table(
        'test_polygon_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('test_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('test_polygons.id', ondelete='CASCADE'), nullable=False),
        sa.Column('flow_config', postgresql.JSON(), nullable=True),
        sa.Column('status', sa.String(20), server_default='pending', nullable=False),
        sa.Column('total_records', sa.Integer(), server_default='0', nullable=False),
        sa.Column('processed_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('matched_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('not_found_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('wrong_ssn_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('error_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_test_polygon_runs_test_id', 'test_polygon_runs', ['test_id'])
    op.create_index('idx_test_polygon_runs_status', 'test_polygon_runs', ['status'])
    op.create_index('idx_test_polygon_runs_created_at', 'test_polygon_runs', ['created_at'])

    # test_polygon_results
    op.create_table(
        'test_polygon_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('run_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('test_polygon_runs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('record_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('test_polygon_records.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('found_ssn', sa.String(11), nullable=True),
        sa.Column('best_method', sa.String(50), nullable=True),
        sa.Column('matched_keys_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('total_candidates', sa.Integer(), server_default='0', nullable=False),
        sa.Column('debug_data', postgresql.JSON(), nullable=True),
        sa.Column('search_time', sa.Float(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_test_polygon_results_run_id', 'test_polygon_results', ['run_id'])
    op.create_index('idx_test_polygon_results_record_id', 'test_polygon_results', ['record_id'])
    op.create_index('idx_test_polygon_results_status', 'test_polygon_results', ['status'])


def downgrade() -> None:
    op.drop_table('test_polygon_results')
    op.drop_table('test_polygon_runs')
    op.drop_table('test_polygon_records')
    op.drop_table('test_polygons')
