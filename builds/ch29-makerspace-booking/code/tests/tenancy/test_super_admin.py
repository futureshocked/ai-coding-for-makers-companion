"""Tests for the super-admin blueprint (Chunk 5).

Covers: host isolation, login/logout, dashboard access control,
tenant approval/rejection/suspend/unsuspend/toggle_listed, audit log.
"""
import pytest
from unittest.mock import patch

from app.models import AuditEvent, Tenant, User
from app.models.tenant import TenantStatus
from app.models.user import UserStatus
from tests.conftest import HostedFlaskClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login_super_admin(client, super_admin_user):
    client.post("/super/login", data={"email": super_admin_user.email, "password": "testpassword1"})


def _make_pending_tenant(db, subdomain="neworg") -> Tenant:
    t = Tenant(name="New Org", subdomain=subdomain, status=TenantStatus.pending, is_listed=True)
    db.session.add(t)
    db.session.commit()
    return t


def _make_pending_admin(db, tenant) -> User:
    from werkzeug.security import generate_password_hash
    u = User(
        tenant_id=tenant.id,
        email="newadmin@example.com",
        password_hash=generate_password_hash("adminpass123"),
        display_name="New Admin",
        is_admin=True,
        status=UserStatus.pending,
        notification_prefs={},
    )
    db.session.add(u)
    db.session.commit()
    return u


# ---------------------------------------------------------------------------
# 1. Host isolation
# ---------------------------------------------------------------------------

class TestHostIsolation:
    def test_super_admin_login_on_tenant_subdomain_is_404(self, app, tenant):
        c = HostedFlaskClient(app, default_host=f"{tenant.subdomain}.lvh.me")
        assert c.get("/super/login").status_code == 404

    def test_super_admin_login_on_apex_is_404(self, apex_client):
        assert apex_client.get("/super/login").status_code == 404

    def test_super_admin_login_on_super_admin_host_is_200(self, super_admin_client):
        assert super_admin_client.get("/super/login").status_code == 200

    def test_tenant_routes_on_super_admin_host_are_404(self, super_admin_client):
        assert super_admin_client.get("/admin/resources").status_code == 404
        assert super_admin_client.get("/auth/login").status_code == 404


# ---------------------------------------------------------------------------
# 2. Login / logout
# ---------------------------------------------------------------------------

class TestSuperAdminLogin:
    def test_valid_credentials_redirect_to_dashboard(self, super_admin_client, super_admin_user):
        resp = super_admin_client.post(
            "/super/login",
            data={"email": super_admin_user.email, "password": "testpassword1"},
        )
        assert resp.status_code == 302
        assert "/super/" in resp.location

    def test_wrong_password_shows_login_form(self, super_admin_client, super_admin_user):
        resp = super_admin_client.post(
            "/super/login",
            data={"email": super_admin_user.email, "password": "wrong"},
        )
        assert resp.status_code == 200

    def test_tenant_user_cannot_log_in_to_super_admin(self, super_admin_client, admin_user):
        resp = super_admin_client.post(
            "/super/login",
            data={"email": admin_user.email, "password": "testpassword1"},
        )
        assert resp.status_code == 200  # re-renders login

    def test_logout_redirects_to_login(self, super_admin_client, super_admin_user):
        _login_super_admin(super_admin_client, super_admin_user)
        resp = super_admin_client.post("/super/logout")
        assert resp.status_code == 302
        assert "/super/login" in resp.location


# ---------------------------------------------------------------------------
# 3. Dashboard access control
# ---------------------------------------------------------------------------

class TestDashboardAccess:
    def test_unauthenticated_redirects_to_login(self, super_admin_client):
        resp = super_admin_client.get("/super/")
        assert resp.status_code == 302
        assert "/super/login" in resp.location

    def test_authenticated_super_admin_sees_dashboard(self, super_admin_client, super_admin_user, tenant):
        _login_super_admin(super_admin_client, super_admin_user)
        resp = super_admin_client.get("/super/")
        assert resp.status_code == 200
        assert tenant.name.encode() in resp.data

    def test_dashboard_shows_pending_tenant(self, super_admin_client, super_admin_user, db):
        pt = _make_pending_tenant(db)
        _login_super_admin(super_admin_client, super_admin_user)
        resp = super_admin_client.get("/super/")
        assert pt.name.encode() in resp.data


# ---------------------------------------------------------------------------
# 4. Tenant approval
# ---------------------------------------------------------------------------

