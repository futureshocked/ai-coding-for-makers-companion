from datetime import date, datetime, time, timedelta, timezone

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from flask_login import current_user

from app.auth_decorators import member_required, require_tenant
from app.extensions import db
from app.models import Booking, Resource
from app.models.booking import BookingStatus
from app.models.resource import ResourceCategory
from app.models.user import UserStatus
from app.scoping import get_for_tenant_or_404

bp = Blueprint("bookings", __name__)
bp.before_request(require_tenant)

UTC = timezone.utc
EDIT_GRACE_MINUTES = 60


# ---------------------------------------------------------------------------
# Booking form
# ---------------------------------------------------------------------------

@bp.get("/resources/<int:id>/book")
@member_required
def booking_form(id: int):
    resource = get_for_tenant_or_404(Resource, id)
    if resource.is_archived:
        abort(404)
    is_book = resource.category == ResourceCategory.book
    return render_template(
        "bookings/book_form.html",
        resource=resource,
        is_book=is_book,
        form={},
    )


# ---------------------------------------------------------------------------
# Create booking
# ---------------------------------------------------------------------------

@bp.post("/resources/<int:id>/book")
@member_required
def booking_create(id: int):
    resource = get_for_tenant_or_404(Resource, id)
    if resource.is_archived:
        abort(404)
    is_book = resource.category == ResourceCategory.book

    errors = []
    starts_at = ends_at = None

    if is_book:
        checkout_raw = request.form.get("checkout_date", "").strip()
        return_raw = request.form.get("return_date", "").strip()
        try:
            checkout_date = date.fromisoformat(checkout_raw)
            return_date = date.fromisoformat(return_raw)
            starts_at = datetime.combine(checkout_date, time(0, 0), tzinfo=UTC)
            ends_at = datetime.combine(return_date, time(23, 59), tzinfo=UTC)
        except ValueError:
            errors.append("Invalid date. Please use the date picker.")
    else:
        start_raw = request.form.get("start_datetime", "").strip()
        end_raw = request.form.get("end_datetime", "").strip()
        try:
            starts_at = datetime.strptime(start_raw, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
        except ValueError:
            errors.append("Invalid start date/time.")
        try:
            ends_at = datetime.strptime(end_raw, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
        except ValueError:
            errors.append("Invalid end date/time.")

    if starts_at and ends_at:
        if ends_at <= starts_at:
            errors.append("End must be after start.")

        is_weekend = starts_at.weekday() >= 5

        if is_weekend and resource.weekend_start is None:
            errors.append(
                f'"{resource.name}" is not available on weekends.'
            )
        elif not is_book:
            window_start = resource.weekend_start if is_weekend else resource.weekday_start
            window_end = resource.weekend_end if is_weekend else resource.weekday_end
            if starts_at.time() < window_start or ends_at.time() > window_end:
                errors.append(
                    f"Booking must be within availability window "
                    f"{window_start.strftime('%H:%M')}–{window_end.strftime('%H:%M')}."
                )

    if errors:
        for e in errors:
            flash(e, "error")
        return render_template(
            "bookings/book_form.html",
            resource=resource,
            is_book=is_book,
            form=request.form,
        )

    if starts_at and not request.form.get("holiday_acknowledged"):
        from app.services.holidays import is_public_holiday
        holiday_name = is_public_holiday(starts_at.date())
        if holiday_name:
            flash(
                f"{starts_at.date().strftime('%A, %d %B %Y')} is a public holiday"
                f" ({holiday_name}). You can still make this booking.",
                "warning",
            )
            return render_template(
                "bookings/book_form.html",
                resource=resource,
                is_book=is_book,
                form=request.form,
                holiday_acknowledged=True,
            )

    conflict = db.session.execute(
        db.select(Booking).where(
            Booking.tenant_id == g.tenant.id,
            Booking.resource_id == resource.id,
            Booking.status == BookingStatus.active,
            Booking.starts_at < ends_at,
            Booking.ends_at > starts_at,
        )
    ).scalar_one_or_none()

    if conflict:
        flash(
            f"This resource is already booked from "
            f"{conflict.starts_at.strftime('%Y-%m-%d %H:%M')} to "
            f"{conflict.ends_at.strftime('%Y-%m-%d %H:%M')}.",
            "error",
        )
        return render_template(
            "bookings/book_form.html",
            resource=resource,
            is_book=is_book,
            form=request.form,
        )

    booking = Booking(
        tenant_id=g.tenant.id,
        user_id=current_user.id,
        resource_id=resource.id,
        starts_at=starts_at,
        ends_at=ends_at,
        status=BookingStatus.active,
        original_starts_at=starts_at,
        original_ends_at=ends_at,
    )
    db.session.add(booking)
    db.session.commit()
    flash(f'Booking confirmed for "{resource.name}".', "success")
    return redirect(url_for("bookings.my_bookings"))


# ---------------------------------------------------------------------------
# Member booking list
# ---------------------------------------------------------------------------

@bp.get("/my-bookings")
@member_required
def my_bookings():
    now = datetime.now(UTC)
    all_bookings = db.session.execute(
        db.select(Booking)
        .where(Booking.user_id == current_user.id)
        .order_by(Booking.starts_at.desc())
    ).scalars().all()
    upcoming = [b for b in all_bookings if b.starts_at > now and b.status == BookingStatus.active]
    past = [b for b in all_bookings if b not in upcoming]
    return render_template("bookings/my_bookings.html", upcoming=upcoming, past=past)


# ---------------------------------------------------------------------------
# Cancel booking
# ---------------------------------------------------------------------------

@bp.post("/bookings/<int:id>/cancel")
@member_required
def booking_cancel(id: int):
    booking = get_for_tenant_or_404(Booking, id)
    if booking.user_id != current_user.id:
        flash("You can only cancel your own bookings.", "error")
        return redirect(url_for("bookings.my_bookings"))

    now = datetime.now(UTC)
    if booking.starts_at <= now + timedelta(hours=1):
        flash("Cancellation cutoff has passed (must cancel more than 1 hour before start).", "error")
        return redirect(url_for("bookings.my_bookings"))

    booking.status = BookingStatus.cancelled_by_member
    booking.cancelled_at = now
    booking.cancelled_by_user_id = current_user.id
    db.session.commit()
    flash("Booking cancelled.", "info")
    return redirect(url_for("bookings.my_bookings"))


# ---------------------------------------------------------------------------
# Edit booking
# ---------------------------------------------------------------------------

@bp.route("/bookings/<int:id>/edit", methods=["GET", "POST"])
@member_required
def booking_edit(id: int):
    booking = get_for_tenant_or_404(Booking, id)

    if booking.user_id != current_user.id:
        flash("You can only edit your own bookings.", "error")
        return redirect(url_for("bookings.my_bookings"))

    if booking.status != BookingStatus.active:
        flash("Only active bookings can be edited.", "error")
        return redirect(url_for("bookings.my_bookings"))

    now = datetime.now(UTC)
    if booking.starts_at <= now:
        flash("Only upcoming bookings can be edited.", "error")
        return redirect(url_for("bookings.my_bookings"))

    resource = booking.resource
    is_book = resource.category == ResourceCategory.book
    edits_remaining = 2 - booking.edit_count

    if request.method == "GET":
        if is_book:
            form = {
                "checkout_date": booking.starts_at.strftime("%Y-%m-%d"),
                "return_date": booking.ends_at.strftime("%Y-%m-%d"),
                "comment": booking.comment or "",
            }
        else:
            form = {
                "start_datetime": booking.starts_at.strftime("%Y-%m-%dT%H:%M"),
                "end_datetime": booking.ends_at.strftime("%Y-%m-%dT%H:%M"),
                "comment": booking.comment or "",
            }
        return render_template(
            "bookings/booking_edit_form.html",
            booking=booking,
            resource=resource,
            is_book=is_book,
            form=form,
            edits_remaining=edits_remaining,
        )

    # POST — parse submitted times
    errors = []
    new_starts_at = new_ends_at = None

    if is_book:
        checkout_raw = request.form.get("checkout_date", "").strip()
        return_raw = request.form.get("return_date", "").strip()
        try:
            checkout_date = date.fromisoformat(checkout_raw)
            new_starts_at = datetime.combine(checkout_date, time(0, 0), tzinfo=UTC)
        except ValueError:
            errors.append("Invalid checkout date.")
        try:
            return_date = date.fromisoformat(return_raw)
            new_ends_at = datetime.combine(return_date, time(23, 59), tzinfo=UTC)
        except ValueError:
            errors.append("Invalid return date.")
    else:
        start_raw = request.form.get("start_datetime", "").strip()
        end_raw = request.form.get("end_datetime", "").strip()
        try:
            new_starts_at = datetime.strptime(start_raw, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
        except ValueError:
            errors.append("Invalid start date/time.")
        try:
            new_ends_at = datetime.strptime(end_raw, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
        except ValueError:
            errors.append("Invalid end date/time.")

    comment = request.form.get("comment", "").strip() or None

    if errors:
        for e in errors:
            flash(e, "error")
        return render_template(
            "bookings/booking_edit_form.html",
            booking=booking,
            resource=resource,
            is_book=is_book,
            form=request.form,
            edits_remaining=edits_remaining,
        )

    time_changed = (new_starts_at != booking.starts_at or new_ends_at != booking.ends_at)

    if time_changed:
        if new_ends_at <= new_starts_at:
            errors.append("End must be after start.")
        elif booking.edit_count >= 2:
            errors.append("You've already edited this booking twice.")
        else:
            grace_seconds = EDIT_GRACE_MINUTES * 60
            if abs((new_starts_at - booking.starts_at).total_seconds()) > grace_seconds:
                errors.append(
                    f"Edits must stay within {EDIT_GRACE_MINUTES} minutes of the current start time."
                )

            if not errors:
                is_weekend = new_starts_at.weekday() >= 5
                if is_weekend and resource.weekend_start is None:
                    errors.append(f'"{resource.name}" is not available on weekends.')
                elif not is_book:
                    window_start = resource.weekend_start if is_weekend else resource.weekday_start
                    window_end = resource.weekend_end if is_weekend else resource.weekday_end
                    if new_starts_at.time() < window_start or new_ends_at.time() > window_end:
                        errors.append(
                            f"Booking must be within availability window "
                            f"{window_start.strftime('%H:%M')}–{window_end.strftime('%H:%M')}."
                        )

            if not errors:
                conflict = db.session.execute(
                    db.select(Booking).where(
                        Booking.tenant_id == g.tenant.id,
                        Booking.resource_id == resource.id,
                        Booking.status == BookingStatus.active,
                        Booking.starts_at < new_ends_at,
                        Booking.ends_at > new_starts_at,
                        Booking.id != booking.id,
                    )
                ).scalar_one_or_none()
                if conflict:
                    flash(
                        f"This resource is already booked from "
                        f"{conflict.starts_at.strftime('%Y-%m-%d %H:%M')} to "
                        f"{conflict.ends_at.strftime('%Y-%m-%d %H:%M')}.",
                        "error",
                    )
                    return render_template(
                        "bookings/booking_edit_form.html",
                        booking=booking,
                        resource=resource,
                        is_book=is_book,
                        form=request.form,
                        edits_remaining=edits_remaining,
                    )

    if errors:
        for e in errors:
            flash(e, "error")
        return render_template(
            "bookings/booking_edit_form.html",
            booking=booking,
            resource=resource,
            is_book=is_book,
            form=request.form,
            edits_remaining=edits_remaining,
        )

    if time_changed:
        booking.starts_at = new_starts_at
        booking.ends_at = new_ends_at
        booking.edit_count += 1
    booking.comment = comment
    db.session.commit()
    flash("Booking updated.", "success")
    return redirect(url_for("bookings.my_bookings"))
