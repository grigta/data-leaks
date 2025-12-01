"""fix_worker_role_type_to_boolean

Revision ID: 245e9ad29e6f
Revises: 515832942a16
Create Date: 2025-11-08 10:29:17.013628

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '245e9ad29e6f'
down_revision = '515832942a16'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if column is already boolean type - skip if so
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'worker_role'
    """)).fetchone()

    if result and result[0] == 'boolean':
        # Column is already boolean, nothing to do
        return

    # Сначала обновляем все NULL значения на 'false'
    op.execute("UPDATE users SET worker_role = 'false' WHERE worker_role IS NULL OR worker_role = ''")

    # Изменяем тип колонки с character varying на boolean
    # USING clause преобразует существующие строковые значения в boolean
    op.execute("""
        ALTER TABLE users
        ALTER COLUMN worker_role
        TYPE BOOLEAN
        USING CASE
            WHEN worker_role::text IN ('true', 't', '1', 'yes', 'True', 'TRUE') THEN TRUE
            ELSE FALSE
        END
    """)


def downgrade() -> None:
    # Возвращаем обратно к VARCHAR(20) если нужно откатить миграцию
    op.execute("""
        ALTER TABLE users
        ALTER COLUMN worker_role
        TYPE VARCHAR(20)
        USING CASE
            WHEN worker_role = TRUE THEN 'true'
            ELSE 'false'
        END
    """)
