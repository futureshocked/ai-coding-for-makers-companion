"""add tenants table, tenant_id columns, is_super_admin, and backfill default tenant

Revision ID: a1f2b3c4d5e6
Revises: 30dd2b6b0a27
Create Date: 2026-05-25 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1f2b3c4d5e6'
down_revision = '30dd2b6b0a27'
branch_labels = None
depends_on = None


TENANT_STATUS = sa.Enum('pending', 'active', 'suspended', name='tenant_status')


def upgrade():
    bind = op.get_bind()

    # tenant_status enum is created implicitly by the tenants.status column below.

    op.create_table(
        'tenants',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('subdomain', sa.Text(), nullable=False),
        sa.Column('status', TENANT_STATUS, nullable=False, server_default='pending'),
        sa.Column('is_listed', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'uq_tenants_subdomain_lower',
        'tenants',
        [sa.text('lower(subdomain)')],
        unique=True,
    )

    op.add_column('users', sa.Column('tenant_id', sa.BigInteger(), nullable=True))
    op.add_column('users', sa.Column('is_super_admin', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.create_foreign_key('fk_users_tenant_id', 'users', 'tenants', ['tenant_id'], ['id'])
    op.create_index('ix_users_tenant_id', 'users', ['tenant_id'])

    op.add_column('resources', sa.Column('tenant_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_resources_tenant_id', 'resources', 'tenants', ['tenant_id'], ['id'])
    op.create_index('ix_resources_tenant_id', 'resources', ['tenant_id'])

    op.add_column('bookings', sa.Column('tenant_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_bookings_tenant_id', 'bookings', 'tenants', ['tenant_id'], ['id'])
    op.create_index('ix_bookings_tenant_id', 'bookings', ['tenant_id'])

    op.add_column('notification_log', sa.Column('tenant_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_notification_log_tenant_id', 'notification_log', 'tenants', ['tenant_id'], ['id'])
    op.create_index('ix_notification_log_tenant_id', 'notification_log', ['tenant_id'])

    op.add_column('audit_events', sa.Column('tenant_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_audit_events_tenant_id', 'audit_events', 'tenants', ['tenant_id'], ['id'])
    op.create_index('ix_audit_events_tenant_id', 'audit_events', ['tenant_id'])

    # Backfill: create a Default tenant and assign existing data to it.
    # Only runs if there is existing data to backfill (i.e. not a fresh DB).
    has_data = bind.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM users) "
        "OR EXISTS (SELECT 1 FROM resources) "
        "OR EXISTS (SELECT 1 FROM bookings) "
        "OR EXISTS (SELECT 1 FROM notification_log) "
        "OR EXISTS (SELECT 1 FROM audit_events)"
    )).scalar()

    if has_data:
        default_id = bind.execute(sa.text(
            "INSERT INTO tenants (name, subdomain, status, is_listed) "
            "VALUES ('Default', 'default', 'active', true) RETURNING id"
        )).scalar()

        # Tenant users (existing users are all real tenant members, not super-admins).
        bind.execute(sa.text("UPDATE users SET tenant_id = :tid WHERE tenant_id IS NULL"),
                     {"tid": default_id})
        bind.execute(sa.text("UPDATE resources SET tenant_id = :tid WHERE tenant_id IS NULL"),
                     {"tid": default_id})
        bind.execute(sa.text("UPDATE bookings SET tenant_id = :tid WHERE tenant_id IS NULL"),
                     {"tid": default_id})
        bind.execute(sa.text("UPDATE notification_log SET tenant_id = :tid WHERE tenant_id IS NULL"),
                     {"tid": default_id})
        bind.execute(sa.text("UPDATE audit_events SET tenant_id = :tid WHERE tenant_id IS NULL"),
                     {"tid": default_id})


def downgrade():
    op.drop_index('ix_audit_events_tenant_id', table_name='audit_events')
    op.drop_constraint('fk_audit_events_tenant_id', 'audit_events', type_='foreignkey')
    op.drop_column('audit_events', 'tenant_id')

    op.drop_index('ix_notification_log_tenant_id', table_name='notification_log')
    op.drop_constraint('fk_notification_log_tenant_id', 'notification_log', type_='foreignkey')
    op.drop_column('notification_log', 'tenant_id')

    op.drop_index('ix_bookings_tenant_id', table_name='bookings')
    op.drop_constraint('fk_bookings_tenant_id', 'bookings', type_='foreignkey')
    op.drop_column('bookings', 'tenant_id')

    op.drop_index('ix_resources_tenant_id', table_name='resources')
    op.drop_constraint('fk_resources_tenant_id', 'resources', type_='foreignkey')
    op.drop_column('resources', 'tenant_id')

    op.drop_index('ix_users_tenant_id', table_name='users')
    op.drop_constraint('fk_users_tenant_id', 'users', type_='foreignkey')
    op.drop_column('users', 'is_super_admin')
    op.drop_column('users', 'tenant_id')

    op.drop_index('uq_tenants_subdomain_lower', table_name='tenants')
    op.drop_table('tenants')

    TENANT_STATUS.drop(op.get_bind(), checkfirst=True)
