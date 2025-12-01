"""Add maintenance_modes and custom_pricing tables

Revision ID: aabbcc112233
Revises: 99aa11bb22cc
Create Date: 2025-11-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'aabbcc112233'
down_revision = 'payment_provider_idx_001'
branch_labels = None
depends_on = None


def upgrade():
    # Create maintenance_modes table
    op.create_table('maintenance_modes',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('service_name', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('service_name', name='uq_maintenance_modes_service_name')
    )

    # Create indexes for maintenance_modes
    op.create_index('idx_maintenance_modes_service_name', 'maintenance_modes', ['service_name'], unique=True)
    op.create_index('idx_maintenance_modes_is_active', 'maintenance_modes', ['is_active'], unique=False)

    # Create trigger function for maintenance_modes.updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_maintenance_modes_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger for maintenance_modes
    op.execute("""
        CREATE TRIGGER trigger_update_maintenance_modes_updated_at
        BEFORE UPDATE ON maintenance_modes
        FOR EACH ROW
        EXECUTE FUNCTION update_maintenance_modes_updated_at();
    """)

    # Create custom_pricing table
    op.create_table('custom_pricing',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('access_code', sa.String(length=15), nullable=False),
        sa.Column('service_name', sa.String(length=50), nullable=False),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('price >= 0', name='check_custom_pricing_price_non_negative'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('access_code', 'service_name', name='uq_custom_pricing_access_code_service')
    )

    # Create indexes for custom_pricing
    op.create_index('idx_custom_pricing_access_code', 'custom_pricing', ['access_code'], unique=False)
    op.create_index('idx_custom_pricing_service_name', 'custom_pricing', ['service_name'], unique=False)
    op.create_index('idx_custom_pricing_is_active', 'custom_pricing', ['is_active'], unique=False)

    # Create trigger function for custom_pricing.updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_custom_pricing_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger for custom_pricing
    op.execute("""
        CREATE TRIGGER trigger_update_custom_pricing_updated_at
        BEFORE UPDATE ON custom_pricing
        FOR EACH ROW
        EXECUTE FUNCTION update_custom_pricing_updated_at();
    """)


def downgrade():
    # Drop trigger for custom_pricing
    op.execute("DROP TRIGGER IF EXISTS trigger_update_custom_pricing_updated_at ON custom_pricing;")

    # Drop trigger function for custom_pricing
    op.execute("DROP FUNCTION IF EXISTS update_custom_pricing_updated_at();")

    # Drop indexes for custom_pricing
    op.drop_index('idx_custom_pricing_is_active', table_name='custom_pricing')
    op.drop_index('idx_custom_pricing_service_name', table_name='custom_pricing')
    op.drop_index('idx_custom_pricing_access_code', table_name='custom_pricing')

    # Drop custom_pricing table
    op.drop_table('custom_pricing')

    # Drop trigger for maintenance_modes
    op.execute("DROP TRIGGER IF EXISTS trigger_update_maintenance_modes_updated_at ON maintenance_modes;")

    # Drop trigger function for maintenance_modes
    op.execute("DROP FUNCTION IF EXISTS update_maintenance_modes_updated_at();")

    # Drop indexes for maintenance_modes
    op.drop_index('idx_maintenance_modes_is_active', table_name='maintenance_modes')
    op.drop_index('idx_maintenance_modes_service_name', table_name='maintenance_modes')

    # Drop maintenance_modes table
    op.drop_table('maintenance_modes')
