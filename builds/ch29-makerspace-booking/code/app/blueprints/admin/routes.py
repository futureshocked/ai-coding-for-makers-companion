import os
import uuid
from datetime import date, datetime, time, timezone
from functools import wraps

from flask import current_app, flash, g, redirect, render_template, request, url_for
from flask_login import current_user
from werkzeug.utils import secure_filename

from app.auth_decorators import admin_required, require_tenant
from app.blueprints.admin import bp
from app.blueprints.member.routes import AVATAR_OPTIONS
from app.extensions import db
from app.models import AuditEvent, Booking, BookingStatus, Resource, User, UserStatus
from app.models.resource import DEFAULT_WEEKDAY_END, DEFAULT_WEEKDAY_START, ResourceCategory
from app.scoping import get_for_tenant_or_404

bp.before_request(require_tenant)


def _log_audit(action: str, subject_type: str, subject_id=None, payload=None):
    """Append one audit event to the session (caller owns the commit)."""
    db.session.add(AuditEvent(
        tenant_id=g.tenant.id,
        actor_user_id=current_user.id,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        payload=payload or {},
    ))


# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------

@bp.get("")
@admin_required
def dashboard():
    return render_template("admin/dashboard.html")


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@bp.get("/audit-log")
@admin_required
def audit_log():
    page      = request.args.get("page", 1, type=int)
    action_f  = request.args.get("action", "").strip()
    subject_f = request.args.get("subject_type", "").strip()

    q = db.select(AuditEvent).where(AuditEvent.tenant_id == g.tenant.id).order_by(AuditEvent.created_at.desc())
    if action_f:
        q = q.where(AuditEvent.action == action_f)
    if subject_f:
        q = q.where(AuditEvent.subject_type == subject_f)

    pagination = db.paginate(q, page=page, per_page=50, error_out=False)
    return render_template(
        "admin/audit_log.html",
        pagination=pagination,
        action_f=action_f,
        subject_f=subject_f,
    )


# ---------------------------------------------------------------------------
# Resource list
# ---------------------------------------------------------------------------

@bp.get("/resources")
@admin_required
def resources_list():
    resources = db.session.execute(
        db.select(Resource)
        .where(Resource.tenant_id == g.tenant.id, Resource.is_archived == False)  # noqa: E712
        .order_by(Resource.name)
    ).scalars().all()
    return render_template("admin/resources_list.html", resources=resources)


# ---------------------------------------------------------------------------
# Add resource
# ---------------------------------------------------------------------------

@bp.route("/resources/new", methods=["GET", "POST"])
@admin_required
def resource_new():
    if request.method == "POST":
        resource, errors = _resource_from_form(None)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "admin/resource_form.html",
                resource=None,
                categories=ResourceCategory,
                form=request.form,
            )
        db.session.add(resource)
        db.session.flush()
        _log_audit("resource_created", "resource", resource.id,
                   {"name": resource.name, "category": resource.category.value})
        db.session.commit()
        flash(f'Resource "{resource.name}" added.', "success")
        return redirect(url_for("admin.resources_list"))

    return render_template(
        "admin/resource_form.html",
        resource=None,
        categories=ResourceCategory,
        form={},
    )


# ---------------------------------------------------------------------------
# Edit resource
# ---------------------------------------------------------------------------

@bp.route("/resources/<int:id>/edit", methods=["GET", "POST"])
@admin_required
def resource_edit(id: int):
    resource = get_for_tenant_or_404(Resource, id)

    if request.method == "POST":
        before = {
            "name": resource.name,
            "category": resource.category.value,
            "description": resource.description,
            "location": resource.location,
        }
        updated, errors = _resource_from_form(resource)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "admin/resource_form.html",
                resource=resource,
                categories=ResourceCategory,
                form=request.form,
            )
        after = {
            "name": updated.name,
            "category": updated.category.value,
            "description": updated.description,
            "location": updated.location,
        }
        _log_audit("resource_updated", "resource", updated.id,
                   {"before": before, "after": after})
        db.session.commit()
        flash(f'Resource "{updated.name}" updated.', "success")
        return redirect(url_for("admin.resources_list"))

    return render_template(
        "admin/resource_form.html",
        resource=resource,
        categories=ResourceCategory,
        form={},
    )


# ---------------------------------------------------------------------------
# Archive resource
# ---------------------------------------------------------------------------

