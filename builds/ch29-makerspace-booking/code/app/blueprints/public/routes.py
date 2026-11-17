from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import generate_password_hash

from flask import current_app, flash, g, redirect, render_template, request

from app.auth_decorators import require_apex
from app.blueprints.public import bp
from app.extensions import db
from app.models import AuditEvent, Tenant, User
from app.models.tenant import SUBDOMAIN_PATTERN, TenantStatus
from app.models.user import UserStatus

bp.before_request(require_apex)


def _make_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt="password-reset")


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------

@bp.get("/")
def landing():
    tenants = db.session.scalars(
        db.select(Tenant)
        .where(Tenant.status == TenantStatus.active, Tenant.is_listed == True)  # noqa: E712
        .order_by(Tenant.name)
    ).all()
    apex = current_app.config["APEX_HOST"]
    return render_template("public/landing.html", tenants=tenants, apex=apex)


# ---------------------------------------------------------------------------
# Org self-signup
# ---------------------------------------------------------------------------

@bp.route("/register/org", methods=["GET", "POST"])
def register_org():
    if request.method == "POST":
        org_name = request.form.get("org_name", "").strip()
        subdomain = request.form.get("subdomain", "").strip().lower()
        admin_email = request.form.get("admin_email", "").strip().lower()
        admin_display_name = request.form.get("admin_display_name", "").strip()
        admin_password = request.form.get("admin_password", "")
        admin_password2 = request.form.get("admin_password2", "")

        errors = []
        if not org_name:
            errors.append("Organisation name is required.")
        if not subdomain:
            errors.append("Subdomain is required.")
        elif not SUBDOMAIN_PATTERN.match(subdomain):
            errors.append(
                "Subdomain must be 3–32 lowercase letters, digits, or hyphens, "
                "starting and ending with a letter or digit."
            )
        elif subdomain in current_app.config["RESERVED_SUBDOMAINS"]:
            errors.append(f"'{subdomain}' is a reserved subdomain.")
        else:
            existing = db.session.scalar(
                db.select(Tenant).where(
                    db.func.lower(Tenant.subdomain) == subdomain
                )
            )
            if existing:
                errors.append(f"The subdomain '{subdomain}' is already taken.")
        if not admin_email:
            errors.append("Admin email is required.")
        if not admin_display_name:
            errors.append("Admin display name is required.")
        if len(admin_password) < 10:
            errors.append("Password must be at least 10 characters.")
        elif admin_password != admin_password2:
            errors.append("Passwords do not match.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "public/register_org.html",
                form={
                    "org_name": org_name,
                    "subdomain": subdomain,
                    "admin_email": admin_email,
                    "admin_display_name": admin_display_name,
                },
            )

        tenant = Tenant(
            name=org_name,
            subdomain=subdomain,
            status=TenantStatus.pending,
            is_listed=True,
        )
        db.session.add(tenant)
        db.session.flush()  # get tenant.id before creating user

        user = User(
            tenant_id=tenant.id,
            email=admin_email,
            password_hash=generate_password_hash(admin_password),
            display_name=admin_display_name,
            is_admin=True,
            status=UserStatus.pending,
            notification_prefs={},
        )
        db.session.add(user)

        audit = AuditEvent(
            tenant_id=None,
            actor_user_id=None,
            action="tenant_signup",
            subject_type="tenant",
            subject_id=tenant.id,
            payload={"org_name": org_name, "subdomain": subdomain},
        )
        db.session.add(audit)
        db.session.commit()

        flash(
            f"Your makerspace '{org_name}' has been submitted for review. "
            "You'll be notified once it's approved.",
            "info",
        )
        return redirect("/")

    return render_template("public/register_org.html", form={})


# ---------------------------------------------------------------------------
# Apex-hosted password reset (moved from auth blueprint)
# ---------------------------------------------------------------------------

@bp.route("/auth/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    s = _make_serializer()
    try:
        data = s.loads(token, max_age=3600)
    except (SignatureExpired, BadSignature):
        flash("The reset link is invalid or has expired.", "error")
        return redirect("/")

    tenant_id = data.get("tenant_id")
    if tenant_id is None:
        # Super-admin reset — implemented in Chunk 5
        flash("Super-admin password reset is not yet available.", "error")
        return redirect("/")

    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        flash("The reset link is no longer valid.", "error")
        return redirect("/")

    user = db.session.execute(
        db.select(User).where(
            User.tenant_id == tenant_id,
            User.email == data.get("email"),
        )
    ).scalar_one_or_none()

    if not user or user.password_hash[16:32] != data.get("ph"):
        flash("The reset link is no longer valid.", "error")
        return redirect("/")

    if request.method == "POST":
        new_password = request.form.get("password", "")
        confirm = request.form.get("password2", "")
        if len(new_password) < 10:
            flash("Password must be at least 10 characters.", "error")
            return render_template(
                "public/reset_password.html", token=token, tenant_name=tenant.name
            )
        if new_password != confirm:
            flash("Passwords do not match.", "error")
            return render_template(
                "public/reset_password.html", token=token, tenant_name=tenant.name
            )

        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash("Password updated. You can now log in.", "info")
        apex = current_app.config["APEX_HOST"]
        return redirect(f"https://{tenant.subdomain}.{apex}/auth/login")

    return render_template(
        "public/reset_password.html", token=token, tenant_name=tenant.name
    )
