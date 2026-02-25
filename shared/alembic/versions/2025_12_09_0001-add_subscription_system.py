"""Add subscription system tables

Revision ID: add_subscription_001
Revises: 9f689bdfe298
Create Date: 2025-12-09 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_subscription_001'
down_revision = '9f689bdfe298'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create subscription_plans table
    op.create_table('subscription_plans',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('duration_months', sa.Integer(), nullable=False),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('discount_percent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_subscription_plans_name')
    )
    op.create_index('idx_subscription_plans_is_active', 'subscription_plans', ['is_active'], unique=False)
    op.create_index('idx_subscription_plans_duration', 'subscription_plans', ['duration_months'], unique=False)

    # Create subscriptions table
    op.create_table('subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('plan_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('start_date', sa.DateTime(), nullable=False),
        sa.Column('end_date', sa.DateTime(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['plan_id'], ['subscription_plans.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('end_date > start_date', name='check_end_date_after_start')
    )
    op.create_index('idx_subscriptions_user_id', 'subscriptions', ['user_id'], unique=False)
    op.create_index('idx_subscriptions_is_active', 'subscriptions', ['is_active'], unique=False)
    op.create_index('idx_subscriptions_end_date', 'subscriptions', ['end_date'], unique=False)
    op.create_index('idx_subscriptions_user_active', 'subscriptions', ['user_id', 'is_active'], unique=False)

    # Insert default subscription plans
    op.execute("""
        INSERT INTO subscription_plans (id, name, duration_months, price, discount_percent, is_active, created_at)
        VALUES
            (gen_random_uuid(), '1 Month', 1, 50.00, 0, true, now()),
            (gen_random_uuid(), '3 Months', 3, 135.00, 10, true, now()),
            (gen_random_uuid(), '6 Months', 6, 255.00, 15, true, now()),
            (gen_random_uuid(), '12 Months', 12, 480.00, 20, true, now())
    """)


def downgrade() -> None:
    # Drop subscriptions table and indexes
    op.drop_index('idx_subscriptions_user_active', table_name='subscriptions')
    op.drop_index('idx_subscriptions_end_date', table_name='subscriptions')
    op.drop_index('idx_subscriptions_is_active', table_name='subscriptions')
    op.drop_index('idx_subscriptions_user_id', table_name='subscriptions')
    op.drop_table('subscriptions')

    # Drop subscription_plans table and indexes
    op.drop_index('idx_subscription_plans_duration', table_name='subscription_plans')
    op.drop_index('idx_subscription_plans_is_active', table_name='subscription_plans')
    op.drop_table('subscription_plans')