@bp.post("/resources/<int:id>/archive")
@admin_required
def resource_archive(id: int):
    resource = get_for_tenant_or_404(Resource, id)
    resource.is_archived = True
    _log_audit("resource_deleted", "resource", resource.id, {"name": resource.name})
    db.session.commit()
    flash(f'Resource "{resource.name}" archived.', "info")
    return redirect(url_for("admin.resources_list"))


# ---------------------------------------------------------------------------
# Member list
# ---------------------------------------------------------------------------

@bp.get("/members")
@admin_required
def members_list():
    page     = request.args.get("page", 1, type=int)
    status_f = request.args.get("status", "").strip()

    q = db.select(User).where(User.tenant_id == g.tenant.id).order_by(User.created_at.desc())
    if status_f:
        try:
            q = q.where(User.status == UserStatus(status_f))
        except ValueError:
            status_f = ""

    pagination = db.paginate(q, page=page, per_page=25, error_out=False)
    return render_template(
        "admin/members_list.html",
        pagination=pagination,
        status_f=status_f,
        UserStatus=UserStatus,
    )


# ---------------------------------------------------------------------------
# Member actions
# ---------------------------------------------------------------------------

@bp.post("/members/<int:id>/approve")
@admin_required
def member_approve(id: int):
    member = get_for_tenant_or_404(User, id)
    if member.id == current_user.id:
        flash("You cannot change your own account status.", "error")
        return redirect(url_for("admin.members_list"))
    if member.status != UserStatus.pending:
        flash(f"{member.display_name} is not pending approval.", "error")
        return redirect(url_for("admin.members_list"))
    member.status = UserStatus.active
    member.approved_at = datetime.now(tz=timezone.utc)
    _log_audit("member_approved", "user", member.id,
               {"email": member.email, "display_name": member.display_name})
    db.session.commit()
    flash(f"{member.display_name} approved.", "success")
    return redirect(url_for("admin.members_list"))


@bp.route("/members/<int:id>/reject", methods=["GET", "POST"])
@admin_required
def member_reject(id: int):
    member = get_for_tenant_or_404(User, id)
    if member.id == current_user.id:
        flash("You cannot change your own account status.", "error")
        return redirect(url_for("admin.members_list"))
    if member.status not in (UserStatus.pending, UserStatus.active):
        flash(f"{member.display_name} cannot be rejected from their current status.", "error")
        return redirect(url_for("admin.members_list"))

    if request.method == "POST":
        note = request.form.get("note", "").strip()
        if not note:
            flash("A rejection reason is required.", "error")
            return render_template("admin/member_reject_form.html", member=member)
        member.status = UserStatus.rejected
        member.rejection_note = note
        _log_audit("member_rejected", "user", member.id,
                   {"email": member.email, "display_name": member.display_name, "note": note})
        db.session.commit()
        flash(f"{member.display_name} rejected.", "info")
        return redirect(url_for("admin.members_list"))

    return render_template("admin/member_reject_form.html", member=member)


@bp.post("/members/<int:id>/freeze")
@admin_required
def member_freeze(id: int):
    member = get_for_tenant_or_404(User, id)
    if member.id == current_user.id:
        flash("You cannot change your own account status.", "error")
        return redirect(url_for("admin.members_list"))
    if member.status != UserStatus.active:
        flash(f"{member.display_name} is not active.", "error")
        return redirect(url_for("admin.members_list"))
    member.status = UserStatus.frozen
    _log_audit("member_frozen", "user", member.id,
               {"email": member.email, "display_name": member.display_name})
    db.session.commit()
    flash(f"{member.display_name}'s account frozen.", "info")
    return redirect(url_for("admin.members_list"))


@bp.post("/members/<int:id>/unfreeze")
@admin_required
def member_unfreeze(id: int):
    member = get_for_tenant_or_404(User, id)
    if member.id == current_user.id:
        flash("You cannot change your own account status.", "error")
        return redirect(url_for("admin.members_list"))
    if member.status != UserStatus.frozen:
        flash(f"{member.display_name} is not frozen.", "error")
        return redirect(url_for("admin.members_list"))
    member.status = UserStatus.active
    member.rejection_note = None
    _log_audit("member_unfrozen", "user", member.id,
               {"email": member.email, "display_name": member.display_name})
    db.session.commit()
    flash(f"{member.display_name}'s account unfrozen.", "success")
    return redirect(url_for("admin.members_list"))


# ---------------------------------------------------------------------------
# Edit member account details
# ---------------------------------------------------------------------------

