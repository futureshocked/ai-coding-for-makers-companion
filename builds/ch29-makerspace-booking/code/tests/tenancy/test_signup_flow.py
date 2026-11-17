"""Tests for public blueprint: landing page, org signup, apex-hosted password reset."""
import pytest
from unittest.mock import patch
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import generate_password_hash

from app.models import Tenant, User, AuditEvent
from app.models.tenant import TenantStatus
from app.models.user import UserStatus
from tests.conftest import HostedFlaskClient


def _make_serializer(app):
    return URLSafeTimedSerializer(app.secret_key, salt="password-reset")


def _valid_org_form(**overrides):
    data = {
        "org_name": "New Makerspace",
        "subdomain": "newms",
        "admin_email": "admin@newms.com",
        "admin_display_name": "Admin User",
        "admin_password": "strongpass123",
        "admin_password2": "strongpass123",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------

class TestLandingPage:
    def test_landing_returns_200(self, apex_client):
        assert apex_client.get("/").status_code == 200

    def test_landing_shows_active_listed_tenant(self, apex_client, tenant):
        resp = apex_client.get("/")
        assert tenant.name.encode() in resp.data

    def test_landing_hides_pending_tenant(self, apex_client, db):
        t = Tenant(name="Pending Corp", subdomain="pendingco", status=TenantStatus.pending, is_listed=True)
        db.session.add(t)
        db.session.commit()
        resp = apex_client.get("/")
        assert b"Pending Corp" not in resp.data

    def test_landing_hides_unlisted_tenant(self, apex_client, db):
        t = Tenant(name="Hidden Corp", subdomain="hiddenco", status=TenantStatus.active, is_listed=False)
        db.session.add(t)
        db.session.commit()
        resp = apex_client.get("/")
        assert b"Hidden Corp" not in resp.data

    def test_landing_on_tenant_subdomain_redirects(self, app, tenant):
        c = HostedFlaskClient(app, default_host=f"{tenant.subdomain}.lvh.me")
        resp = c.get("/")
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/auth/login"


# ---------------------------------------------------------------------------
# Org self-signup
# ---------------------------------------------------------------------------

class TestRegisterOrg:
    def test_get_form_returns_200(self, apex_client):
        assert apex_client.get("/register/org").status_code == 200

    def test_post_creates_pending_tenant_and_admin(self, apex_client, db):
        resp = apex_client.post("/register/org", data=_valid_org_form())
        assert resp.status_code == 302

        tenant = db.session.execute(
            db.select(Tenant).where(Tenant.subdomain == "newms")
        ).scalar_one_or_none()
        assert tenant is not None
        assert tenant.status == TenantStatus.pending

        user = db.session.execute(
            db.select(User).where(User.tenant_id == tenant.id)
        ).scalar_one_or_none()
        assert user is not None
        assert user.is_admin is True
        assert user.status == UserStatus.pending
        assert user.email == "admin@newms.com"

    def test_audit_event_created(self, apex_client, db):
        apex_client.post("/register/org", data=_valid_org_form())
        event = db.session.execute(
            db.select(AuditEvent).where(AuditEvent.action == "tenant_signup")
        ).scalar_one_or_none()
        assert event is not None
        assert event.tenant_id is None
        assert event.payload["subdomain"] == "newms"

    def test_reserved_subdomain_rejected(self, apex_client, db):
        resp = apex_client.post("/register/org", data=_valid_org_form(subdomain="admin"))
        assert resp.status_code == 200
        assert b"reserved" in resp.data.lower()
        assert db.session.execute(db.select(Tenant).where(Tenant.subdomain == "admin")).scalar_one_or_none() is None

    def test_duplicate_subdomain_rejected(self, apex_client, tenant, db):
        resp = apex_client.post("/register/org", data=_valid_org_form(subdomain=tenant.subdomain))
        assert resp.status_code == 200
        assert b"already taken" in resp.data.lower()

    def test_invalid_subdomain_pattern_rejected(self, apex_client, db):
        # "invalid!" has a special char that won't match the subdomain pattern
        resp = apex_client.post("/register/org", data=_valid_org_form(subdomain="invalid!"))
        assert resp.status_code == 200
        assert b"subdomain" in resp.data.lower()

    def test_password_mismatch_rejected(self, apex_client, db):
        resp = apex_client.post("/register/org", data=_valid_org_form(admin_password2="different123"))
        assert resp.status_code == 200
        assert b"match" in resp.data.lower()
        assert db.session.execute(db.select(Tenant).where(Tenant.subdomain == "newms")).scalar_one_or_none() is None

    def test_short_password_rejected(self, apex_client, db):
        resp = apex_client.post("/register/org", data=_valid_org_form(admin_password="short", admin_password2="short"))
        assert resp.status_code == 200
        assert db.session.execute(db.select(Tenant).where(Tenant.subdomain == "newms")).scalar_one_or_none() is None

    def test_new_tenant_subdomain_still_404(self, apex_client, app, db):
        apex_client.post("/register/org", data=_valid_org_form())
        c = HostedFlaskClient(app, default_host="newms.lvh.me")
        assert c.get("/auth/login").status_code == 404

    def test_register_org_on_tenant_subdomain_is_404(self, app, tenant):
        c = HostedFlaskClient(app, default_host=f"{tenant.subdomain}.lvh.me")
        assert c.get("/register/org").status_code == 404


# ---------------------------------------------------------------------------
# forgot-password generates an apex-based reset URL with tenant_id in token
# ---------------------------------------------------------------------------

class TestForgotPasswordApexURL:
    def _create_user(self, db, tenant):
        user = User(
            tenant_id=tenant.id,
            email="alice@example.com",
            password_hash=generate_password_hash("password12345"),
            display_name="Alice",
            status=UserStatus.active,
            notification_prefs={},
        )
        db.session.add(user)
        db.session.commit()
        return user

    def test_reset_url_points_to_apex(self, app, tenant_client, tenant, db):
        self._create_user(db, tenant)
        captured = {}

        def fake_send(to_email, reset_url):
            captured["reset_url"] = reset_url
            return "fake-id"

        with patch("app.blueprints.auth.routes.send_password_reset", side_effect=fake_send):
            tenant_client.post("/auth/forgot-password", data={"email": "alice@example.com"})

        assert "reset_url" in captured
        assert captured["reset_url"].startswith("https://lvh.me/auth/reset-password/")

    def test_token_contains_tenant_id(self, app, tenant_client, tenant, db):
        user = self._create_user(db, tenant)
        captured = {}

        def fake_send(to_email, reset_url):
            captured["reset_url"] = reset_url
            return "fake-id"

        with patch("app.blueprints.auth.routes.send_password_reset", side_effect=fake_send):
            tenant_client.post("/auth/forgot-password", data={"email": "alice@example.com"})

        assert "reset_url" in captured
        token = captured["reset_url"].split("/auth/reset-password/")[-1]
        s = _make_serializer(app)
        data = s.loads(token, max_age=3600)
        assert data["tenant_id"] == tenant.id
        assert data["email"] == user.email


# ---------------------------------------------------------------------------
# Apex-hosted password reset
# ---------------------------------------------------------------------------

class TestResetPassword:
    def _create_user(self, db, tenant):
        pw = "password12345"
        user = User(
            tenant_id=tenant.id,
            email="reset@example.com",
            password_hash=generate_password_hash(pw),
            display_name="Reset User",
            status=UserStatus.active,
            notification_prefs={},
        )
        db.session.add(user)
        db.session.commit()
        return user, pw

    def _make_token(self, app, user, tenant_id):
        s = _make_serializer(app)
        return s.dumps({
            "email": user.email,
            "ph": user.password_hash[16:32],
            "tenant_id": tenant_id,
        })

    def test_get_reset_page_on_apex(self, apex_client, app, tenant, db):
        user, _ = self._create_user(db, tenant)
        token = self._make_token(app, user, tenant.id)
        resp = apex_client.get(f"/auth/reset-password/{token}")
        assert resp.status_code == 200
        assert tenant.name.encode() in resp.data

    def test_get_reset_page_on_tenant_subdomain_is_404(self, app, tenant, db):
        user, _ = self._create_user(db, tenant)
        token = self._make_token(app, user, tenant.id)
        c = HostedFlaskClient(app, default_host=f"{tenant.subdomain}.lvh.me")
        assert c.get(f"/auth/reset-password/{token}").status_code == 404

    def test_tampered_token_redirects(self, apex_client):
        resp = apex_client.get("/auth/reset-password/badtoken")
        assert resp.status_code == 302

    def test_post_updates_password_and_redirects_to_tenant(self, apex_client, app, tenant, db):
        user, _ = self._create_user(db, tenant)
        token = self._make_token(app, user, tenant.id)
        resp = apex_client.post(
            f"/auth/reset-password/{token}",
            data={"password": "newpassword99", "password2": "newpassword99"},
        )
        assert resp.status_code == 302
        assert f"{tenant.subdomain}.lvh.me" in resp.location
        assert "/auth/login" in resp.location

        db.session.refresh(user)
        from werkzeug.security import check_password_hash
        assert check_password_hash(user.password_hash, "newpassword99")

    def test_post_password_mismatch_shows_form(self, apex_client, app, tenant, db):
        user, _ = self._create_user(db, tenant)
        token = self._make_token(app, user, tenant.id)
        resp = apex_client.post(
            f"/auth/reset-password/{token}",
            data={"password": "newpassword99", "password2": "different123"},
        )
        assert resp.status_code == 200
        assert b"match" in resp.data.lower()

    def test_cross_tenant_token_rejected(self, apex_client, app, tenant, other_tenant, db):
        # Token claims tenant_id=tenant.id, but user only exists in other_tenant
        user = User(
            tenant_id=other_tenant.id,
            email="cross@example.com",
            password_hash=generate_password_hash("password12345"),
            display_name="Cross User",
            status=UserStatus.active,
            notification_prefs={},
        )
        db.session.add(user)
        db.session.commit()

        # Token with wrong tenant_id (tenant instead of other_tenant)
        s = _make_serializer(app)
        token = s.dumps({
            "email": user.email,
            "ph": user.password_hash[16:32],
            "tenant_id": tenant.id,  # wrong tenant — user lives in other_tenant
        })
        resp = apex_client.get(f"/auth/reset-password/{token}")
        # User not found in tenant → redirect with error
        assert resp.status_code == 302
