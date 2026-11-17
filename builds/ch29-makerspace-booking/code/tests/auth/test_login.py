import pytest
from app.models.user import UserStatus


def _login(client, email, password, **extra):
    return client.post("/auth/login", data={"email": email, "password": password, **extra})


class TestLoginGet:
    def test_returns_200(self, client):
        assert client.get("/auth/login").status_code == 200

    def test_shows_form(self, client):
        resp = client.get("/auth/login")
        assert b"email" in resp.data
        assert b"password" in resp.data


class TestLoginSuccess:
    def test_active_user_redirects_to_member(self, client, active_user):
        resp = _login(client, active_user.email, "testpassword1")
        assert resp.status_code == 302
        assert "/auth/pending" not in resp.headers["Location"]

    def test_active_user_session_created(self, client, active_user):
        _login(client, active_user.email, "testpassword1")
        with client.session_transaction() as sess:
            assert "_user_id" in sess

    def test_pending_user_redirects_to_pending(self, client, pending_user):
        resp = _login(client, pending_user.email, "testpassword1")
        assert resp.status_code == 302
        assert "/auth/pending" in resp.headers["Location"]

    def test_pending_user_session_created(self, client, pending_user):
        _login(client, pending_user.email, "testpassword1")
        with client.session_transaction() as sess:
            assert "_user_id" in sess

    def test_email_is_case_insensitive(self, client, active_user):
        resp = _login(client, active_user.email.upper(), "testpassword1")
        assert resp.status_code == 302
        with client.session_transaction() as sess:
            assert "_user_id" in sess


class TestLoginFailure:
    def test_wrong_password_shows_error(self, client, active_user):
        resp = _login(client, active_user.email, "wrongpassword", follow_redirects=True)
        # note: no follow_redirects — the route renders the template directly
        assert b"Invalid email or password" in resp.data

    def test_unknown_email_shows_error(self, client):
        resp = _login(client, "nobody@example.com", "testpassword1")
        assert b"Invalid email or password" in resp.data

    def test_wrong_password_no_session(self, client, active_user):
        _login(client, active_user.email, "wrongpassword")
        with client.session_transaction() as sess:
            assert "_user_id" not in sess

    def test_frozen_user_shows_frozen_error(self, client, frozen_user):
        resp = _login(client, frozen_user.email, "testpassword1")
        assert b"frozen" in resp.data

    def test_frozen_user_no_session(self, client, frozen_user):
        _login(client, frozen_user.email, "testpassword1")
        with client.session_transaction() as sess:
            assert "_user_id" not in sess

    def test_rejected_user_shows_rejected_error(self, client, rejected_user):
        resp = _login(client, rejected_user.email, "testpassword1")
        assert b"rejected" in resp.data

    def test_rejected_user_no_session(self, client, rejected_user):
        _login(client, rejected_user.email, "testpassword1")
        with client.session_transaction() as sess:
            assert "_user_id" not in sess


class TestLoginNextParam:
    def test_valid_next_param_redirects_there(self, client, active_user):
        resp = _login(client, active_user.email, "testpassword1", next="/auth/pending")
        assert "/auth/pending" in resp.headers["Location"]

    def test_next_in_query_string_used(self, client, active_user):
        resp = client.post(
            "/auth/login?next=/auth/pending",
            data={"email": active_user.email, "password": "testpassword1"},
        )
        assert "/auth/pending" in resp.headers["Location"]

    def test_external_next_blocked(self, client, active_user):
        resp = _login(client, active_user.email, "testpassword1", next="http://evil.com/steal")
        assert "evil.com" not in resp.headers["Location"]

    def test_protocol_relative_next_blocked(self, client, active_user):
        resp = _login(client, active_user.email, "testpassword1", next="//evil.com")
        assert "evil.com" not in resp.headers["Location"]


class TestLoginAlreadyAuthenticated:
    def test_active_user_redirected_away_from_login(self, client, active_user):
        _login(client, active_user.email, "testpassword1")
        resp = client.get("/auth/login")
        assert resp.status_code == 302
        assert "/auth/login" not in resp.headers["Location"]

    def test_pending_user_redirected_to_pending(self, client, pending_user):
        _login(client, pending_user.email, "testpassword1")
        resp = client.get("/auth/login")
        assert resp.status_code == 302
        assert "/auth/pending" in resp.headers["Location"]
