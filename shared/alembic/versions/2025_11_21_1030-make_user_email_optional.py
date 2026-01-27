"""make_user_email_optional

Revision ID: bbccdd223344
Revises: aec8a3af6743
Create Date: 2025-11-21 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bbccdd223344'
down_revision = 'aec8a3af6743'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop unique constraint on email
    op.drop_constraint('users_email_key', 'users', type_='unique')

    # Make email nullable
    op.alter_column('users', 'email',
                   existing_type=sa.String(length=255),
                   nullable=True)


def downgrade() -> None:
    # Make email non-nullable
    op.alter_column('users', 'email',
                   existing_type=sa.String(length=255),
                   nullable=False)

    # Restore unique constraint on email
    op.create_unique_constraint('users_email_key', 'users', ['email'])
