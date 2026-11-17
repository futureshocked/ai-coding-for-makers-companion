import pytest
from app.extensions import db
from app.models.user import User, UserStatus
from werkzeug.security import check_password_hash


def _post(client, **form):
    return client.post("/auth/register", data=form)


def _valid(client, **overrides):
    data = dict(email="new@example.com", password="longpassword1", display_name="New User")
    data.update(overrides)
    return _post(client, **data)


class TestRegisterGet:
    def test_returns_200(self, client):
        resp = client.get("/auth/register")
        assert resp.status_code == 200

    def test_shows_form_fields(self, client):
        resp = client.get("/auth/register")
        assert b"display_name" in resp.data
        assert b"email" in resp.data
        assert b"password" in resp.data


class TestRegisterSuccess:
    def test_redirects_to_pending(self, client):
        resp = _valid(client)
        assert resp.status_code == 302
        assert "/auth/pending" in resp.headers["Location"]

    def test_creates_user_with_pending_status(self, client):
        _valid(client)
        user = db.session.execute(
            db.select(User).where(User.email == "new@example.com")
        ).scalar_one()
        assert user.status == UserStatus.pending

    def test_hashes_password(self, client):
        _valid(client, password="longpassword1")
        user = db.session.execute(
            db.select(User).where(User.email == "new@example.com")
        ).scalar_one()
        assert check_password_hash(user.password_hash, "longpassword1")

    def test_no_session_created(self, client):
        _valid(client)
        with client.session_transaction() as sess:
            assert "_user_id" not in sess

    def test_stores_display_name(self, client):
        _valid(client, display_name="Ada Lovelace")
        user = db.session.execute(
            db.select(User).where(User.email == "new@example.com")
        ).scalar_one()
        assert user.display_name == "Ada Lovelace"

    def test_is_not_admin(self, client):
        _valid(client)
        user = db.session.execute(
            db.select(User).where(User.email == "new@example.com")
        ).scalar_one()
        assert not user.is_admin


class TestRegisterValidation:
    def test_short_password_shows_error(self, client):
        resp = _valid(client, password="short", follow_redirects=True)
        # follow_redirects not applicable for non-redirect; check inline error
        resp = client.post(
            "/auth/register",
            data={"email": "x@example.com", "password": "short", "display_name": "X"},
            follow_redirects=True,
        )
        assert b"10 characters" in resp.data

    def test_missing_email_shows_error(self, client):
        resp = client.post(
            "/auth/register",
            data={"email": "", "password": "longpassword1", "display_name": "X"},
            follow_redirects=True,
        )
        assert b"Email is required" in resp.data

    def test_missing_display_name_shows_error(self, client):
        resp = client.post(
            "/auth/register",
            data={"email": "x@example.com", "password": "longpassword1", "display_name": ""},
            follow_redirects=True,
        )
        assert b"Display name is required" in resp.data

    def test_validation_error_preserves_email(self, client):
        resp = client.post(
            "/auth/register",
            data={"email": "typed@example.com", "password": "short", "display_name": "X"},
        )
        assert b"typed@example.com" in resp.data


class TestRegisterDuplicateEmail:
    def test_active_email_shows_error(self, client, active_user):
        resp = client.post(
            "/auth/register",
            data={"email": active_user.email, "password": "longpassword1", "display_name": "Dup"},
            follow_redirects=True,
        )
        assert b"already registered" in resp.data

    def test_pending_email_shows_error(self, client, pending_user):
        resp = client.post(
            "/auth/register",
            data={"email": pending_user.email, "password": "longpassword1", "display_name": "Dup"},
            follow_redirects=True,
        )
        assert b"already registered" in resp.data

    def test_rejected_user_resets_to_pending(self, client, rejected_user):
        resp = _post(
            client,
            email=rejected_user.email,
            password="newlongpassword",
            display_name="Updated Name",
        )
        assert resp.status_code == 302
        assert "/auth/pending" in resp.headers["Location"]
        db.session.refresh(rejected_user)
        assert rejected_user.status == UserStatus.pending

    def test_rejected_user_clears_rejection_note(self, client, rejected_user):
        _post(
            client,
            email=rejected_user.email,
            password="newlongpassword",
            display_name="Updated",
        )
        db.session.refresh(rejected_user)
        assert rejected_user.rejection_note is None

    def test_rejected_user_updates_password(self, client, rejected_user):
        _post(
            client,
            email=rejected_user.email,
            password="brandnewpass1",
            display_name="Updated",
        )
        db.session.refresh(rejected_user)
        assert check_password_hash(rejected_user.password_hash, "brandnewpass1")


class TestRegisterAuthenticatedUser:
    def test_active_user_redirected_away(self, client, active_user):
        client.post(
            "/auth/login",
            data={"email": active_user.email, "password": "testpassword1"},
        )
        resp = client.get("/auth/register")
        assert resp.status_code == 302
        assert "/auth/register" not in resp.headers["Location"]

    def test_pending_user_redirected_to_pending(self, client, pending_user):
        client.post(
            "/auth/login",
            data={"email": pending_user.email, "password": "testpassword1"},
        )
        resp = client.get("/auth/register")
        assert resp.status_code == 302
        assert "/auth/pending" in resp.headers["Location"]
