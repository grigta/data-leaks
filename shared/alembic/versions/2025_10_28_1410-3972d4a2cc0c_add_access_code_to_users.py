"""add access_code to users

Revision ID: 3972d4a2cc0c
Revises: 7cf900d47608
Create Date: 2025-10-28 14:10:57.930000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3972d4a2cc0c'
down_revision = '7cf900d47608'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add access_code column
    op.add_column('users', sa.Column('access_code', sa.String(length=15), nullable=True))
    op.create_index('idx_users_access_code', 'users', ['access_code'], unique=False)
    op.create_unique_constraint('uq_users_access_code', 'users', ['access_code'])


def downgrade() -> None:
    # Remove access_code column
    op.drop_constraint('uq_users_access_code', 'users', type_='unique')
    op.drop_index('idx_users_access_code', table_name='users')
    op.drop_column('users', 'access_code')