class TestTenantApproval:
    def test_approve_flips_tenant_and_admin_to_active(self, super_admin_client, super_admin_user, db):
        pending_t = _make_pending_tenant(db)
        pending_u = _make_pending_admin(db, pending_t)

        _login_super_admin(super_admin_client, super_admin_user)
        with patch("app.blueprints.super_admin.routes.send_tenant_approval"):
            resp = super_admin_client.post(f"/super/tenants/{pending_t.id}/approve")

        assert resp.status_code == 302

        db.session.refresh(pending_t)
        db.session.refresh(pending_u)
        assert pending_t.status == TenantStatus.active
        assert pending_u.status == UserStatus.active

    def test_approve_creates_audit_event(self, super_admin_client, super_admin_user, db):
        pending_t = _make_pending_tenant(db)
        _login_super_admin(super_admin_client, super_admin_user)
        with patch("app.blueprints.super_admin.routes.send_tenant_approval"):
            super_admin_client.post(f"/super/tenants/{pending_t.id}/approve")

        event = db.session.scalar(
            db.select(AuditEvent).where(AuditEvent.action == "tenant_approved")
        )
        assert event is not None
        assert event.tenant_id is None
        assert event.subject_id == pending_t.id

    def test_approve_already_active_tenant_flashes_error(self, super_admin_client, super_admin_user, tenant):
        _login_super_admin(super_admin_client, super_admin_user)
        resp = super_admin_client.post(
            f"/super/tenants/{tenant.id}/approve", follow_redirects=True
        )
        assert b"not pending" in resp.data.lower()

    def test_approve_nonexistent_tenant_flashes_error(self, super_admin_client, super_admin_user):
        _login_super_admin(super_admin_client, super_admin_user)
        resp = super_admin_client.post("/super/tenants/99999/approve", follow_redirects=True)
        assert b"not found" in resp.data.lower()


# ---------------------------------------------------------------------------
# 5. Tenant rejection
# ---------------------------------------------------------------------------

class TestTenantRejection:
    def test_reject_sets_tenant_suspended(self, super_admin_client, super_admin_user, db):
        pending_t = _make_pending_tenant(db)
        _login_super_admin(super_admin_client, super_admin_user)
        with patch("app.blueprints.super_admin.routes.send_tenant_rejection"):
            resp = super_admin_client.post(f"/super/tenants/{pending_t.id}/reject")

        assert resp.status_code == 302
        db.session.refresh(pending_t)
        assert pending_t.status == TenantStatus.suspended

    def test_reject_creates_audit_event(self, super_admin_client, super_admin_user, db):
        pending_t = _make_pending_tenant(db)
        _login_super_admin(super_admin_client, super_admin_user)
        with patch("app.blueprints.super_admin.routes.send_tenant_rejection"):
            super_admin_client.post(f"/super/tenants/{pending_t.id}/reject")

        event = db.session.scalar(
            db.select(AuditEvent).where(AuditEvent.action == "tenant_rejected")
        )
        assert event is not None
        assert event.tenant_id is None


# ---------------------------------------------------------------------------
# 6. Suspend / unsuspend
# ---------------------------------------------------------------------------

class TestSuspendUnsuspend:
    def test_suspend_active_tenant(self, super_admin_client, super_admin_user, tenant):
        _login_super_admin(super_admin_client, super_admin_user)
        resp = super_admin_client.post(f"/super/tenants/{tenant.id}/suspend")
        assert resp.status_code == 302

        from app.extensions import db as _db
        _db.session.refresh(tenant)
        assert tenant.status == TenantStatus.suspended

    def test_unsuspend_suspended_tenant(self, super_admin_client, super_admin_user, db):
        t = _make_pending_tenant(db, subdomain="suspendme")
        t.status = TenantStatus.suspended
        db.session.commit()

        _login_super_admin(super_admin_client, super_admin_user)
        resp = super_admin_client.post(f"/super/tenants/{t.id}/unsuspend")
        assert resp.status_code == 302

        db.session.refresh(t)
        assert t.status == TenantStatus.active


# ---------------------------------------------------------------------------
# 7. Toggle listed
# ---------------------------------------------------------------------------

class TestToggleListed:
    def test_toggle_listed_flips_flag(self, super_admin_client, super_admin_user, tenant, db):
        assert tenant.is_listed is True
        _login_super_admin(super_admin_client, super_admin_user)

        super_admin_client.post(f"/super/tenants/{tenant.id}/toggle_listed")
        db.session.refresh(tenant)
        assert tenant.is_listed is False

        super_admin_client.post(f"/super/tenants/{tenant.id}/toggle_listed")
        db.session.refresh(tenant)
        assert tenant.is_listed is True


# ---------------------------------------------------------------------------
# 8. Audit log
# ---------------------------------------------------------------------------

class TestAuditLog:
    def test_audit_log_shows_null_tenant_events(self, super_admin_client, super_admin_user, db):
        db.session.add(AuditEvent(
            tenant_id=None,
            actor_user_id=None,
            action="test_platform_event",
            subject_type="tenant",
            payload={},
        ))
        db.session.commit()

        _login_super_admin(super_admin_client, super_admin_user)
        resp = super_admin_client.get("/super/audit-log")
        assert resp.status_code == 200
        assert b"test_platform_event" in resp.data

    def test_audit_log_excludes_tenant_scoped_events(self, super_admin_client, super_admin_user, tenant, db):
        db.session.add(AuditEvent(
            tenant_id=tenant.id,
            actor_user_id=None,
            action="tenant_scoped_event",
            subject_type="resource",
            payload={},
        ))
        db.session.commit()

        _login_super_admin(super_admin_client, super_admin_user)
        resp = super_admin_client.get("/super/audit-log")
        assert b"tenant_scoped_event" not in resp.data

    def test_audit_log_requires_auth(self, super_admin_client):
        resp = super_admin_client.get("/super/audit-log")
        assert resp.status_code == 302
        assert "/super/login" in resp.location
