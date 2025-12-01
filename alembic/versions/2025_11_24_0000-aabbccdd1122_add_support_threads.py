"""Add support threads and refactor support messages

Revision ID: aabbccdd1122
Revises: ffeedd445566
Create Date: 2025-11-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'aabbccdd1122'
down_revision = 'ffeedd445566'
branch_labels = None
depends_on = None


def upgrade():
    # Create MessageStatus enum type if not exists (may already exist from contact_messages)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'messagestatus') THEN
                CREATE TYPE messagestatus AS ENUM ('pending', 'answered', 'closed');
            END IF;
        END $$;
    """)

    # Create MessageType enum type
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'messagetype') THEN
                CREATE TYPE messagetype AS ENUM ('user', 'admin');
            END IF;
        END $$;
    """)

    # Create support_threads table
    op.create_table('support_threads',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('subject', sa.String(200), nullable=True),
        sa.Column('status', postgresql.ENUM('pending', 'answered', 'closed', name='messagestatus', create_type=False), server_default='pending', nullable=False),
        sa.Column('last_message_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for support_threads
    op.create_index('idx_support_threads_user_id', 'support_threads', ['user_id'], unique=False)
    op.create_index('idx_support_threads_status', 'support_threads', ['status'], unique=False)
    op.create_index('idx_support_threads_last_message_at', 'support_threads', ['last_message_at'], unique=False)
    op.create_index('idx_support_threads_user_status', 'support_threads', ['user_id', 'status'], unique=False)

    # Create trigger function for support_threads.updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_support_threads_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger for support_threads
    op.execute("""
        CREATE TRIGGER trigger_update_support_threads_updated_at
        BEFORE UPDATE ON support_threads
        FOR EACH ROW
        EXECUTE FUNCTION update_support_threads_updated_at();
    """)

    # Add new columns to support_messages
    op.add_column('support_messages', sa.Column('thread_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('support_messages', sa.Column('message_type', postgresql.ENUM('user', 'admin', name='messagetype', create_type=False), nullable=True))
    op.add_column('support_messages', sa.Column('is_read', sa.Boolean(), server_default='false', nullable=False))

    # Data migration: Create threads from existing messages and migrate data
    # For each existing support message, create a thread
    op.execute("""
        INSERT INTO support_threads (id, user_id, subject, status, last_message_at, created_at, updated_at)
        SELECT
            gen_random_uuid() as id,
            sm.user_id,
            NULL as subject,
            sm.status,
            COALESCE(sm.responded_at, sm.created_at) as last_message_at,
            sm.created_at,
            sm.updated_at
        FROM support_messages sm
    """)

    # Update support_messages to link to threads (one message per thread for now)
    op.execute("""
        WITH thread_mapping AS (
            SELECT
                sm.id as message_id,
                st.id as thread_id,
                ROW_NUMBER() OVER (PARTITION BY sm.id ORDER BY st.created_at) as rn
            FROM support_messages sm
            JOIN support_threads st ON st.user_id = sm.user_id
                AND st.created_at = sm.created_at
        )
        UPDATE support_messages sm
        SET thread_id = tm.thread_id,
            message_type = 'user'
        FROM thread_mapping tm
        WHERE sm.id = tm.message_id AND tm.rn = 1
    """)

    # Create admin response messages from existing admin_response field
    op.execute("""
        INSERT INTO support_messages (id, thread_id, user_id, message, message_type, is_read, created_at, updated_at)
        SELECT
            gen_random_uuid() as id,
            sm.thread_id,
            sm.responded_by,
            sm.admin_response,
            'admin' as message_type,
            true as is_read,
            sm.responded_at,
            sm.responded_at
        FROM support_messages sm
        WHERE sm.admin_response IS NOT NULL
            AND sm.responded_by IS NOT NULL
            AND sm.responded_at IS NOT NULL
    """)

    # Update thread last_message_at for threads with admin responses
    op.execute("""
        UPDATE support_threads st
        SET last_message_at = (
            SELECT MAX(sm.created_at)
            FROM support_messages sm
            WHERE sm.thread_id = st.id
        )
        WHERE EXISTS (
            SELECT 1 FROM support_messages sm
            WHERE sm.thread_id = st.id AND sm.message_type = 'admin'
        )
    """)

    # Make thread_id and message_type NOT NULL after data migration
    op.alter_column('support_messages', 'thread_id', nullable=False)
    op.alter_column('support_messages', 'message_type', nullable=False)

    # Add foreign key constraint for thread_id
    op.create_foreign_key(
        'fk_support_messages_thread_id',
        'support_messages', 'support_threads',
        ['thread_id'], ['id'],
        ondelete='CASCADE'
    )

    # Drop old indexes
    op.drop_index('idx_support_messages_user_status', table_name='support_messages')
    op.drop_index('idx_support_messages_status', table_name='support_messages')

    # Drop old columns
    op.drop_constraint('support_messages_responded_by_fkey', 'support_messages', type_='foreignkey')
    op.drop_column('support_messages', 'admin_response')
    op.drop_column('support_messages', 'status')
    op.drop_column('support_messages', 'responded_by')
    op.drop_column('support_messages', 'responded_at')

    # Create new indexes for support_messages
    op.create_index('idx_support_messages_thread_id', 'support_messages', ['thread_id'], unique=False)
    op.create_index('idx_support_messages_message_type', 'support_messages', ['message_type'], unique=False)
    op.create_index('idx_support_messages_is_read', 'support_messages', ['is_read'], unique=False)
    op.create_index('idx_support_messages_thread_read', 'support_messages', ['thread_id', 'is_read'], unique=False)


def downgrade():
    # WARNING: This downgrade will result in data loss (threads cannot be fully restored to old format)

    # Drop new indexes
    op.drop_index('idx_support_messages_thread_read', table_name='support_messages')
    op.drop_index('idx_support_messages_is_read', table_name='support_messages')
    op.drop_index('idx_support_messages_message_type', table_name='support_messages')
    op.drop_index('idx_support_messages_thread_id', table_name='support_messages')

    # Add back old columns
    op.add_column('support_messages', sa.Column('admin_response', sa.Text(), nullable=True))
    op.add_column('support_messages', sa.Column('status', postgresql.ENUM('pending', 'answered', 'closed', name='messagestatus', create_type=False), nullable=True))
    op.add_column('support_messages', sa.Column('responded_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('support_messages', sa.Column('responded_at', sa.DateTime(), nullable=True))

    # Attempt to restore data (best effort)
    # Delete admin messages (they will be lost)
    op.execute("DELETE FROM support_messages WHERE message_type = 'admin'")

    # Restore status from thread
    op.execute("""
        UPDATE support_messages sm
        SET status = st.status
        FROM support_threads st
        WHERE sm.thread_id = st.id
    """)

    # Make status NOT NULL
    op.alter_column('support_messages', 'status', nullable=False, server_default='pending')

    # Add back foreign key for responded_by
    op.create_foreign_key(
        'support_messages_responded_by_fkey',
        'support_messages', 'users',
        ['responded_by'], ['id'],
        ondelete='SET NULL'
    )

    # Recreate old indexes
    op.create_index('idx_support_messages_status', 'support_messages', ['status'], unique=False)
    op.create_index('idx_support_messages_user_status', 'support_messages', ['user_id', 'status'], unique=False)

    # Drop foreign key for thread_id
    op.drop_constraint('fk_support_messages_thread_id', 'support_messages', type_='foreignkey')

    # Drop new columns
    op.drop_column('support_messages', 'is_read')
    op.drop_column('support_messages', 'message_type')
    op.drop_column('support_messages', 'thread_id')

    # Drop trigger for support_threads
    op.execute("DROP TRIGGER IF EXISTS trigger_update_support_threads_updated_at ON support_threads;")

    # Drop trigger function for support_threads
    op.execute("DROP FUNCTION IF EXISTS update_support_threads_updated_at();")

    # Drop indexes for support_threads
    op.drop_index('idx_support_threads_user_status', table_name='support_threads')
    op.drop_index('idx_support_threads_last_message_at', table_name='support_threads')
    op.drop_index('idx_support_threads_status', table_name='support_threads')
    op.drop_index('idx_support_threads_user_id', table_name='support_threads')

    # Drop support_threads table
    op.drop_table('support_threads')

    # Drop MessageType enum type
    op.execute('DROP TYPE IF EXISTS messagetype')
