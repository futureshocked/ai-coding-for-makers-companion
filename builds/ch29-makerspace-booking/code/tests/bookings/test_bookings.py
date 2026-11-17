from datetime import date, datetime, time, timedelta, timezone

import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db as _db
from app.models import Booking, Resource
from app.models.booking import BookingStatus
from app.models.resource import ResourceCategory, ResourceState
from app.models.user import User, UserStatus

PASSWORD = "testpassword1"

# Monday 2026-05-25 (weekday)
MONDAY = date(2026, 5, 25)
# Saturday 2026-05-24 (weekend)
SATURDAY = date(2026, 5, 24)


def _utc(year, month, day, hour=0, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _login(client, user):
    client.post("/auth/login", data={"email": user.email, "password": PASSWORD})


def _make_resource(db, tenant_id, **kwargs) -> Resource:
    defaults = dict(
        name="Test Resource",
        category=ResourceCategory.equipment,
        description=None,
        location=None,
        weekday_start=time(9, 0),
        weekday_end=time(18, 0),
        weekend_start=None,
        weekend_end=None,
        is_archived=False,
        state=ResourceState.available,
        tenant_id=tenant_id,
    )
    defaults.update(kwargs)
    r = Resource(**defaults)
    db.session.add(r)
    db.session.commit()
    return r


def _make_booking(db, user, resource, starts_at, ends_at, **kwargs) -> Booking:
    defaults = dict(
        status=BookingStatus.active,
        original_starts_at=starts_at,
        original_ends_at=ends_at,
        tenant_id=resource.tenant_id,
    )
    defaults.update(kwargs)
    b = Booking(
        user_id=user.id,
        resource_id=resource.id,
        starts_at=starts_at,
        ends_at=ends_at,
        **defaults,
    )
    db.session.add(b)
    db.session.commit()
    return b


def _make_other_user(db, tenant_id) -> User:
    u = User(
        email="other@example.com",
        password_hash=generate_password_hash(PASSWORD),
        display_name="Other User",
        status=UserStatus.active,
        is_admin=False,
        notification_prefs={},
        tenant_id=tenant_id,
    )
    db.session.add(u)
    db.session.commit()
    return u


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

class TestMemberRequired:
    def test_index_anonymous(self, client):
        resp = client.get("/home")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_booking_form_anonymous(self, client):
        resp = client.get("/resources/1/book")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_booking_create_anonymous(self, client):
        resp = client.post("/resources/1/book", data={})
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_my_bookings_anonymous(self, client):
        resp = client.get("/my-bookings")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_cancel_anonymous(self, client):
        resp = client.post("/bookings/1/cancel")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_index_pending(self, client, pending_user):
        _login(client, pending_user)
        resp = client.get("/home")
        assert resp.status_code == 302
        assert "/auth/pending" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# Resource list  GET /
# ---------------------------------------------------------------------------

class TestResourceList:
    def test_shows_active_resources(self, client, db, active_user):
        _make_resource(db, active_user.tenant_id, name="Laser Cutter")
        _make_resource(db, active_user.tenant_id, name="3D Printer", category=ResourceCategory.workbench)
        _login(client, active_user)
        resp = client.get("/home")
        assert resp.status_code == 200
        assert b"Laser Cutter" in resp.data
        assert b"3D Printer" in resp.data

    def test_hides_archived_resource(self, client, db, active_user):
        _make_resource(db, active_user.tenant_id, name="Active One")
        _make_resource(db, active_user.tenant_id, name="Archived One", is_archived=True)
        _login(client, active_user)
        resp = client.get("/home")
        assert b"Active One" in resp.data
        assert b"Archived One" not in resp.data

    def test_category_filter(self, client, db, active_user):
        _make_resource(db, active_user.tenant_id, name="Drill", category=ResourceCategory.equipment)
        _make_resource(db, active_user.tenant_id, name="Conference Room", category=ResourceCategory.meeting_room)
        _login(client, active_user)
        resp = client.get("/home?category=equipment")
        assert b"Drill" in resp.data
        assert b"Conference Room" not in resp.data

    def test_invalid_category_ignored(self, client, db, active_user):
        _make_resource(db, active_user.tenant_id, name="Workbench A")
        _login(client, active_user)
        resp = client.get("/home?category=bogus")
        assert resp.status_code == 200
        assert b"Workbench A" in resp.data

    def test_empty_state(self, client, db, active_user):
        _login(client, active_user)
        resp = client.get("/home")
        assert resp.status_code == 200
        assert b"No resources found" in resp.data

    def test_shows_thumbnail_img(self, client, db, active_user):
        _make_resource(db, active_user.tenant_id, name="Laser Cutter", thumbnail="xyz789.png")
        _login(client, active_user)
        resp = client.get("/home")
        assert b"uploads/resources/xyz789.png" in resp.data

    def test_shows_placeholder_when_no_thumbnail(self, client, db, active_user):
        _make_resource(db, active_user.tenant_id, name="Band Saw")
        _login(client, active_user)
        resp = client.get("/home")
        assert b"resource_placeholder.svg" in resp.data


# ---------------------------------------------------------------------------
# Booking form  GET /resources/<id>/book
# ---------------------------------------------------------------------------

class TestBookingForm:
    def test_404_for_missing_resource(self, client, active_user):
        _login(client, active_user)
        resp = client.get("/resources/9999/book")
        assert resp.status_code == 404

    def test_404_for_archived_resource(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id, is_archived=True)
        _login(client, active_user)
        resp = client.get(f"/resources/{r.id}/book")
        assert resp.status_code == 404

    def test_book_category_shows_date_inputs(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id, category=ResourceCategory.book)
        _login(client, active_user)
        resp = client.get(f"/resources/{r.id}/book")
        assert resp.status_code == 200
        # Check for HTML element (not CSS selector which also contains these strings)
        assert b'<input type="date"' in resp.data
        assert b'name="checkout_date"' in resp.data
        assert b'<input type="datetime-local"' not in resp.data

    def test_non_book_shows_datetime_inputs(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id, category=ResourceCategory.equipment)
        _login(client, active_user)
        resp = client.get(f"/resources/{r.id}/book")
        assert resp.status_code == 200
        assert b'<input type="datetime-local"' in resp.data
        assert b'<input type="date"' not in resp.data


# ---------------------------------------------------------------------------
# Create booking  POST /resources/<id>/book
# ---------------------------------------------------------------------------

class TestBookingCreate:
    def test_invalid_dates_shows_error(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id, category=ResourceCategory.book)
        _login(client, active_user)
        resp = client.post(
            f"/resources/{r.id}/book",
            data={"checkout_date": "not-a-date", "return_date": "also-bad"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Invalid date" in resp.data

    def test_invalid_datetimes_shows_error(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id, category=ResourceCategory.equipment)
        _login(client, active_user)
        resp = client.post(
            f"/resources/{r.id}/book",
            data={"start_datetime": "bad", "end_datetime": "bad"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Invalid" in resp.data

    def test_end_before_start_shows_error(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id, category=ResourceCategory.equipment)
        _login(client, active_user)
        resp = client.post(
            f"/resources/{r.id}/book",
            data={
                "start_datetime": f"{MONDAY}T14:00",
                "end_datetime": f"{MONDAY}T12:00",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"End must be after start" in resp.data

    def test_weekend_booking_rejected_when_no_weekend_window(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id, weekend_start=None, weekend_end=None)
        _login(client, active_user)
        resp = client.post(
            f"/resources/{r.id}/book",
            data={
                "start_datetime": f"{SATURDAY}T10:00",
                "end_datetime": f"{SATURDAY}T11:00",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"not available on weekends" in resp.data

    def test_time_outside_weekday_window_start(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id, weekday_start=time(9, 0), weekday_end=time(18, 0))
        _login(client, active_user)
        resp = client.post(
            f"/resources/{r.id}/book",
            data={
                "start_datetime": f"{MONDAY}T07:00",
                "end_datetime": f"{MONDAY}T10:00",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"availability window" in resp.data

    def test_time_outside_weekday_window_end(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id, weekday_start=time(9, 0), weekday_end=time(18, 0))
        _login(client, active_user)
        resp = client.post(
            f"/resources/{r.id}/book",
            data={
                "start_datetime": f"{MONDAY}T16:00",
                "end_datetime": f"{MONDAY}T20:00",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"availability window" in resp.data

    def test_conflict_shows_error(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id)
        _make_booking(
            db, active_user, r,
            starts_at=_utc(2026, 5, 25, 10, 0),
            ends_at=_utc(2026, 5, 25, 12, 0),
        )
        _login(client, active_user)
        resp = client.post(
            f"/resources/{r.id}/book",
            data={
                "start_datetime": f"{MONDAY}T11:00",
                "end_datetime": f"{MONDAY}T13:00",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"already booked" in resp.data

    def test_cancelled_booking_not_a_conflict(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id)
        _make_booking(
            db, active_user, r,
            starts_at=_utc(2026, 5, 25, 10, 0),
            ends_at=_utc(2026, 5, 25, 12, 0),
            status=BookingStatus.cancelled_by_member,
        )
        _login(client, active_user)
        resp = client.post(
            f"/resources/{r.id}/book",
            data={
                "start_datetime": f"{MONDAY}T10:00",
                "end_datetime": f"{MONDAY}T12:00",
            },
        )
        assert resp.status_code == 302
        assert "/my-bookings" in resp.headers["Location"]
        count = _db.session.execute(
            _db.select(Booking).where(Booking.status == BookingStatus.active)
        ).scalars().all()
        assert len(count) == 1

    def test_valid_booking_created(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id)
        _login(client, active_user)
        resp = client.post(
            f"/resources/{r.id}/book",
            data={
                "start_datetime": f"{MONDAY}T10:00",
                "end_datetime": f"{MONDAY}T12:00",
            },
        )
        assert resp.status_code == 302
        assert "/my-bookings" in resp.headers["Location"]
        booking = _db.session.execute(_db.select(Booking)).scalar_one()
        assert booking.resource_id == r.id
        assert booking.user_id == active_user.id
        assert booking.status == BookingStatus.active
        assert booking.starts_at == _utc(2026, 5, 25, 10, 0)
        assert booking.ends_at == _utc(2026, 5, 25, 12, 0)

    def test_book_category_booking_created(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id, category=ResourceCategory.book)
        _login(client, active_user)
        checkout = date(2026, 5, 25)
        return_d = date(2026, 5, 27)
        resp = client.post(
            f"/resources/{r.id}/book",
            data={"checkout_date": str(checkout), "return_date": str(return_d)},
        )
        assert resp.status_code == 302
        booking = _db.session.execute(_db.select(Booking)).scalar_one()
        assert booking.starts_at == _utc(2026, 5, 25, 0, 0)
        assert booking.ends_at.hour == 23
        assert booking.ends_at.minute == 59

    def test_weekend_booking_with_weekend_window(self, client, db, active_user):
        r = _make_resource(
            db, active_user.tenant_id,
            weekday_start=time(9, 0), weekday_end=time(18, 0),
            weekend_start=time(10, 0), weekend_end=time(16, 0),
        )
        _login(client, active_user)
        resp = client.post(
            f"/resources/{r.id}/book",
            data={
                "start_datetime": f"{SATURDAY}T11:00",
                "end_datetime": f"{SATURDAY}T13:00",
            },
        )
        assert resp.status_code == 302
        assert "/my-bookings" in resp.headers["Location"]

    def test_adjacent_booking_not_a_conflict(self, client, db, active_user):
        """A new slot that starts exactly when an existing one ends is not a conflict."""
        r = _make_resource(db, active_user.tenant_id)
        _make_booking(
            db, active_user, r,
            starts_at=_utc(2026, 5, 25, 10, 0),
            ends_at=_utc(2026, 5, 25, 12, 0),
        )
        _login(client, active_user)
        resp = client.post(
            f"/resources/{r.id}/book",
            data={
                "start_datetime": f"{MONDAY}T12:00",
                "end_datetime": f"{MONDAY}T14:00",
            },
        )
        assert resp.status_code == 302
        assert "/my-bookings" in resp.headers["Location"]

    def test_post_404_for_archived_resource(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id, is_archived=True)
        _login(client, active_user)
        resp = client.post(
            f"/resources/{r.id}/book",
            data={
                "start_datetime": f"{MONDAY}T10:00",
                "end_datetime": f"{MONDAY}T12:00",
            },
        )
        assert resp.status_code == 404

    def test_book_return_before_checkout_shows_error(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id, category=ResourceCategory.book)
        _login(client, active_user)
        resp = client.post(
            f"/resources/{r.id}/book",
            data={"checkout_date": "2026-05-27", "return_date": "2026-05-25"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"End must be after start" in resp.data


# ---------------------------------------------------------------------------
# My bookings  GET /my-bookings
# ---------------------------------------------------------------------------

class TestMyBookings:
    def test_shows_upcoming_booking(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id, name="Laser Cutter")
        future = datetime.now(timezone.utc) + timedelta(days=1)
        _make_booking(db, active_user, r,
                      starts_at=future,
                      ends_at=future + timedelta(hours=1))
        _login(client, active_user)
        resp = client.get("/my-bookings")
        assert resp.status_code == 200
        assert b"Laser Cutter" in resp.data
        assert b"Cancel" in resp.data

    def test_shows_past_booking_without_cancel(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id, name="Workbench B")
        past = _utc(2020, 1, 10, 10, 0)
        _make_booking(db, active_user, r,
                      starts_at=past, ends_at=past + timedelta(hours=1))
        _login(client, active_user)
        resp = client.get("/my-bookings")
        assert b"Workbench B" in resp.data
        # No Cancel button (heading "Past & Cancelled" contains "Cancel" as substring,
        # so check for the button text specifically)
        assert b">Cancel<" not in resp.data

    def test_shows_cancelled_booking_in_past(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id, name="3D Printer")
        future = datetime.now(timezone.utc) + timedelta(days=1)
        _make_booking(db, active_user, r,
                      starts_at=future,
                      ends_at=future + timedelta(hours=1),
                      status=BookingStatus.cancelled_by_member)
        _login(client, active_user)
        resp = client.get("/my-bookings")
        assert b"3D Printer" in resp.data
        assert b">Cancel<" not in resp.data  # no Cancel button for non-active booking

    def test_does_not_show_other_users_bookings(self, client, db, active_user):
        other = _make_other_user(db, active_user.tenant_id)
        r = _make_resource(db, active_user.tenant_id, name="Others Resource")
        future = datetime.now(timezone.utc) + timedelta(days=1)
        _make_booking(db, other, r,
                      starts_at=future, ends_at=future + timedelta(hours=1))
        _login(client, active_user)
        resp = client.get("/my-bookings")
        assert b"Others Resource" not in resp.data


# ---------------------------------------------------------------------------
# Cancel booking  POST /bookings/<id>/cancel
# ---------------------------------------------------------------------------

class TestCancelBooking:
    def test_cancel_another_users_booking(self, client, db, active_user):
        other = _make_other_user(db, active_user.tenant_id)
        r = _make_resource(db, active_user.tenant_id)
        future = datetime.now(timezone.utc) + timedelta(hours=3)
        b = _make_booking(db, other, r,
                          starts_at=future, ends_at=future + timedelta(hours=1))
        _login(client, active_user)
        resp = client.post(f"/bookings/{b.id}/cancel")
        assert resp.status_code == 302
        _db.session.refresh(b)
        assert b.status == BookingStatus.active  # unchanged

    def test_cancel_within_one_hour_rejected(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id)
        soon = datetime.now(timezone.utc) + timedelta(minutes=30)
        b = _make_booking(db, active_user, r,
                          starts_at=soon, ends_at=soon + timedelta(hours=1))
        _login(client, active_user)
        resp = client.post(f"/bookings/{b.id}/cancel", follow_redirects=True)
        assert resp.status_code == 200
        assert b"cutoff" in resp.data
        _db.session.refresh(b)
        assert b.status == BookingStatus.active

    def test_cancel_exactly_at_cutoff_rejected(self, client, db, active_user):
        """starts_at == now + 1h is at the boundary and must be rejected."""
        r = _make_resource(db, active_user.tenant_id)
        exactly_one_hour = datetime.now(timezone.utc) + timedelta(hours=1)
        b = _make_booking(db, active_user, r,
                          starts_at=exactly_one_hour,
                          ends_at=exactly_one_hour + timedelta(hours=1))
        _login(client, active_user)
        resp = client.post(f"/bookings/{b.id}/cancel", follow_redirects=True)
        assert b"cutoff" in resp.data
        _db.session.refresh(b)
        assert b.status == BookingStatus.active

    def test_cancel_success(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id)
        future = datetime.now(timezone.utc) + timedelta(hours=3)
        b = _make_booking(db, active_user, r,
                          starts_at=future, ends_at=future + timedelta(hours=1))
        _login(client, active_user)
        resp = client.post(f"/bookings/{b.id}/cancel")
        assert resp.status_code == 302
        assert "/my-bookings" in resp.headers["Location"]
        _db.session.refresh(b)
        assert b.status == BookingStatus.cancelled_by_member
        assert b.cancelled_at is not None
        assert b.cancelled_by_user_id == active_user.id

    def test_cancelled_booking_appears_in_past_section(self, client, db, active_user):
        r = _make_resource(db, active_user.tenant_id, name="Plottr")
        future = datetime.now(timezone.utc) + timedelta(hours=3)
        b = _make_booking(db, active_user, r,
                          starts_at=future, ends_at=future + timedelta(hours=1))
        _login(client, active_user)
        client.post(f"/bookings/{b.id}/cancel")
        resp = client.get("/my-bookings")
        assert b"Plottr" in resp.data
        # cancelled booking should not show Cancel button
        assert b">Cancel<" not in resp.data
