"""Add contact threads and refactor contact messages

Revision ID: bbccddee5566
Revises: aabbccdd1122
Create Date: 2025-11-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'bbccddee5566'
down_revision = 'aabbccdd1122'
branch_labels = None
depends_on = None


def upgrade():
    # MessageType enum already exists from support threads migration (user, admin)
    # MessageStatus enum already exists (pending, answered, closed)
    # No need to recreate them

    # Create contact_threads table
    op.create_table('contact_threads',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('message_type', postgresql.ENUM('bug_report', 'feature_request', name='contactmessagetype', create_type=False), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'answered', 'closed', name='messagestatus', create_type=False), server_default='pending', nullable=False),
        sa.Column('last_message_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for contact_threads
    op.create_index('idx_contact_threads_user_id', 'contact_threads', ['user_id'], unique=False)
    op.create_index('idx_contact_threads_status', 'contact_threads', ['status'], unique=False)
    op.create_index('idx_contact_threads_last_message_at', 'contact_threads', ['last_message_at'], unique=False)
    op.create_index('idx_contact_threads_user_status', 'contact_threads', ['user_id', 'status'], unique=False)
    op.create_index('idx_contact_threads_message_type', 'contact_threads', ['message_type'], unique=False)

    # Create trigger function for contact_threads.updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_contact_threads_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger for contact_threads
    op.execute("""
        CREATE TRIGGER trigger_update_contact_threads_updated_at
        BEFORE UPDATE ON contact_threads
        FOR EACH ROW
        EXECUTE FUNCTION update_contact_threads_updated_at();
    """)

    # Add new columns to contact_messages
    op.add_column('contact_messages', sa.Column('thread_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('contact_messages', sa.Column('message_type_msg', postgresql.ENUM('user', 'admin', name='messagetype', create_type=False), nullable=True))
    op.add_column('contact_messages', sa.Column('is_read', sa.Boolean(), server_default='false', nullable=False))

    # Data migration: Create threads from existing messages and migrate data
    # Create a temporary column to store original message id in threads
    op.execute("ALTER TABLE contact_threads ADD COLUMN temp_original_message_id UUID")

    # For each existing contact message, create a thread with reference to original message id
    op.execute("""
        INSERT INTO contact_threads (id, user_id, message_type, status, last_message_at, created_at, updated_at, temp_original_message_id)
        SELECT
            gen_random_uuid() as id,
            cm.user_id,
            cm.message_type,
            cm.status,
            COALESCE(cm.responded_at, cm.created_at) as last_message_at,
            cm.created_at,
            cm.updated_at,
            cm.id as temp_original_message_id
        FROM contact_messages cm
    """)

    # Update contact_messages to link to threads using the original message id
    op.execute("""
        UPDATE contact_messages cm
        SET thread_id = ct.id,
            message_type_msg = 'user'
        FROM contact_threads ct
        WHERE ct.temp_original_message_id = cm.id
    """)

    # Create admin response messages from existing admin_response field
    op.execute("""
        INSERT INTO contact_messages (id, thread_id, user_id, message, message_type_msg, is_read, created_at, updated_at)
        SELECT
            gen_random_uuid() as id,
            cm.thread_id,
            cm.responded_by,
            cm.admin_response,
            'admin' as message_type_msg,
            true as is_read,
            cm.responded_at,
            cm.responded_at
        FROM contact_messages cm
        WHERE cm.admin_response IS NOT NULL
            AND cm.responded_by IS NOT NULL
            AND cm.responded_at IS NOT NULL
    """)

    # Update thread last_message_at for threads with admin responses
    op.execute("""
        UPDATE contact_threads ct
        SET last_message_at = (
            SELECT MAX(cm.created_at)
            FROM contact_messages cm
            WHERE cm.thread_id = ct.id
        )
        WHERE EXISTS (
            SELECT 1 FROM contact_messages cm
            WHERE cm.thread_id = ct.id AND cm.message_type_msg = 'admin'
        )
    """)

    # Drop temporary column after migration is complete
    op.execute("ALTER TABLE contact_threads DROP COLUMN temp_original_message_id")

    # Make thread_id and message_type_msg NOT NULL after data migration
    op.alter_column('contact_messages', 'thread_id', nullable=False)
    op.alter_column('contact_messages', 'message_type_msg', nullable=False)

    # Add foreign key constraint for thread_id
    op.create_foreign_key(
        'fk_contact_messages_thread_id',
        'contact_messages', 'contact_threads',
        ['thread_id'], ['id'],
        ondelete='CASCADE'
    )

    # Drop old indexes
    op.drop_index('idx_contact_messages_user_status', table_name='contact_messages')
    op.drop_index('idx_contact_messages_status', table_name='contact_messages')
    op.drop_index('idx_contact_messages_message_type', table_name='contact_messages')

    # Drop old columns
    op.drop_constraint('contact_messages_responded_by_fkey', 'contact_messages', type_='foreignkey')
    op.drop_column('contact_messages', 'admin_response')
    op.drop_column('contact_messages', 'status')
    op.drop_column('contact_messages', 'responded_by')
    op.drop_column('contact_messages', 'responded_at')
    op.drop_column('contact_messages', 'message_type')

    # Rename message_type_msg to message_type
    op.alter_column('contact_messages', 'message_type_msg', new_column_name='message_type')

    # Create new indexes for contact_messages
    op.create_index('idx_contact_messages_thread_id', 'contact_messages', ['thread_id'], unique=False)
    op.create_index('idx_contact_messages_message_type', 'contact_messages', ['message_type'], unique=False)
    op.create_index('idx_contact_messages_is_read', 'contact_messages', ['is_read'], unique=False)
    op.create_index('idx_contact_messages_thread_read', 'contact_messages', ['thread_id', 'is_read'], unique=False)


def downgrade():
    # WARNING: This downgrade will result in data loss (threads cannot be fully restored to old format)

    # Drop new indexes
    op.drop_index('idx_contact_messages_thread_read', table_name='contact_messages')
    op.drop_index('idx_contact_messages_is_read', table_name='contact_messages')
    op.drop_index('idx_contact_messages_message_type', table_name='contact_messages')
    op.drop_index('idx_contact_messages_thread_id', table_name='contact_messages')

    # Rename message_type back to message_type_msg
    op.alter_column('contact_messages', 'message_type', new_column_name='message_type_msg')

    # Add back old columns
    op.add_column('contact_messages', sa.Column('message_type', postgresql.ENUM('bug_report', 'feature_request', name='contactmessagetype', create_type=False), nullable=True))
    op.add_column('contact_messages', sa.Column('admin_response', sa.Text(), nullable=True))
    op.add_column('contact_messages', sa.Column('status', postgresql.ENUM('pending', 'answered', 'closed', name='messagestatus', create_type=False), nullable=True))
    op.add_column('contact_messages', sa.Column('responded_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('contact_messages', sa.Column('responded_at', sa.DateTime(), nullable=True))

    # Attempt to restore data (best effort)
    # Delete admin messages first (they will be lost in downgrade)
    # Use message_type_msg column which holds MessageType enum (user/admin) after rename
    op.execute("DELETE FROM contact_messages WHERE message_type_msg = 'admin'")

    # Restore message_type from thread (for remaining user messages)
    op.execute("""
        UPDATE contact_messages cm
        SET message_type = ct.message_type
        FROM contact_threads ct
        WHERE cm.thread_id = ct.id
    """)

    # Restore status from thread
    op.execute("""
        UPDATE contact_messages cm
        SET status = ct.status
        FROM contact_threads ct
        WHERE cm.thread_id = ct.id
    """)

    # Make status and message_type NOT NULL
    op.alter_column('contact_messages', 'status', nullable=False, server_default='pending')
    op.alter_column('contact_messages', 'message_type', nullable=False)

    # Add back foreign key for responded_by
    op.create_foreign_key(
        'contact_messages_responded_by_fkey',
        'contact_messages', 'users',
        ['responded_by'], ['id'],
        ondelete='SET NULL'
    )

    # Recreate old indexes
    op.create_index('idx_contact_messages_message_type', 'contact_messages', ['message_type'], unique=False)
    op.create_index('idx_contact_messages_status', 'contact_messages', ['status'], unique=False)
    op.create_index('idx_contact_messages_user_status', 'contact_messages', ['user_id', 'status'], unique=False)

    # Drop foreign key for thread_id
    op.drop_constraint('fk_contact_messages_thread_id', 'contact_messages', type_='foreignkey')

    # Drop new columns
    op.drop_column('contact_messages', 'is_read')
    op.drop_column('contact_messages', 'message_type_msg')
    op.drop_column('contact_messages', 'thread_id')

    # Drop trigger for contact_threads
    op.execute("DROP TRIGGER IF EXISTS trigger_update_contact_threads_updated_at ON contact_threads;")

    # Drop trigger function for contact_threads
    op.execute("DROP FUNCTION IF EXISTS update_contact_threads_updated_at();")

    # Drop indexes for contact_threads
    op.drop_index('idx_contact_threads_message_type', table_name='contact_threads')
    op.drop_index('idx_contact_threads_user_status', table_name='contact_threads')
    op.drop_index('idx_contact_threads_last_message_at', table_name='contact_threads')
    op.drop_index('idx_contact_threads_status', table_name='contact_threads')
    op.drop_index('idx_contact_threads_user_id', table_name='contact_threads')

    # Drop contact_threads table
    op.drop_table('contact_threads')
