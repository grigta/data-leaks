"""Add abuse tracking and ban fields

Revision ID: 8f5a9c1d2e3b
Revises: c7cda8d54464
Create Date: 2025-11-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '8f5a9c1d2e3b'
down_revision = '76eb642c6879'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add ban fields to users table
    op.add_column('users', sa.Column('is_banned', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('ban_reason', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('banned_at', sa.DateTime(), nullable=True))

    # Add instant SSN rules acceptance fields to users table
    op.add_column('users', sa.Column('instant_ssn_rules_accepted', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('instant_ssn_rules_accepted_at', sa.DateTime(), nullable=True))

    # Create index for is_banned
    op.create_index('idx_users_is_banned', 'users', ['is_banned'], unique=False)

    # Create instant_ssn_abuse_tracking table
    op.create_table('instant_ssn_abuse_tracking',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('search_params', sa.JSON(), nullable=False),
        sa.Column('abuse_type', sa.String(length=50), nullable=False),
        sa.Column('is_abuse', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('consecutive_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for instant_ssn_abuse_tracking
    op.create_index('idx_abuse_user_id', 'instant_ssn_abuse_tracking', ['user_id'], unique=False)
    op.create_index('idx_abuse_user_created', 'instant_ssn_abuse_tracking', ['user_id', 'created_at'], unique=False)
    op.create_index('idx_abuse_type', 'instant_ssn_abuse_tracking', ['abuse_type'], unique=False)


def downgrade() -> None:
    # Drop instant_ssn_abuse_tracking table and its indexes
    op.drop_index('idx_abuse_type', table_name='instant_ssn_abuse_tracking')
    op.drop_index('idx_abuse_user_created', table_name='instant_ssn_abuse_tracking')
    op.drop_index('idx_abuse_user_id', table_name='instant_ssn_abuse_tracking')
    op.drop_table('instant_ssn_abuse_tracking')

    # Drop index and columns from users table
    op.drop_index('idx_users_is_banned', table_name='users')
    op.drop_column('users', 'instant_ssn_rules_accepted_at')
    op.drop_column('users', 'instant_ssn_rules_accepted')
    op.drop_column('users', 'banned_at')
    op.drop_column('users', 'ban_reason')
    op.drop_column('users', 'is_banned')
