from functools import wraps

from flask import abort, flash, g, redirect, url_for
from flask_login import current_user

from app.models.user import UserStatus


def tenant_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if g.get("tenant") is None:
            abort(404)
        return fn(*args, **kwargs)
    return inner


def require_tenant():
    """before_request hook for tenant-scoped blueprints."""
    if g.get("tenant") is None:
        abort(404)


def member_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access this page.", "error")
            return redirect(url_for("auth.login"))
        if current_user.status != UserStatus.active:
            flash("Your account is not yet active.", "error")
            return redirect(url_for("auth.pending"))
        if g.get("tenant") and current_user.tenant_id != g.tenant.id:
            abort(404)
        return fn(*args, **kwargs)
    return inner


def admin_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access this page.", "error")
            return redirect(url_for("auth.login"))
        if not current_user.is_admin:
            flash("Admin access required.", "error")
            return redirect(url_for("member.home"))
        if g.get("tenant") and current_user.tenant_id != g.tenant.id:
            abort(404)
        return fn(*args, **kwargs)
    return inner


def super_admin_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if not g.get("is_super_admin_host"):
            abort(404)
        if not current_user.is_authenticated or not current_user.is_super_admin:
            return redirect(url_for("super_admin.login"))
        return fn(*args, **kwargs)
    return inner


def require_apex():
    """before_request hook for apex-only blueprints."""
    if not g.get("is_apex"):
        abort(404)


def apex_only(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if not g.get("is_apex"):
            abort(404)
        return fn(*args, **kwargs)
    return inner
