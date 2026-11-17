from urllib.parse import urlsplit

from flask import current_app, flash, g, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from app.auth_decorators import require_tenant
from app.blueprints.auth import bp
from app.extensions import db, limiter
from app.models import User
from app.models.user import UserStatus
from app.services.email import send_password_reset

bp.before_request(require_tenant)


def _make_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt="password-reset")


def _safe_next(next_url: str | None) -> str | None:
    """Only allow relative paths on the same host to prevent open-redirect."""
    if not next_url:
        return None
    parsed = urlsplit(next_url)
    if parsed.netloc or parsed.scheme:
        return None
    return next_url


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        if current_user.status == UserStatus.pending:
            return redirect(url_for("auth.pending"))
        return redirect(url_for("member.home"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        display_name = request.form.get("display_name", "").strip()

        errors = []
        if not email:
            errors.append("Email is required.")
        if len(password) < 10:
            errors.append("Password must be at least 10 characters.")
        if not display_name:
            errors.append("Display name is required.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("auth/register.html", email=email, display_name=display_name)

        existing = db.session.execute(
            db.select(User).where(User.tenant_id == g.tenant.id, User.email == email)
        ).scalar_one_or_none()

        if existing:
            if existing.status == UserStatus.rejected:
                existing.status = UserStatus.pending
                existing.password_hash = generate_password_hash(password)
                existing.display_name = display_name
                existing.rejection_note = None
                db.session.commit()
                flash("Your application has been resubmitted. Please wait for admin approval.", "info")
                return redirect(url_for("auth.pending"))
            else:
                flash("That email is already registered.", "error")
                return render_template("auth/register.html", email=email, display_name=display_name)

        user = User(
            tenant_id=g.tenant.id,
            email=email,
            password_hash=generate_password_hash(password),
            display_name=display_name,
            status=UserStatus.pending,
            is_admin=False,
            notification_prefs={},
        )
        db.session.add(user)
        db.session.commit()
        flash("Registration successful. Your account is pending approval.", "info")
        return redirect(url_for("auth.pending"))

    return render_template("auth/register.html", email="", display_name="")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        if current_user.status == UserStatus.pending:
            return redirect(url_for("auth.pending"))
        return redirect(url_for("member.home"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = db.session.execute(
            db.select(User).where(User.tenant_id == g.tenant.id, User.email == email)
        ).scalar_one_or_none()

        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid email or password.", "error")
            return render_template("auth/login.html")

        if user.status == UserStatus.frozen:
            flash("Your account has been frozen. Contact an administrator.", "error")
            return render_template("auth/login.html")

        if user.status == UserStatus.rejected:
            flash("Your application was rejected. You may re-register with the same email.", "error")
            return render_template("auth/login.html")

        login_user(user, remember=True)

        if user.status == UserStatus.pending:
            return redirect(url_for("auth.pending"))

        next_url = _safe_next(request.form.get("next") or request.args.get("next"))
        return redirect(next_url or url_for("member.home"))

    return render_template("auth/login.html")


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# Pending-approval page (protected — demonstrates @login_required redirect)
# ---------------------------------------------------------------------------

@bp.get("/pending")
@login_required
def pending():
    if current_user.status == UserStatus.active:
        return redirect(url_for("member.home"))
    return render_template("auth/pending.html")


# ---------------------------------------------------------------------------
# Password reset scaffold (no email sending yet)
# ---------------------------------------------------------------------------

@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = db.session.execute(
            db.select(User).where(User.tenant_id == g.tenant.id, User.email == email)
        ).scalar_one_or_none()

        if user:
            s = _make_serializer()
            # password_hash prefix invalidates the token after a successful reset
            # tenant_id in payload so apex reset-password route can find the right user
            token = s.dumps({"email": user.email, "ph": user.password_hash[16:32], "tenant_id": g.tenant.id})
            reset_url = f"https://{current_app.config['APEX_HOST']}/auth/reset-password/{token}"
            try:
                send_password_reset(user.email, reset_url)
            except Exception:
                current_app.logger.exception(
                    "Failed to send password reset email to %s", user.email
                )
                flash(
                    "We couldn't send the reset email. Please try again later or contact support.",
                    "danger",
                )
                return redirect(url_for("auth.forgot_password"))

        # Same message regardless of whether the email exists — avoids leaking info
        flash("Check your email for a password reset link. It expires in 1 hour.", "info")
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html")


