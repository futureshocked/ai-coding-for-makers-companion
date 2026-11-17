from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.booking import Booking, BookingStatus
from app.models.notification import NotificationLog, NotificationStatus
from app.services.email import send_booking_reminder

REMINDER_TYPE = "booking_reminder"


def send_due_reminders(app):
    with app.app_context():
        hours_before = app.config["REMINDER_HOURS_BEFORE"]
        now = datetime.now(timezone.utc)
        window_end = now + timedelta(hours=hours_before)

        due = (
            db.session.execute(
                db.select(Booking).filter(
                    Booking.status == BookingStatus.active,
                    Booking.starts_at > now,
                    Booking.starts_at <= window_end,
                )
            )
            .scalars()
            .all()
        )

        for booking in due:
            already = db.session.execute(
                db.select(NotificationLog).filter_by(
                    booking_id=booking.id,
                    type=REMINDER_TYPE,
                    status=NotificationStatus.sent,
                )
            ).scalar_one_or_none()
            if already:
                continue

            manage_url = (
                f"https://{booking.user.tenant.subdomain}"
                f".{app.config['APEX_HOST']}/my-bookings"
            )
            status = NotificationStatus.failed
            provider_id = None
            try:
                provider_id = send_booking_reminder(booking, manage_url)
                status = NotificationStatus.sent
            except Exception:
                pass

            db.session.add(
                NotificationLog(
                    user_id=booking.user_id,
                    booking_id=booking.id,
                    tenant_id=booking.tenant_id,
                    type=REMINDER_TYPE,
                    sent_at=datetime.now(timezone.utc),
                    status=status,
                    provider_message_id=provider_id,
                )
            )
            db.session.commit()
