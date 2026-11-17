import pytest
from unittest.mock import patch
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import check_password_hash

from app.extensions import db
from app.models.user import User

_patch_email = lambda: patch("app.blueprints.auth.routes.send_password_reset")


def _make_token(app, email, password_hash, tenant_id=None):
    s = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="password-reset")
    return s.dumps({"email": email, "ph": password_hash[16:32], "tenant_id": tenant_id})


class TestForgotPassword:
    def test_get_returns_200(self, client):
        assert client.get("/auth/forgot-password").status_code == 200

    def test_post_known_email_flashes_message(self, client, active_user):
        with _patch_email():
            resp = client.post(
                "/auth/forgot-password",
                data={"email": active_user.email},
                follow_redirects=True,
            )
        assert b"reset link" in resp.data

    def test_post_unknown_email_same_message(self, client):
        resp = client.post(
            "/auth/forgot-password",
            data={"email": "nobody@example.com"},
            follow_redirects=True,
        )
        assert b"reset link" in resp.data

    def test_post_redirects_to_login(self, client, active_user):
        with _patch_email():
            resp = client.post("/auth/forgot-password", data={"email": active_user.email})
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]


class TestResetPasswordToken:
    def test_invalid_token_redirects_to_apex(self, apex_client):
        resp = apex_client.get("/auth/reset-password/notavalidtoken")
        assert resp.status_code == 302

    def test_valid_token_shows_form(self, apex_client, active_user, tenant, app):
        token = _make_token(app, active_user.email, active_user.password_hash, tenant_id=tenant.id)
        resp = apex_client.get(f"/auth/reset-password/{token}")
        assert resp.status_code == 200
        assert b"password" in resp.data

    def test_tampered_token_redirects(self, apex_client, active_user, tenant, app):
        token = _make_token(app, active_user.email, active_user.password_hash, tenant_id=tenant.id)
        resp = apex_client.get(f"/auth/reset-password/{token}TAMPERED")
        assert resp.status_code == 302


class TestResetPasswordPost:
    def test_valid_reset_updates_password(self, apex_client, active_user, tenant, app):
        token = _make_token(app, active_user.email, active_user.password_hash, tenant_id=tenant.id)
        apex_client.post(
            f"/auth/reset-password/{token}",
            data={"password": "brandnewpass1", "password2": "brandnewpass1"},
        )
        db.session.refresh(active_user)
        assert check_password_hash(active_user.password_hash, "brandnewpass1")

    def test_valid_reset_redirects_to_tenant_login(self, apex_client, active_user, tenant, app):
        token = _make_token(app, active_user.email, active_user.password_hash, tenant_id=tenant.id)
        resp = apex_client.post(
            f"/auth/reset-password/{token}",
            data={"password": "brandnewpass1", "password2": "brandnewpass1"},
        )
        assert resp.status_code == 302
        assert tenant.subdomain in resp.headers["Location"]
        assert "/auth/login" in resp.headers["Location"]

    def test_short_password_shows_error(self, apex_client, active_user, tenant, app):
        token = _make_token(app, active_user.email, active_user.password_hash, tenant_id=tenant.id)
        resp = apex_client.post(
            f"/auth/reset-password/{token}",
            data={"password": "short", "password2": "short"},
            follow_redirects=True,
        )
        assert b"10 characters" in resp.data

    def test_mismatched_passwords_show_error(self, apex_client, active_user, tenant, app):
        token = _make_token(app, active_user.email, active_user.password_hash, tenant_id=tenant.id)
        resp = apex_client.post(
            f"/auth/reset-password/{token}",
            data={"password": "longpassword1", "password2": "different111"},
            follow_redirects=True,
        )
        assert b"do not match" in resp.data

    def test_token_invalidated_after_use(self, apex_client, active_user, tenant, app):
        token = _make_token(app, active_user.email, active_user.password_hash, tenant_id=tenant.id)
        apex_client.post(
            f"/auth/reset-password/{token}",
            data={"password": "brandnewpass1", "password2": "brandnewpass1"},
        )
        # Second use should fail since password_hash changed
        resp = apex_client.get(f"/auth/reset-password/{token}")
        assert resp.status_code == 302
