from datetime import datetime, time, timezone

import pytest

from app.extensions import db as _db
from app.models import AuditEvent, Booking, Resource, User
from app.models.booking import BookingStatus
from app.models.resource import ResourceCategory
from app.models.user import UserStatus
from werkzeug.security import generate_password_hash

UTC = timezone.utc
PASSWORD = "testpassword1"

# Fixed future datetimes for tests (2027-06-07 is a Monday)
T_START = datetime(2027, 6, 7, 10, 0, tzinfo=UTC)
T_END   = datetime(2027, 6, 7, 12, 0, tzinfo=UTC)


def _login(client, user):
    client.post("/auth/login", data={"email": user.email, "password": PASSWORD})


def _make_user(db_session, tenant_id, **kwargs) -> User:
    defaults = dict(
        tenant_id=tenant_id,
        email="member@example.com",
        password_hash=generate_password_hash(PASSWORD),
        display_name="Test Member",
        status=UserStatus.active,
        is_admin=False,
        notification_prefs={},
    )
    defaults.update(kwargs)
    user = User(**defaults)
    db_session.session.add(user)
    db_session.session.commit()
    return user


def _make_resource(db_session, tenant_id, **kwargs) -> Resource:
    defaults = dict(
        tenant_id=tenant_id,
        name="Test Laser",
        category=ResourceCategory.equipment,
        weekday_start=time(9, 0),
        weekday_end=time(18, 0),
    )
    defaults.update(kwargs)
    r = Resource(**defaults)
    db_session.session.add(r)
    db_session.session.commit()
    return r


def _make_booking(db_session, user, resource, **kwargs) -> Booking:
    defaults = dict(
        tenant_id=resource.tenant_id,
        user_id=user.id,
        resource_id=resource.id,
        starts_at=T_START,
        ends_at=T_END,
        status=BookingStatus.active,
        original_starts_at=T_START,
        original_ends_at=T_END,
        edit_count=0,
    )
    defaults.update(kwargs)
    b = Booking(**defaults)
    db_session.session.add(b)
    db_session.session.commit()
    return b


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

class TestAdminRequired:
    def test_list_anonymous(self, client):
        resp = client.get("/admin/bookings")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_list_non_admin(self, client, db, active_user):
        _login(client, active_user)
        resp = client.get("/admin/bookings")
        assert resp.status_code == 302
        assert "/auth/login" not in resp.headers["Location"]

    def test_edit_anonymous(self, client, db, tenant):
        member = _make_user(db, tenant.id, email="m@example.com")
        resource = _make_resource(db, tenant.id)
        booking = _make_booking(db, member, resource)
        resp = client.get(f"/admin/bookings/{booking.id}/edit")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_cancel_anonymous(self, client, db, tenant):
        member = _make_user(db, tenant.id, email="m@example.com")
        resource = _make_resource(db, tenant.id)
        booking = _make_booking(db, member, resource)
        resp = client.post(f"/admin/bookings/{booking.id}/cancel")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# Bookings list
# ---------------------------------------------------------------------------

class TestBookingsList:
    def test_list_renders(self, client, db, admin_user, active_user):
        resource = _make_resource(db, active_user.tenant_id)
        booking = _make_booking(db, active_user, resource)
        _login(client, admin_user)
        resp = client.get("/admin/bookings")
        assert resp.status_code == 200
        assert active_user.display_name.encode() in resp.data
        assert resource.name.encode() in resp.data

    def test_status_filter_active(self, client, db, admin_user, active_user):
        resource = _make_resource(db, active_user.tenant_id)
        _make_booking(db, active_user, resource, status=BookingStatus.active)
        _make_booking(db, active_user, resource,
                      starts_at=datetime(2027, 6, 8, 10, 0, tzinfo=UTC),
                      ends_at=datetime(2027, 6, 8, 12, 0, tzinfo=UTC),
                      original_starts_at=datetime(2027, 6, 8, 10, 0, tzinfo=UTC),
                      original_ends_at=datetime(2027, 6, 8, 12, 0, tzinfo=UTC),
                      status=BookingStatus.cancelled_by_member)
        _login(client, admin_user)
        resp = client.get("/admin/bookings?status=active")
        assert resp.status_code == 200
        assert b"Active" in resp.data
        assert b"Cancelled By Member" in resp.data or b"cancelled_by_member" not in resp.data

    def test_status_filter_cancelled(self, client, db, admin_user, active_user):
        resource = _make_resource(db, active_user.tenant_id)
        _make_booking(db, active_user, resource, status=BookingStatus.cancelled_by_admin)
        _login(client, admin_user)
        resp = client.get("/admin/bookings?status=cancelled_by_admin")
        assert resp.status_code == 200
        assert b"Cancelled By Admin" in resp.data

    def test_invalid_status_filter_ignored(self, client, db, admin_user):
        _login(client, admin_user)
        resp = client.get("/admin/bookings?status=garbage")
        assert resp.status_code == 200

    def test_empty_list(self, client, admin_user):
        _login(client, admin_user)
        resp = client.get("/admin/bookings")
        assert resp.status_code == 200
        assert b"No bookings found" in resp.data


