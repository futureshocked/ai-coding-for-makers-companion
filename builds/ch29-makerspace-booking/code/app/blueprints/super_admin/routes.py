from datetime import datetime, timezone

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import func
from werkzeug.security import check_password_hash

from app.auth_decorators import super_admin_required
from app.blueprints.super_admin import bp
from app.extensions import db
from app.models import AuditEvent, Booking, Resource, Tenant, User
from app.models.booking import BookingStatus
from app.models.tenant import TenantStatus
from app.models.user import UserStatus
from app.services.email import send_tenant_approval, send_tenant_rejection
from app.services.tenants import activate_tenant


def _log_super_audit(action: str, subject_type: str, subject_id=None, payload=None):
    db.session.add(AuditEvent(
        tenant_id=None,
        actor_user_id=current_user.id,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        payload=payload or {},
    ))


def _first_admin_email(tenant: Tenant) -> str | None:
    user = db.session.scalar(
        db.select(User).where(
            User.tenant_id == tenant.id,
            User.is_admin == True,  # noqa: E712
        )
    )
    return user.email if user else None


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------

@bp.route("/super/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated and current_user.is_super_admin:
        return redirect(url_for("super_admin.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = db.session.scalar(
            db.select(User).where(
                User.tenant_id == None,  # noqa: E711
                User.is_super_admin == True,  # noqa: E712
                func.lower(User.email) == email,
            )
        )
        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid email or password.", "error")
            return render_template("super_admin/login.html")

        login_user(user, remember=True)
        return redirect(url_for("super_admin.dashboard"))

    return render_template("super_admin/login.html")


@bp.post("/super/logout")
@super_admin_required
def logout():
    logout_user()
    return redirect(url_for("super_admin.login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@bp.get("/super/")
@super_admin_required
def dashboard():
    member_count_sq = (
        db.select(func.count(User.id))
        .where(User.tenant_id == Tenant.id)
        .correlate(Tenant)
        .scalar_subquery()
    )
    rows = db.session.execute(
        db.select(Tenant, member_count_sq.label("member_count"))
        .order_by(
            db.case(
                (Tenant.status == TenantStatus.pending, 0),
                (Tenant.status == TenantStatus.active, 1),
                else_=2,
            ),
            Tenant.created_at.desc(),
        )
    ).all()
    tenants = [{"tenant": r.Tenant, "member_count": r.member_count} for r in rows]
    return render_template("super_admin/dashboard.html", tenants=tenants)


# ---------------------------------------------------------------------------
# Tenant lifecycle actions
# ---------------------------------------------------------------------------

@bp.post("/super/tenants/<int:tenant_id>/approve")
@super_admin_required
def approve_tenant(tenant_id: int):
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        flash("Tenant not found.", "error")
        return redirect(url_for("super_admin.dashboard"))

    if tenant.status != TenantStatus.pending:
        flash(f"Tenant '{tenant.name}' is not pending.", "error")
        return redirect(url_for("super_admin.dashboard"))

    activate_tenant(tenant)

    admin_email = _first_admin_email(tenant)
    if admin_email:
        apex = current_app.config["APEX_HOST"]
        login_url = f"https://{tenant.subdomain}.{apex}/auth/login"
        try:
            send_tenant_approval(admin_email, tenant.name, login_url)
        except Exception:
            current_app.logger.exception(
                "Failed to send approval email for tenant %s", tenant.id
            )

    _log_super_audit("tenant_approved", "tenant", tenant.id, {"subdomain": tenant.subdomain})
    db.session.commit()

    flash(f"'{tenant.name}' has been approved.", "success")
    return redirect(url_for("super_admin.dashboard"))


@bp.post("/super/tenants/<int:tenant_id>/reject")
@super_admin_required
def reject_tenant(tenant_id: int):
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        flash("Tenant not found.", "error")
        return redirect(url_for("super_admin.dashboard"))

    admin_email = _first_admin_email(tenant)
    tenant.status = TenantStatus.suspended

    _log_super_audit("tenant_rejected", "tenant", tenant.id, {"subdomain": tenant.subdomain})
    db.session.commit()

    if admin_email:
        try:
            send_tenant_rejection(admin_email, tenant.name)
        except Exception:
            current_app.logger.exception(
                "Failed to send rejection email for tenant %s", tenant.id
            )

    flash(f"'{tenant.name}' has been rejected.", "info")
    return redirect(url_for("super_admin.dashboard"))


@bp.post("/super/tenants/<int:tenant_id>/suspend")
@super_admin_required
def suspend_tenant(tenant_id: int):
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        flash("Tenant not found.", "error")
        return redirect(url_for("super_admin.dashboard"))

    tenant.status = TenantStatus.suspended
    _log_super_audit("tenant_suspended", "tenant", tenant.id, {"subdomain": tenant.subdomain})
    db.session.commit()

    flash(f"'{tenant.name}' has been suspended.", "info")
    return redirect(url_for("super_admin.dashboard"))


@bp.post("/super/tenants/<int:tenant_id>/unsuspend")
@super_admin_required
def unsuspend_tenant(tenant_id: int):
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        flash("Tenant not found.", "error")
        return redirect(url_for("super_admin.dashboard"))

    tenant.status = TenantStatus.active
    _log_super_audit("tenant_unsuspended", "tenant", tenant.id, {"subdomain": tenant.subdomain})
    db.session.commit()

    flash(f"'{tenant.name}' has been unsuspended.", "info")
    return redirect(url_for("super_admin.dashboard"))


@bp.post("/super/tenants/<int:tenant_id>/toggle_listed")
@super_admin_required
def toggle_listed(tenant_id: int):
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        flash("Tenant not found.", "error")
        return redirect(url_for("super_admin.dashboard"))

    tenant.is_listed = not tenant.is_listed
    db.session.commit()

    state = "listed" if tenant.is_listed else "unlisted"
    flash(f"'{tenant.name}' is now {state}.", "info")
    return redirect(url_for("super_admin.dashboard"))


# ---------------------------------------------------------------------------
# Per-tenant stats
# ---------------------------------------------------------------------------

_CANCELLED_STATUSES = [
    BookingStatus.cancelled_by_member,
    BookingStatus.cancelled_by_admin,
    BookingStatus.cancelled_downtime,
]


@bp.get("/super/stats")
@super_admin_required
def stats():
    now = datetime.now(timezone.utc)
    period = request.args.get("period", "all")

    # Subqueries: users count current state (not created_at)
    admin_sq = (
        db.select(func.count(User.id))
        .where(
            User.tenant_id == Tenant.id,
            User.is_admin == True,  # noqa: E712
            User.status == UserStatus.active,
        )
        .correlate(Tenant).scalar_subquery()
    )
    member_sq = (
        db.select(func.count(User.id))
        .where(
            User.tenant_id == Tenant.id,
            User.is_admin == False,  # noqa: E712
            User.is_super_admin == False,  # noqa: E712
            User.status == UserStatus.active,
        )
        .correlate(Tenant).scalar_subquery()
    )
    suspended_sq = (
        db.select(func.count(User.id))
        .where(
            User.tenant_id == Tenant.id,
            User.is_admin == False,  # noqa: E712
            User.is_super_admin == False,  # noqa: E712
            User.status == UserStatus.frozen,
        )
        .correlate(Tenant).scalar_subquery()
    )
    resource_sq = (
        db.select(func.count(Resource.id))
        .where(Resource.tenant_id == Tenant.id)
        .correlate(Tenant).scalar_subquery()
    )
    future_sq = (
        db.select(func.count(Booking.id))
        .where(
            Booking.tenant_id == Tenant.id,
            Booking.starts_at > now,
            Booking.status == BookingStatus.active,
        )
        .correlate(Tenant).scalar_subquery()
    )
    completed_sq = (
        db.select(func.count(Booking.id))
        .where(
            Booking.tenant_id == Tenant.id,
            Booking.ends_at <= now,
            Booking.status.notin_(_CANCELLED_STATUSES),
        )
        .correlate(Tenant).scalar_subquery()
    )

    rows = db.session.execute(
        db.select(
            Tenant,
            admin_sq.label("admin_count"),
            member_sq.label("member_count"),
            suspended_sq.label("suspended_count"),
            resource_sq.label("resource_count"),
            future_sq.label("future_bookings"),
            completed_sq.label("completed_bookings"),
        ).order_by(Tenant.name)
    ).all()

    return render_template(
        "super_admin/stats.html",
        rows=rows,
        period=period,
        now=now,
    )


# ---------------------------------------------------------------------------
# Audit log (super-admin events only: tenant_id IS NULL)
# ---------------------------------------------------------------------------

@bp.get("/super/audit-log")
@super_admin_required
def audit_log():
    page = request.args.get("page", 1, type=int)
    per_page = 50

    events_q = (
        db.select(AuditEvent)
        .where(AuditEvent.tenant_id == None)  # noqa: E711
        .order_by(AuditEvent.created_at.desc())
    )
    total = db.session.scalar(
        db.select(func.count()).select_from(
            db.select(AuditEvent).where(AuditEvent.tenant_id == None).subquery()  # noqa: E711
        )
    )
    events = db.session.scalars(
        events_q.limit(per_page).offset((page - 1) * per_page)
    ).all()
    total_pages = max(1, (total + per_page - 1) // per_page)

    return render_template(
        "super_admin/audit_log.html",
        events=events,
        page=page,
        total_pages=total_pages,
    )
