"""alter_worker_id_fk_to_set_null

Revision ID: 515832942a16
Revises: manual_ssn_worker_001
Create Date: 2025-11-08 06:56:22.235087

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '515832942a16'
down_revision = 'manual_ssn_worker_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the existing foreign key constraint on worker_id
    op.drop_constraint('manual_ssn_tickets_worker_id_fkey', 'manual_ssn_tickets', type_='foreignkey')

    # Recreate the foreign key constraint with ondelete='SET NULL'
    op.create_foreign_key(
        'manual_ssn_tickets_worker_id_fkey',
        'manual_ssn_tickets',
        'users',
        ['worker_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    # Drop the foreign key constraint with SET NULL
    op.drop_constraint('manual_ssn_tickets_worker_id_fkey', 'manual_ssn_tickets', type_='foreignkey')

    # Recreate the original foreign key constraint with ondelete='CASCADE'
    op.create_foreign_key(
        'manual_ssn_tickets_worker_id_fkey',
        'manual_ssn_tickets',
        'users',
        ['worker_id'],
        ['id'],
        ondelete='CASCADE'
    )
