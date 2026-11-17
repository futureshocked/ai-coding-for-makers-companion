from flask import flash, g, redirect, render_template, request, url_for
from flask_login import current_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.auth_decorators import member_required, require_tenant
from app.blueprints.member import bp
from app.extensions import db
from app.models import Resource, User
from app.models.resource import ResourceCategory
from app.models.user import UserStatus

bp.before_request(require_tenant)

AVATAR_OPTIONS = ["🦊", "🐱", "🐸", "🦝", "🐧", "🦁", "🐺", "🦉", "🐙", "🦋", "🐝", "🌵"]


@bp.route("/profile", methods=["GET", "POST"])
@member_required
def profile():
    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        avatar = request.form.get("avatar", "")

        errors = []

        if not display_name:
            errors.append("Display name is required.")
        if not email:
            errors.append("Email is required.")
        elif email != current_user.email:
            conflict = db.session.execute(
                db.select(User).where(User.tenant_id == g.tenant.id, User.email == email, User.id != current_user.id)
            ).scalar_one_or_none()
            if conflict:
                errors.append("That email is already in use by another account.")

        if new_password:
            if not check_password_hash(current_user.password_hash, current_password):
                errors.append("Current password is incorrect.")
            elif len(new_password) < 10:
                errors.append("New password must be at least 10 characters.")
            elif new_password != confirm_password:
                errors.append("New passwords do not match.")

        if avatar and avatar not in AVATAR_OPTIONS:
            avatar = ""

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "member/profile.html",
                avatar_options=AVATAR_OPTIONS,
                form={"display_name": display_name, "email": email, "avatar": avatar},
            )

        current_user.display_name = display_name
        current_user.email = email
        current_user.avatar = avatar or None
        if new_password:
            current_user.password_hash = generate_password_hash(new_password)

        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("member.profile"))

    return render_template(
        "member/profile.html",
        avatar_options=AVATAR_OPTIONS,
        form={
            "display_name": current_user.display_name,
            "email": current_user.email,
            "avatar": current_user.avatar or "",
        },
    )


@bp.get("/home")
@member_required
def home():
    category_filter = request.args.get("category", "")
    q = (
        db.select(Resource)
        .where(Resource.tenant_id == g.tenant.id, Resource.is_archived == False)  # noqa: E712
        .order_by(Resource.name)
    )
    if category_filter:
        try:
            cat = ResourceCategory(category_filter)
            q = q.where(Resource.category == cat)
        except ValueError:
            pass
    resources = db.session.execute(q).scalars().all()
    return render_template(
        "bookings/resources_list.html",
        resources=resources,
        categories=ResourceCategory,
        current_category=category_filter,
    )
