"""Add manual SSN tickets and worker registration tables

Revision ID: manual_ssn_worker_001
Revises: worker_role_001
Create Date: 2025-11-08 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'manual_ssn_worker_001'
down_revision = 'worker_role_001'
branch_labels = None
depends_on = None


def upgrade():
    # Create TicketStatus enum type if it doesn't exist
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'ticketstatus') THEN
                CREATE TYPE ticketstatus AS ENUM ('pending', 'processing', 'completed', 'rejected');
            END IF;
        END $$;
    """)

    # Create RegistrationStatus enum type if it doesn't exist
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'registrationstatus') THEN
                CREATE TYPE registrationstatus AS ENUM ('pending', 'approved', 'rejected');
            END IF;
        END $$;
    """)

    # Create manual_ssn_tickets table if it doesn't exist
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    if 'manual_ssn_tickets' not in inspector.get_table_names():
        op.create_table('manual_ssn_tickets',
            sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
            sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('firstname', sa.String(length=100), nullable=False),
            sa.Column('lastname', sa.String(length=100), nullable=False),
            sa.Column('address', sa.Text(), nullable=False),
            sa.Column('status', postgresql.ENUM('pending', 'processing', 'completed', 'rejected', name='ticketstatus', create_type=False), server_default='pending', nullable=False),
            sa.Column('worker_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('response_data', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['worker_id'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )

        # Create indexes for manual_ssn_tickets
        op.create_index('idx_manual_ssn_tickets_user_id', 'manual_ssn_tickets', ['user_id'], unique=False)
        op.create_index('idx_manual_ssn_tickets_worker_id', 'manual_ssn_tickets', ['worker_id'], unique=False)
        op.create_index('idx_manual_ssn_tickets_status', 'manual_ssn_tickets', ['status'], unique=False)
        op.create_index('idx_manual_ssn_tickets_created_at', 'manual_ssn_tickets', ['created_at'], unique=False)
        op.create_index('idx_manual_ssn_tickets_worker_status', 'manual_ssn_tickets', ['worker_id', 'status'], unique=False)

        # Create trigger function for manual_ssn_tickets.updated_at
        op.execute("""
            CREATE OR REPLACE FUNCTION update_manual_ssn_tickets_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = now();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)

        # Create trigger for manual_ssn_tickets
        op.execute("""
            CREATE TRIGGER trigger_update_manual_ssn_tickets_updated_at
            BEFORE UPDATE ON manual_ssn_tickets
            FOR EACH ROW
            EXECUTE FUNCTION update_manual_ssn_tickets_updated_at();
        """)

    # Create worker_registration_requests table if it doesn't exist
    if 'worker_registration_requests' not in inspector.get_table_names():
        op.create_table('worker_registration_requests',
            sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
            sa.Column('username', sa.String(length=50), nullable=False),
            sa.Column('email', sa.String(length=255), nullable=False),
            sa.Column('hashed_password', sa.String(length=255), nullable=False),
            sa.Column('access_code', sa.String(length=15), nullable=False),
            sa.Column('status', postgresql.ENUM('pending', 'approved', 'rejected', name='registrationstatus', create_type=False), server_default='pending', nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('access_code')
        )

        # Create indexes for worker_registration_requests
        op.create_index('idx_worker_registration_requests_status', 'worker_registration_requests', ['status'], unique=False)
        op.create_index('idx_worker_registration_requests_access_code', 'worker_registration_requests', ['access_code'], unique=False)
        op.create_index('idx_worker_registration_requests_created_at', 'worker_registration_requests', ['created_at'], unique=False)


def downgrade():
    # Drop indexes for worker_registration_requests
    op.drop_index('idx_worker_registration_requests_created_at', table_name='worker_registration_requests')
    op.drop_index('idx_worker_registration_requests_access_code', table_name='worker_registration_requests')
    op.drop_index('idx_worker_registration_requests_status', table_name='worker_registration_requests')

    # Drop worker_registration_requests table
    op.drop_table('worker_registration_requests')

    # Drop trigger for manual_ssn_tickets
    op.execute("DROP TRIGGER IF EXISTS trigger_update_manual_ssn_tickets_updated_at ON manual_ssn_tickets;")

    # Drop trigger function for manual_ssn_tickets
    op.execute("DROP FUNCTION IF EXISTS update_manual_ssn_tickets_updated_at();")

    # Drop indexes for manual_ssn_tickets
    op.drop_index('idx_manual_ssn_tickets_worker_status', table_name='manual_ssn_tickets')
    op.drop_index('idx_manual_ssn_tickets_created_at', table_name='manual_ssn_tickets')
    op.drop_index('idx_manual_ssn_tickets_status', table_name='manual_ssn_tickets')
    op.drop_index('idx_manual_ssn_tickets_worker_id', table_name='manual_ssn_tickets')
    op.drop_index('idx_manual_ssn_tickets_user_id', table_name='manual_ssn_tickets')

    # Drop manual_ssn_tickets table
    op.drop_table('manual_ssn_tickets')

    # Drop RegistrationStatus enum type
    op.execute('DROP TYPE registrationstatus')

    # Drop TicketStatus enum type
    op.execute('DROP TYPE ticketstatus')
