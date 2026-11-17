from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db as _db
from app.models.booking import Booking, BookingStatus
from app.models.notification import NotificationLog, NotificationStatus
from app.models.resource import Resource, ResourceCategory, ResourceState
from app.models.user import User, UserStatus
from app.services.reminders import REMINDER_TYPE, send_due_reminders

UTC = timezone.utc
NOW = datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(tenant_id, email="member@example.com"):
    u = User(
        tenant_id=tenant_id,
        email=email,
        password_hash=generate_password_hash("pw"),
        display_name="Test Member",
        status=UserStatus.active,
        is_admin=False,
        notification_prefs={},
    )
    _db.session.add(u)
    _db.session.commit()
    return u


def _make_resource(tenant_id):
    r = Resource(
        tenant_id=tenant_id,
        name="Laser Cutter",
        category=ResourceCategory.equipment,
        location="Workshop A",
        is_archived=False,
        state=ResourceState.available,
    )
    _db.session.add(r)
    _db.session.commit()
    return r


def _make_booking(user, resource, starts_at, ends_at, status=BookingStatus.active):
    b = Booking(
        tenant_id=user.tenant_id,
        user_id=user.id,
        resource_id=resource.id,
        starts_at=starts_at,
        ends_at=ends_at,
        status=status,
        original_starts_at=starts_at,
        original_ends_at=ends_at,
    )
    _db.session.add(b)
    _db.session.commit()
    return b


def _run_job(app, fake_now=NOW):
    with patch("app.services.reminders.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        with patch("app.services.reminders.send_booking_reminder", return_value="msg-123") as mock_send:
            send_due_reminders(app)
    return mock_send


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSendDueReminders:

    def test_sends_reminder_for_eligible_booking(self, app, tenant):
        user = _make_user(tenant.id)
        resource = _make_resource(tenant.id)
        starts_at = NOW + timedelta(hours=12)
        booking = _make_booking(user, resource, starts_at, starts_at + timedelta(hours=1))

        mock_send = _run_job(app)

        assert mock_send.call_count == 1
        log = _db.session.execute(
            _db.select(NotificationLog).filter_by(booking_id=booking.id, type=REMINDER_TYPE)
        ).scalar_one()
        assert log.status == NotificationStatus.sent
        assert log.provider_message_id == "msg-123"
        assert log.user_id == user.id

    def test_skips_already_sent_booking(self, app, tenant):
        user = _make_user(tenant.id)
        resource = _make_resource(tenant.id)
        starts_at = NOW + timedelta(hours=12)
        booking = _make_booking(user, resource, starts_at, starts_at + timedelta(hours=1))

        existing_log = NotificationLog(
            tenant_id=tenant.id,
            user_id=user.id,
            booking_id=booking.id,
            type=REMINDER_TYPE,
            sent_at=NOW - timedelta(hours=1),
            status=NotificationStatus.sent,
        )
        _db.session.add(existing_log)
        _db.session.commit()

        mock_send = _run_job(app)

        assert mock_send.call_count == 0
        count = _db.session.execute(
            _db.select(NotificationLog).filter_by(booking_id=booking.id, type=REMINDER_TYPE)
        ).all()
        assert len(count) == 1

    def test_skips_booking_outside_window(self, app, tenant):
        user = _make_user(tenant.id)
        resource = _make_resource(tenant.id)
        starts_at = NOW + timedelta(hours=48)
        _make_booking(user, resource, starts_at, starts_at + timedelta(hours=1))

        mock_send = _run_job(app)

        assert mock_send.call_count == 0
        logs = _db.session.execute(_db.select(NotificationLog)).scalars().all()
        assert len(logs) == 0

    def test_skips_cancelled_booking(self, app, tenant):
        user = _make_user(tenant.id)
        resource = _make_resource(tenant.id)
        starts_at = NOW + timedelta(hours=12)
        _make_booking(
            user, resource, starts_at, starts_at + timedelta(hours=1),
            status=BookingStatus.cancelled_by_member,
        )

        mock_send = _run_job(app)

        assert mock_send.call_count == 0

    def test_logs_failed_status_when_resend_raises(self, app, tenant):
        user = _make_user(tenant.id)
        resource = _make_resource(tenant.id)
        starts_at = NOW + timedelta(hours=12)
        booking = _make_booking(user, resource, starts_at, starts_at + timedelta(hours=1))

        with patch("app.services.reminders.datetime") as mock_dt:
            mock_dt.now.return_value = NOW
            with patch(
                "app.services.reminders.send_booking_reminder",
                side_effect=Exception("Resend API error"),
            ):
                send_due_reminders(app)

        log = _db.session.execute(
            _db.select(NotificationLog).filter_by(booking_id=booking.id, type=REMINDER_TYPE)
        ).scalar_one()
        assert log.status == NotificationStatus.failed
        assert log.provider_message_id is None

    def test_sends_only_within_window(self, app, tenant):
        user = _make_user(tenant.id)
        resource = _make_resource(tenant.id)
        starts_inside = NOW + timedelta(hours=12)
        starts_outside = NOW + timedelta(hours=48)
        b_inside = _make_booking(user, resource, starts_inside, starts_inside + timedelta(hours=1))
        b_inside_id = b_inside.id
        _make_booking(
            _make_user(tenant.id, "member2@example.com"), resource,
            starts_outside, starts_outside + timedelta(hours=1),
        )

        mock_send = _run_job(app)

        assert mock_send.call_count == 1
        log = _db.session.execute(
            _db.select(NotificationLog).filter_by(type=REMINDER_TYPE, status=NotificationStatus.sent)
        ).scalar_one()
        assert log.booking_id == b_inside_id
