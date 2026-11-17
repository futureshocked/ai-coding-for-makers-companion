from datetime import datetime, timedelta, timezone

import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db as _db
from app.models import Booking, Resource, User
from app.models.booking import BookingStatus
from app.models.resource import ResourceCategory
from app.models.user import UserStatus

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Local helpers (kept local — conftest helpers are fixture-based only)
# ---------------------------------------------------------------------------

def _make_user(db_session, tenant_id, email, is_admin=False):
    from datetime import time
    u = User(
        tenant_id=tenant_id,
        email=email,
        password_hash=generate_password_hash("testpassword1"),
        display_name=email.split("@")[0],
        status=UserStatus.active,
        is_admin=is_admin,
        notification_prefs={},
    )
    db_session.session.add(u)
    db_session.session.commit()
    return u


def _make_resource(db_session, tenant_id, name="Resource"):
    from datetime import time
    r = Resource(
        tenant_id=tenant_id,
        name=name,
        category=ResourceCategory.equipment,
        weekday_start=time(9, 0),
        weekday_end=time(17, 0),
        is_archived=False,
    )
    db_session.session.add(r)
    db_session.session.commit()
    return r


def _make_booking(db_session, tenant_id, user_id, resource_id):
    starts = datetime.now(UTC) + timedelta(days=1)
    ends = starts + timedelta(hours=2)
    b = Booking(
        tenant_id=tenant_id,
        user_id=user_id,
        resource_id=resource_id,
        starts_at=starts,
        ends_at=ends,
        status=BookingStatus.active,
        original_starts_at=starts,
        original_ends_at=ends,
    )
    db_session.session.add(b)
    db_session.session.commit()
    return b


def _login(client, email, password="testpassword1"):
    client.post("/auth/login", data={"email": email, "password": password})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def other_tenant_client(app, other_tenant):
    from tests.conftest import HostedFlaskClient
    return HostedFlaskClient(app, default_host=f"{other_tenant.subdomain}.lvh.me")


# ---------------------------------------------------------------------------
# Cross-tenant isolation tests
# ---------------------------------------------------------------------------

class TestCrossTenantIsolation:

    def test_member_cannot_access_other_tenant_booking(
        self, db, tenant, other_tenant, tenant_client
    ):
        """Member on testorg gets 404 when accessing a booking ID from other tenant."""
        _make_user(db, tenant.id, "member@testorg.com")
        other_member = _make_user(db, other_tenant.id, "member@other.com")
        other_resource = _make_resource(db, other_tenant.id, "Other Resource")
        other_booking = _make_booking(db, other_tenant.id, other_member.id, other_resource.id)

        _login(tenant_client, "member@testorg.com")
        rv = tenant_client.get(f"/bookings/{other_booking.id}/edit")
        assert rv.status_code == 404

    def test_admin_cannot_edit_other_tenant_resource(
        self, db, tenant, other_tenant, tenant_client
    ):
        """Admin on testorg gets 404 when editing a resource ID from other tenant."""
        _make_user(db, tenant.id, "admin@testorg.com", is_admin=True)
        other_resource = _make_resource(db, other_tenant.id, "Other Resource")

        _login(tenant_client, "admin@testorg.com")
        rv = tenant_client.get(f"/admin/resources/{other_resource.id}/edit")
        assert rv.status_code == 404

    def test_members_list_scoped_to_own_tenant(
        self, db, tenant, other_tenant, tenant_client
    ):
        """Admin on testorg sees only testorg members, not other tenant's members."""
        _make_user(db, tenant.id, "admin@testorg.com", is_admin=True)
        _make_user(db, tenant.id, "alice@testorg.com")
        _make_user(db, other_tenant.id, "bob@other.com")

        _login(tenant_client, "admin@testorg.com")
        rv = tenant_client.get("/admin/members")
        assert rv.status_code == 200
        body = rv.data.decode()
        assert "alice@testorg.com" in body
        assert "bob@other.com" not in body

    def test_resources_list_scoped_to_own_tenant(
        self, db, tenant, other_tenant, tenant_client
    ):
        """Admin on testorg sees only testorg resources, not other tenant's resources."""
        _make_user(db, tenant.id, "admin@testorg.com", is_admin=True)
        _make_resource(db, tenant.id, "Testorg Resource")
        _make_resource(db, other_tenant.id, "Other Resource")

        _login(tenant_client, "admin@testorg.com")
        rv = tenant_client.get("/admin/resources")
        assert rv.status_code == 200
        body = rv.data.decode()
        assert "Testorg Resource" in body
        assert "Other Resource" not in body

    def test_bookings_list_scoped_to_own_tenant(
        self, db, tenant, other_tenant, tenant_client
    ):
        """Admin on testorg sees only testorg bookings, not other tenant's bookings."""
        _make_user(db, tenant.id, "admin@testorg.com", is_admin=True)
        member = _make_user(db, tenant.id, "member@testorg.com")
        other_member = _make_user(db, other_tenant.id, "member@other.com")
        testorg_res = _make_resource(db, tenant.id, "Testorg Resource")
        other_res = _make_resource(db, other_tenant.id, "Other Resource")
        _make_booking(db, tenant.id, member.id, testorg_res.id)
        _make_booking(db, other_tenant.id, other_member.id, other_res.id)

        _login(tenant_client, "admin@testorg.com")
        rv = tenant_client.get("/admin/bookings")
        assert rv.status_code == 200
        body = rv.data.decode()
        assert "Testorg Resource" in body
        assert "Other Resource" not in body

    def test_admin_cannot_cancel_other_tenant_booking(
        self, db, tenant, other_tenant, tenant_client
    ):
        """Admin on testorg gets 404 when trying to cancel a booking from other tenant."""
        _make_user(db, tenant.id, "admin@testorg.com", is_admin=True)
        other_member = _make_user(db, other_tenant.id, "member@other.com")
        other_resource = _make_resource(db, other_tenant.id, "Other Resource")
        other_booking = _make_booking(db, other_tenant.id, other_member.id, other_resource.id)

        _login(tenant_client, "admin@testorg.com")
        rv = tenant_client.post(f"/admin/bookings/{other_booking.id}/cancel")
        assert rv.status_code == 404
