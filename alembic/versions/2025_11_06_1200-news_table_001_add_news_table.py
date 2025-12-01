"""Add news table for admin posts

Revision ID: news_table_001
Revises: cart_enrichment_001
Create Date: 2025-11-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'news_table_001'
down_revision = 'cart_enrichment_001'
branch_labels = None
depends_on = None


def upgrade():
    # Create news table
    op.create_table('news',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('idx_news_author_id', 'news', ['author_id'], unique=False)
    op.create_index('idx_news_created_at', 'news', ['created_at'], unique=False)
    op.create_index('idx_news_author_created', 'news', ['author_id', 'created_at'], unique=False)

    # Create function for auto-updating updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_news_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger for auto-updating updated_at
    op.execute("""
        CREATE TRIGGER trigger_update_news_updated_at
        BEFORE UPDATE ON news
        FOR EACH ROW
        EXECUTE FUNCTION update_news_updated_at();
    """)


def downgrade():
    # Drop trigger
    op.execute("DROP TRIGGER IF EXISTS trigger_update_news_updated_at ON news;")

    # Drop function
    op.execute("DROP FUNCTION IF EXISTS update_news_updated_at();")

    # Drop indexes
    op.drop_index('idx_news_author_created', table_name='news')
    op.drop_index('idx_news_created_at', table_name='news')
    op.drop_index('idx_news_author_id', table_name='news')

    # Drop table
    op.drop_table('news')