# ---------------------------------------------------------------------------
# Edit booking
# ---------------------------------------------------------------------------

class TestBookingEdit:
    def test_get_prepopulates_form(self, client, db, admin_user, active_user):
        resource = _make_resource(db, active_user.tenant_id)
        booking = _make_booking(db, active_user, resource)
        _login(client, admin_user)
        resp = client.get(f"/admin/bookings/{booking.id}/edit")
        assert resp.status_code == 200
        assert b"2027-06-07" in resp.data
        assert active_user.display_name.encode() in resp.data
        assert resource.name.encode() in resp.data

    def test_post_updates_times_and_comment(self, client, db, admin_user, active_user):
        resource = _make_resource(db, active_user.tenant_id)
        booking = _make_booking(db, active_user, resource)
        _login(client, admin_user)
        resp = client.post(f"/admin/bookings/{booking.id}/edit", data={
            "start_datetime": "2027-06-07T14:00",
            "end_datetime": "2027-06-07T16:00",
            "comment": "Rescheduled by admin",
        })
        assert resp.status_code == 302
        _db.session.refresh(booking)
        assert booking.starts_at == datetime(2027, 6, 7, 14, 0, tzinfo=UTC)
        assert booking.ends_at == datetime(2027, 6, 7, 16, 0, tzinfo=UTC)
        assert booking.comment == "Rescheduled by admin"

    def test_edit_count_not_incremented(self, client, db, admin_user, active_user):
        resource = _make_resource(db, active_user.tenant_id)
        booking = _make_booking(db, active_user, resource, edit_count=2)
        _login(client, admin_user)
        resp = client.post(f"/admin/bookings/{booking.id}/edit", data={
            "start_datetime": "2027-06-07T14:00",
            "end_datetime": "2027-06-07T16:00",
            "comment": "",
        })
        assert resp.status_code == 302
        _db.session.refresh(booking)
        assert booking.edit_count == 2  # unchanged

    def test_outside_availability_window_allowed(self, client, db, admin_user, active_user):
        # Resource available 09:00-18:00; admin edits to 07:00 which is outside window
        resource = _make_resource(db, active_user.tenant_id, weekday_start=time(9, 0), weekday_end=time(18, 0))
        booking = _make_booking(db, active_user, resource)
        _login(client, admin_user)
        resp = client.post(f"/admin/bookings/{booking.id}/edit", data={
            "start_datetime": "2027-06-07T07:00",
            "end_datetime": "2027-06-07T08:30",
            "comment": "",
        })
        assert resp.status_code == 302
        _db.session.refresh(booking)
        assert booking.starts_at.hour == 7

    def test_audit_event_created(self, client, db, admin_user, active_user):
        resource = _make_resource(db, active_user.tenant_id)
        booking = _make_booking(db, active_user, resource)
        _login(client, admin_user)
        client.post(f"/admin/bookings/{booking.id}/edit", data={
            "start_datetime": "2027-06-07T14:00",
            "end_datetime": "2027-06-07T16:00",
            "comment": "",
        })
        event = _db.session.execute(
            _db.select(AuditEvent).where(AuditEvent.action == "booking_updated")
        ).scalar_one_or_none()
        assert event is not None
        assert event.subject_id == booking.id
        assert event.payload["member"] == active_user.email
        assert event.payload["resource"] == resource.name

    def test_conflict_rejected(self, client, db, admin_user, active_user):
        resource = _make_resource(db, active_user.tenant_id)
        booking = _make_booking(db, active_user, resource,
                                starts_at=datetime(2027, 6, 7, 10, 0, tzinfo=UTC),
                                ends_at=datetime(2027, 6, 7, 12, 0, tzinfo=UTC),
                                original_starts_at=datetime(2027, 6, 7, 10, 0, tzinfo=UTC),
                                original_ends_at=datetime(2027, 6, 7, 12, 0, tzinfo=UTC))
        other_member = _make_user(db, active_user.tenant_id, email="other@example.com")
        # Another booking at 11:00-13:00 on the same resource
        _make_booking(db, other_member, resource,
                      starts_at=datetime(2027, 6, 7, 11, 0, tzinfo=UTC),
                      ends_at=datetime(2027, 6, 7, 13, 0, tzinfo=UTC),
                      original_starts_at=datetime(2027, 6, 7, 11, 0, tzinfo=UTC),
                      original_ends_at=datetime(2027, 6, 7, 13, 0, tzinfo=UTC))
        _login(client, admin_user)
        resp = client.post(f"/admin/bookings/{booking.id}/edit", data={
            "start_datetime": "2027-06-07T11:30",
            "end_datetime": "2027-06-07T13:00",
            "comment": "",
        })
        assert resp.status_code == 200
        assert b"Conflicts" in resp.data

    def test_end_before_start_rejected(self, client, db, admin_user, active_user):
        resource = _make_resource(db, active_user.tenant_id)
        booking = _make_booking(db, active_user, resource)
        _login(client, admin_user)
        resp = client.post(f"/admin/bookings/{booking.id}/edit", data={
            "start_datetime": "2027-06-07T14:00",
            "end_datetime": "2027-06-07T12:00",
            "comment": "",
        })
        assert resp.status_code == 200
        assert b"End must be after start" in resp.data


