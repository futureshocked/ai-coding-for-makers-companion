from app.extensions import db
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus


def activate_tenant(tenant: Tenant) -> None:
    """Flip a pending tenant and its first admin user to active.

    # TODO(v2.1+): Cloudflare per-subdomain provisioning hook slots in here.
    """
    if tenant.status != TenantStatus.pending:
        raise ValueError(f"Cannot activate tenant in status {tenant.status}")
    tenant.status = TenantStatus.active
    first_admin = db.session.scalar(
        db.select(User).where(
            User.tenant_id == tenant.id,
            User.is_admin == True,  # noqa: E712
        )
    )
    if first_admin:
        first_admin.status = UserStatus.active
    db.session.commit()
