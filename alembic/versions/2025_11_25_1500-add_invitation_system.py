"""add_invitation_system

Revision ID: ddee445566ff
Revises: ccddee334455
Create Date: 2025-11-25 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import secrets

# revision identifiers, used by Alembic.
revision = 'ddee445566ff'
down_revision = 'ccddee334455'
branch_labels = None
depends_on = None


def generate_invitation_code() -> str:
    """
    Generate a random 15-character alphanumeric invitation code.
    Similar to access_code generation but using alphanumeric characters.
    """
    # Use alphanumeric characters (uppercase letters and digits)
    chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    return ''.join(secrets.choice(chars) for _ in range(15))


def upgrade() -> None:
    # Add invited_by column
    op.add_column('users', sa.Column('invited_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_users_invited_by', 'users', 'users', ['invited_by'], ['id'], ondelete='SET NULL')

    # Add invitation_code column
    op.add_column('users', sa.Column('invitation_code', sa.String(15), nullable=True))

    # Add invitation_bonus_received column
    op.add_column('users', sa.Column('invitation_bonus_received', sa.Boolean(), nullable=False, server_default='false'))

    # Create indexes
    op.create_index('idx_users_invited_by', 'users', ['invited_by'])
    op.create_index('idx_users_invitation_code', 'users', ['invitation_code'])

    # Create unique constraint on invitation_code
    op.create_unique_constraint('uq_users_invitation_code', 'users', ['invitation_code'])

    # Data migration: Generate unique invitation codes for all existing users
    # Use batch approach with pre-generated codes to avoid manual commits
    connection = op.get_bind()
    result = connection.execute(sa.text("SELECT id FROM users WHERE invitation_code IS NULL"))
    users = result.fetchall()

    # Generate all codes first, ensuring uniqueness
    codes_to_assign = {}
    used_codes = set()

    # Get existing codes to avoid collisions
    existing_result = connection.execute(sa.text("SELECT invitation_code FROM users WHERE invitation_code IS NOT NULL"))
    for row in existing_result:
        if row[0]:
            used_codes.add(row[0])

    for user_row in users:
        user_id = user_row[0]
        max_attempts = 100  # Increased for large user bases

        for attempt in range(max_attempts):
            invitation_code = generate_invitation_code()
            if invitation_code not in used_codes:
                used_codes.add(invitation_code)
                codes_to_assign[user_id] = invitation_code
                break
        else:
            raise Exception(f"Failed to generate unique invitation code for user {user_id} after {max_attempts} attempts")

    # Batch update all users with generated codes
    # Use conditional UPDATE to handle race conditions
    from sqlalchemy.exc import IntegrityError

    for user_id, invitation_code in codes_to_assign.items():
        try:
            result = connection.execute(
                sa.text("UPDATE users SET invitation_code = :code WHERE id = :user_id AND invitation_code IS NULL"),
                {"code": invitation_code, "user_id": user_id}
            )
            if result.rowcount == 0:
                # Row was already updated, try to generate new code
                for retry in range(10):
                    new_code = generate_invitation_code()
                    if new_code not in used_codes:
                        try:
                            result = connection.execute(
                                sa.text("UPDATE users SET invitation_code = :code WHERE id = :user_id AND invitation_code IS NULL"),
                                {"code": new_code, "user_id": user_id}
                            )
                            if result.rowcount > 0:
                                used_codes.add(new_code)
                                break
                        except IntegrityError:
                            continue
        except IntegrityError:
            # Unique constraint violation - code collision, retry
            for retry in range(10):
                new_code = generate_invitation_code()
                if new_code not in used_codes:
                    try:
                        result = connection.execute(
                            sa.text("UPDATE users SET invitation_code = :code WHERE id = :user_id AND invitation_code IS NULL"),
                            {"code": new_code, "user_id": user_id}
                        )
                        if result.rowcount > 0:
                            used_codes.add(new_code)
                            break
                    except IntegrityError:
                        continue
            else:
                raise Exception(f"Failed to assign invitation code to user {user_id} after retries")


def downgrade() -> None:
    # Drop unique constraint
    op.drop_constraint('uq_users_invitation_code', 'users', type_='unique')

    # Drop indexes
    op.drop_index('idx_users_invitation_code', table_name='users')
    op.drop_index('idx_users_invited_by', table_name='users')

    # Drop foreign key
    op.drop_constraint('fk_users_invited_by', 'users', type_='foreignkey')

    # Drop columns
    op.drop_column('users', 'invitation_bonus_received')
    op.drop_column('users', 'invitation_code')
    op.drop_column('users', 'invited_by')