@bp.route("/members/<int:id>/edit", methods=["GET", "POST"])
@admin_required
def member_edit(id: int):
    member = get_for_tenant_or_404(User, id)
    is_self = member.id == current_user.id

    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        avatar = request.form.get("avatar", "")
        new_is_admin = request.form.get("is_admin") == "on"

        errors = []
        if not display_name:
            errors.append("Display name is required.")
        if not email:
            errors.append("Email is required.")
        else:
            conflict = db.session.execute(
                db.select(User).where(User.tenant_id == g.tenant.id, User.email == email, User.id != member.id)
            ).scalar_one_or_none()
            if conflict:
                errors.append("That email is already in use by another account.")
        if avatar and avatar not in AVATAR_OPTIONS:
            avatar = ""

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "admin/member_edit_form.html",
                member=member,
                avatar_options=AVATAR_OPTIONS,
                is_self=is_self,
                form={"display_name": display_name, "email": email, "avatar": avatar},
            )

        before = {
            "display_name": member.display_name,
            "email": member.email,
            "avatar": member.avatar,
            "is_admin": member.is_admin,
        }
        member.display_name = display_name
        member.email = email
        member.avatar = avatar or None
        if not is_self:
            member.is_admin = new_is_admin
        after = {
            "display_name": member.display_name,
            "email": member.email,
            "avatar": member.avatar,
            "is_admin": member.is_admin,
        }
        _log_audit("member_updated", "user", member.id, {"before": before, "after": after})
        db.session.commit()
        flash(f"{member.display_name} updated.", "success")
        return redirect(url_for("admin.members_list"))

    return render_template(
        "admin/member_edit_form.html",
        member=member,
        avatar_options=AVATAR_OPTIONS,
        is_self=is_self,
        form={
            "display_name": member.display_name,
            "email": member.email,
            "avatar": member.avatar or "",
        },
    )


# ---------------------------------------------------------------------------
# Bookings list
# ---------------------------------------------------------------------------

@bp.get("/bookings")
@admin_required
def bookings_list():
    page     = request.args.get("page", 1, type=int)
    status_f = request.args.get("status", "").strip()

    q = db.select(Booking).where(Booking.tenant_id == g.tenant.id).order_by(Booking.starts_at.desc())
    if status_f:
        try:
            q = q.where(Booking.status == BookingStatus(status_f))
        except ValueError:
            status_f = ""

    pagination = db.paginate(q, page=page, per_page=25, error_out=False)
    return render_template(
        "admin/bookings_list.html",
        pagination=pagination,
        status_f=status_f,
        BookingStatus=BookingStatus,
    )


# ---------------------------------------------------------------------------
# Edit booking (admin — no member restrictions)
# ---------------------------------------------------------------------------

@bp.route("/bookings/<int:id>/edit", methods=["GET", "POST"])
@admin_required
def booking_edit(id: int):
    UTC = timezone.utc
    booking = get_for_tenant_or_404(Booking, id)
    resource = booking.resource
    is_book = resource.category.value == "book"

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
            "admin/booking_edit_form.html",
            booking=booking,
            resource=resource,
            is_book=is_book,
            form=form,
        )

    # POST — parse submitted times
    errors = []
    new_starts_at = new_ends_at = None

    if is_book:
        checkout_raw = request.form.get("checkout_date", "").strip()
        return_raw = request.form.get("return_date", "").strip()
        try:
            new_starts_at = datetime.combine(date.fromisoformat(checkout_raw), time(0, 0), tzinfo=UTC)
        except ValueError:
            errors.append("Invalid checkout date.")
        try:
            new_ends_at = datetime.combine(date.fromisoformat(return_raw), time(23, 59), tzinfo=UTC)
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

    if not errors and new_ends_at <= new_starts_at:
        errors.append("End must be after start.")

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
            errors.append(
                f"Conflicts with another active booking from "
                f"{conflict.starts_at.strftime('%Y-%m-%d %H:%M')} to "
                f"{conflict.ends_at.strftime('%Y-%m-%d %H:%M')}."
            )

    if errors:
        for e in errors:
            flash(e, "error")
        return render_template(
            "admin/booking_edit_form.html",
            booking=booking,
            resource=resource,
            is_book=is_book,
            form=request.form,
        )

    before = {
        "starts_at": booking.starts_at.isoformat(),
        "ends_at": booking.ends_at.isoformat(),
        "comment": booking.comment,
    }
    booking.starts_at = new_starts_at
    booking.ends_at = new_ends_at
    booking.comment = comment
    after = {
        "starts_at": booking.starts_at.isoformat(),
        "ends_at": booking.ends_at.isoformat(),
        "comment": booking.comment,
    }
    _log_audit("booking_updated", "booking", booking.id, {
        "member": booking.user.email,
        "resource": resource.name,
        "before": before,
        "after": after,
    })
    db.session.commit()
    flash("Booking updated.", "success")
    return redirect(url_for("admin.bookings_list"))


