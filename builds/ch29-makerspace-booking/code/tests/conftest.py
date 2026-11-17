import pytest
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

from flask.testing import FlaskClient

from app import create_app
from app.extensions import db as _db
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from werkzeug.security import generate_password_hash


class HostedFlaskClient(FlaskClient):
    """FlaskClient subclass that injects a default HTTP_HOST into every request.

    Flask 3.x / Werkzeug 3.x removed environ_base from Client.__init__.
    We override open() to inject HTTP_HOST via environ_overrides so it takes
    precedence over Flask's SERVER_NAME-derived base_url computation.

    session_transaction() is also overridden to use the same host so that
    cookie domain matching works correctly (cookies are stored keyed by domain).
    """

    def __init__(self, *args, default_host: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._default_host = default_host

    def open(self, *args, **kwargs):
        if self._default_host:
            overrides = dict(kwargs.pop("environ_overrides", None) or {})
            overrides.setdefault("HTTP_HOST", self._default_host)
            kwargs["environ_overrides"] = overrides
        return super().open(*args, **kwargs)

    @contextmanager
    def session_transaction(self, *args, **kwargs):
        if self._default_host and not args:
            overrides = dict(kwargs.pop("environ_overrides", None) or {})
            overrides.setdefault("HTTP_HOST", self._default_host)
            kwargs["environ_overrides"] = overrides
        with super().session_transaction(*args, **kwargs) as sess:
            yield sess


@pytest.fixture(scope="session")
def _app_instance():
    return create_app("testing")


@pytest.fixture(scope="session", autouse=True)
def _tables(_app_instance):
    """Create tables once for the session; drop them at the end.

    Uses short-lived contexts so the connection is released immediately,
    preventing idle-in-transaction locks from blocking test cleanup.
    """
    with _app_instance.app_context():
        _db.create_all()
    yield
    with _app_instance.app_context():
        _db.drop_all()


@pytest.fixture
def app(_app_instance, _tables):
    """Push a FRESH app context per test.

    Flask 3.x stores g on the app context, not the request context.
    Without this, Flask-Login's g._login_user leaks across requests
    that share the same long-lived app context.
    """
    with _app_instance.app_context():
        yield _app_instance


@pytest.fixture
def db(app):
    return _db


@pytest.fixture(autouse=True)
def clean_tables(db):
    """Truncate all tables after every test to keep tests isolated."""
    yield
    db.session.rollback()
    for table in reversed(db.metadata.sorted_tables):
        db.session.execute(table.delete())
    db.session.commit()
    db.session.expunge_all()


# ---------------------------------------------------------------------------
# Tenant fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tenant(db):
    t = Tenant(name="Test Org", subdomain="testorg", status=TenantStatus.active, is_listed=True)
    db.session.add(t)
    db.session.commit()
    return t


@pytest.fixture
def other_tenant(db):
    t = Tenant(name="Other Org", subdomain="other", status=TenantStatus.active, is_listed=True)
    db.session.add(t)
    db.session.commit()
    return t


# ---------------------------------------------------------------------------
# Client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(app, tenant):
    """Default client — routes through the testorg tenant subdomain."""
    return HostedFlaskClient(app, default_host=f"{tenant.subdomain}.lvh.me")


@pytest.fixture
def tenant_client(app, tenant):
    return HostedFlaskClient(app, default_host=f"{tenant.subdomain}.lvh.me")


@pytest.fixture
def apex_client(app):
    return HostedFlaskClient(app, default_host="lvh.me")


@pytest.fixture
def super_admin_client(app):
    return HostedFlaskClient(app, default_host="app.lvh.me")


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------

def _make_user(db_session, **kwargs) -> User:
    defaults = dict(
        email="user@example.com",
        password_hash=generate_password_hash("testpassword1"),
        display_name="Test User",
        status=UserStatus.active,
        is_admin=False,
        notification_prefs={},
        tenant_id=None,
    )
    defaults.update(kwargs)
    user = User(**defaults)
    db_session.session.add(user)
    db_session.session.commit()
    return user


@pytest.fixture
def active_user(db, tenant):
    return _make_user(db, email="active@example.com", status=UserStatus.active, tenant_id=tenant.id)


@pytest.fixture
def pending_user(db, tenant):
    return _make_user(db, email="pending@example.com", status=UserStatus.pending, tenant_id=tenant.id)


@pytest.fixture
def frozen_user(db, tenant):
    return _make_user(db, email="frozen@example.com", status=UserStatus.frozen, tenant_id=tenant.id)


@pytest.fixture
def rejected_user(db, tenant):
    return _make_user(
        db,
        email="rejected@example.com",
        status=UserStatus.rejected,
        rejection_note="Not eligible.",
        tenant_id=tenant.id,
    )


@pytest.fixture
def admin_user(db, tenant):
    return _make_user(
        db,
        email="admin@example.com",
        status=UserStatus.active,
        is_admin=True,
        tenant_id=tenant.id,
    )


@pytest.fixture
def super_admin_user(db):
    return _make_user(
        db,
        email="super@example.com",
        status=UserStatus.active,
        is_super_admin=True,
        tenant_id=None,
    )


@pytest.fixture
def upload_dir(app, tmp_path):
    """Redirect UPLOAD_FOLDER to a temp dir for the duration of the test."""
    old = app.config.get("UPLOAD_FOLDER")
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    yield tmp_path
    app.config["UPLOAD_FOLDER"] = old