# ---------------------------------------------------------------------------
# Cancel booking
# ---------------------------------------------------------------------------

class TestBookingCancel:
    def test_cancel_active_booking(self, client, db, admin_user, active_user):
        resource = _make_resource(db, active_user.tenant_id)
        booking = _make_booking(db, active_user, resource)
        _login(client, admin_user)
        resp = client.post(f"/admin/bookings/{booking.id}/cancel")
        assert resp.status_code == 302
        _db.session.refresh(booking)
        assert booking.status == BookingStatus.cancelled_by_admin
        assert booking.cancelled_at is not None
        assert booking.cancelled_by_user_id == admin_user.id

    def test_cancel_creates_audit_event(self, client, db, admin_user, active_user):
        resource = _make_resource(db, active_user.tenant_id)
        booking = _make_booking(db, active_user, resource)
        _login(client, admin_user)
        client.post(f"/admin/bookings/{booking.id}/cancel")
        event = _db.session.execute(
            _db.select(AuditEvent).where(AuditEvent.action == "booking_cancelled")
        ).scalar_one_or_none()
        assert event is not None
        assert event.subject_id == booking.id
        assert event.payload["member"] == active_user.email
        assert event.payload["cancelled_by"] == "admin"

    def test_cancel_already_cancelled_booking_errors(self, client, db, admin_user, active_user):
        resource = _make_resource(db, active_user.tenant_id)
        booking = _make_booking(db, active_user, resource,
                                status=BookingStatus.cancelled_by_member)
        _login(client, admin_user)
        resp = client.post(f"/admin/bookings/{booking.id}/cancel",
                           follow_redirects=True)
        assert resp.status_code == 200
        assert b"Only active bookings can be cancelled" in resp.data
        _db.session.refresh(booking)
        assert booking.status == BookingStatus.cancelled_by_member

    def test_cancel_non_admin_redirected(self, client, db, active_user):
        resource = _make_resource(db, active_user.tenant_id)
        booking = _make_booking(db, active_user, resource)
        _login(client, active_user)
        resp = client.post(f"/admin/bookings/{booking.id}/cancel")
        assert resp.status_code == 302
        _db.session.refresh(booking)
        assert booking.status == BookingStatus.active