# ---------------------------------------------------------------------------
# Cancel booking (admin)
# ---------------------------------------------------------------------------

@bp.post("/bookings/<int:id>/cancel")
@admin_required
def booking_cancel(id: int):
    booking = get_for_tenant_or_404(Booking, id)
    if booking.status != BookingStatus.active:
        flash("Only active bookings can be cancelled.", "error")
        return redirect(url_for("admin.bookings_list"))
    now = datetime.now(timezone.utc)
    booking.status = BookingStatus.cancelled_by_admin
    booking.cancelled_at = now
    booking.cancelled_by_user_id = current_user.id
    _log_audit("booking_cancelled", "booking", booking.id, {
        "member": booking.user.email,
        "resource": booking.resource.name,
        "starts_at": booking.starts_at.isoformat(),
        "cancelled_by": "admin",
    })
    db.session.commit()
    flash("Booking cancelled.", "info")
    return redirect(url_for("admin.bookings_list"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_time(value: str):
    """Return a time object from HH:MM string, or None if blank/invalid."""
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None


_ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}


def _save_thumbnail(file) -> str | None:
    """Validate and save an uploaded image file; return the stored filename or None."""
    if not file or not file.filename:
        return None
    ext = secure_filename(file.filename).rsplit(".", 1)[-1].lower()
    if ext not in _ALLOWED_IMAGE_EXTENSIONS:
        return None
    filename = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, filename))
    return filename


def _delete_thumbnail(filename: str | None) -> None:
    """Delete a stored thumbnail file if it exists."""
    if not filename:
        return
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    try:
        os.remove(path)
    except OSError:
        pass


def _resource_from_form(existing: Resource | None):
    """Validate form data and return (resource, errors).

    If *existing* is None a new Resource is created; otherwise *existing* is
    mutated in-place so SQLAlchemy tracks the changes automatically.
    """
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip() or None
    location = request.form.get("location", "").strip() or None
    category_raw = request.form.get("category", "")
    weekday_start = _parse_time(request.form.get("weekday_start", "")) or DEFAULT_WEEKDAY_START
    weekday_end   = _parse_time(request.form.get("weekday_end",   "")) or DEFAULT_WEEKDAY_END
    weekend_start = _parse_time(request.form.get("weekend_start", ""))
    weekend_end   = _parse_time(request.form.get("weekend_end",   ""))
    remove_thumbnail = bool(request.form.get("remove_thumbnail"))
    uploaded_file = request.files.get("thumbnail")

    errors = []
    if not name:
        errors.append("Name is required.")

    try:
        category = ResourceCategory(category_raw)
    except ValueError:
        category = None
        errors.append("Please select a valid category.")

    if bool(weekend_start) != bool(weekend_end):
        errors.append("Both weekend start and end must be set, or both left blank.")

    new_thumbnail = _save_thumbnail(uploaded_file)
    if uploaded_file and uploaded_file.filename and new_thumbnail is None:
        errors.append("Thumbnail must be a JPG, PNG, GIF, or WebP image (max 4 MB).")

    if errors:
        return existing, errors

    if existing is None:
        resource = Resource(
            tenant_id=g.tenant.id,
            name=name,
            description=description,
            location=location,
            category=category,
            weekday_start=weekday_start,
            weekday_end=weekday_end,
            weekend_start=weekend_start,
            weekend_end=weekend_end,
            thumbnail=new_thumbnail,
        )
    else:
        existing.name = name
        existing.description = description
        existing.location = location
        existing.category = category
        existing.weekday_start = weekday_start
        existing.weekday_end   = weekday_end
        existing.weekend_start = weekend_start
        existing.weekend_end   = weekend_end
        if new_thumbnail:
            _delete_thumbnail(existing.thumbnail)
            existing.thumbnail = new_thumbnail
        elif remove_thumbnail:
            _delete_thumbnail(existing.thumbnail)
            existing.thumbnail = None
        resource = existing

    return resource, []
