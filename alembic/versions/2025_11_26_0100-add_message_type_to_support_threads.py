"""add_message_type_to_support_threads

Revision ID: ffgg778899aa
Revises: eeff667788aa
Create Date: 2025-11-26 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ffgg778899aa'
down_revision = 'eeff667788aa'
branch_labels = None
depends_on = ('aabbccdd1122',)  # Depends on migration that creates support_threads table


def upgrade() -> None:
    # Create SupportMessageType enum type
    support_message_type_enum = postgresql.ENUM(
        'bug_report',
        'feature_request',
        'general_question',
        name='supportmessagetype',
        create_type=True
    )
    support_message_type_enum.create(op.get_bind(), checkfirst=True)

    # Add message_type column to support_threads
    op.add_column('support_threads',
                  sa.Column('message_type',
                           postgresql.ENUM('bug_report', 'feature_request', 'general_question', name='supportmessagetype'),
                           nullable=False,
                           server_default='general_question'))

    # Create index for better query performance
    op.create_index('idx_support_threads_message_type', 'support_threads', ['message_type'])


def downgrade() -> None:
    # Drop index
    op.drop_index('idx_support_threads_message_type', table_name='support_threads')

    # Drop column
    op.drop_column('support_threads', 'message_type')

    # Drop enum type
    support_message_type_enum = postgresql.ENUM(
        'bug_report',
        'feature_request',
        'general_question',
        name='supportmessagetype'
    )
    support_message_type_enum.drop(op.get_bind(), checkfirst=True)
