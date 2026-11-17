"""tenant_constraints

Revision ID: b2c3d4e5f6a7
Revises: a1f2b3c4d5e6
Create Date: 2026-05-25

"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1f2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    # 1. tenant_id NOT NULL on resources, bookings, notification_log
    #    Rev A backfilled all existing rows, so no NULLs remain.
    op.alter_column('resources', 'tenant_id', existing_type=sa.BigInteger(), nullable=False)
    op.alter_column('bookings', 'tenant_id', existing_type=sa.BigInteger(), nullable=False)
    op.alter_column('notification_log', 'tenant_id', existing_type=sa.BigInteger(), nullable=False)

    # 2. Drop the global UNIQUE on users.email
    op.drop_constraint('users_email_key', 'users', type_='unique')

    # 3. Per-tenant email uniqueness (partial unique index)
    op.execute(
        "CREATE UNIQUE INDEX uq_users_tenant_email "
        "ON users (tenant_id, lower(email)) "
        "WHERE tenant_id IS NOT NULL"
    )

    # 4. Super-admin email uniqueness (partial unique index)
    op.execute(
        "CREATE UNIQUE INDEX uq_users_super_admin_email "
        "ON users (lower(email)) "
        "WHERE tenant_id IS NULL AND is_super_admin = true"
    )

    # 5. Invariant: super-admins have no tenant; tenant users always have one
    op.create_check_constraint(
        'ck_users_super_admin_invariant',
        'users',
        '(tenant_id IS NULL) = is_super_admin',
    )

    # 6. Rebuild bookings active-time index with tenant_id first
    op.drop_index('ix_bookings_active_resource_time', table_name='bookings')
    op.execute(
        "CREATE INDEX ix_bookings_active_resource_time "
        "ON bookings (tenant_id, resource_id, starts_at, ends_at) "
        "WHERE status = 'active'"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_bookings_active_resource_time")
    op.execute(
        "CREATE INDEX ix_bookings_active_resource_time "
        "ON bookings (resource_id, starts_at, ends_at) "
        "WHERE status = 'active'"
    )
    op.drop_constraint('ck_users_super_admin_invariant', 'users', type_='check')
    op.execute("DROP INDEX IF EXISTS uq_users_super_admin_email")
    op.execute("DROP INDEX IF EXISTS uq_users_tenant_email")
    op.create_unique_constraint('users_email_key', 'users', ['email'])
    op.alter_column('notification_log', 'tenant_id', existing_type=sa.BigInteger(), nullable=True)
    op.alter_column('bookings', 'tenant_id', existing_type=sa.BigInteger(), nullable=True)
    op.alter_column('resources', 'tenant_id', existing_type=sa.BigInteger(), nullable=True)
