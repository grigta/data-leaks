"""Add support and contact messages tables

Revision ID: 99aa11bb22cc
Revises: 8f5a9c1d2e3b
Create Date: 2025-11-20 13:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '99aa11bb22cc'
down_revision = '8f5a9c1d2e3b'
branch_labels = None
depends_on = None


def upgrade():
    # Create MessageStatus enum type if it doesn't exist
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'messagestatus') THEN
                CREATE TYPE messagestatus AS ENUM ('pending', 'answered', 'closed');
            END IF;
        END $$;
    """)

    # Create ContactMessageType enum type if it doesn't exist
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'contactmessagetype') THEN
                CREATE TYPE contactmessagetype AS ENUM ('bug_report', 'feature_request');
            END IF;
        END $$;
    """)

    # Create support_messages table
    op.create_table('support_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('admin_response', sa.Text(), nullable=True),
        sa.Column('status', postgresql.ENUM('pending', 'answered', 'closed', name='messagestatus', create_type=False), server_default='pending', nullable=False),
        sa.Column('responded_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('responded_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['responded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for support_messages
    op.create_index('idx_support_messages_user_id', 'support_messages', ['user_id'], unique=False)
    op.create_index('idx_support_messages_status', 'support_messages', ['status'], unique=False)
    op.create_index('idx_support_messages_created_at', 'support_messages', ['created_at'], unique=False)
    op.create_index('idx_support_messages_user_status', 'support_messages', ['user_id', 'status'], unique=False)

    # Create trigger function for support_messages.updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_support_messages_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger for support_messages
    op.execute("""
        CREATE TRIGGER trigger_update_support_messages_updated_at
        BEFORE UPDATE ON support_messages
        FOR EACH ROW
        EXECUTE FUNCTION update_support_messages_updated_at();
    """)

    # Create contact_messages table
    op.create_table('contact_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('message_type', postgresql.ENUM('bug_report', 'feature_request', name='contactmessagetype', create_type=False), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('admin_response', sa.Text(), nullable=True),
        sa.Column('status', postgresql.ENUM('pending', 'answered', 'closed', name='messagestatus', create_type=False), server_default='pending', nullable=False),
        sa.Column('responded_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('responded_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['responded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for contact_messages
    op.create_index('idx_contact_messages_user_id', 'contact_messages', ['user_id'], unique=False)
    op.create_index('idx_contact_messages_status', 'contact_messages', ['status'], unique=False)
    op.create_index('idx_contact_messages_message_type', 'contact_messages', ['message_type'], unique=False)
    op.create_index('idx_contact_messages_created_at', 'contact_messages', ['created_at'], unique=False)
    op.create_index('idx_contact_messages_user_status', 'contact_messages', ['user_id', 'status'], unique=False)

    # Create trigger function for contact_messages.updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_contact_messages_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger for contact_messages
    op.execute("""
        CREATE TRIGGER trigger_update_contact_messages_updated_at
        BEFORE UPDATE ON contact_messages
        FOR EACH ROW
        EXECUTE FUNCTION update_contact_messages_updated_at();
    """)


def downgrade():
    # Drop trigger for contact_messages
    op.execute("DROP TRIGGER IF EXISTS trigger_update_contact_messages_updated_at ON contact_messages;")

    # Drop trigger function for contact_messages
    op.execute("DROP FUNCTION IF EXISTS update_contact_messages_updated_at();")

    # Drop indexes for contact_messages
    op.drop_index('idx_contact_messages_user_status', table_name='contact_messages')
    op.drop_index('idx_contact_messages_created_at', table_name='contact_messages')
    op.drop_index('idx_contact_messages_message_type', table_name='contact_messages')
    op.drop_index('idx_contact_messages_status', table_name='contact_messages')
    op.drop_index('idx_contact_messages_user_id', table_name='contact_messages')

    # Drop contact_messages table
    op.drop_table('contact_messages')

    # Drop trigger for support_messages
    op.execute("DROP TRIGGER IF EXISTS trigger_update_support_messages_updated_at ON support_messages;")

    # Drop trigger function for support_messages
    op.execute("DROP FUNCTION IF EXISTS update_support_messages_updated_at();")

    # Drop indexes for support_messages
    op.drop_index('idx_support_messages_user_status', table_name='support_messages')
    op.drop_index('idx_support_messages_created_at', table_name='support_messages')
    op.drop_index('idx_support_messages_status', table_name='support_messages')
    op.drop_index('idx_support_messages_user_id', table_name='support_messages')

    # Drop support_messages table
    op.drop_table('support_messages')

    # Drop ContactMessageType enum type
    op.execute('DROP TYPE IF EXISTS contactmessagetype')

    # Drop MessageStatus enum type
    op.execute('DROP TYPE IF EXISTS messagestatus')
