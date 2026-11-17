from flask import Blueprint, abort, g

bp = Blueprint("super_admin", __name__)


def _require_super_admin_host():
    """before_request hook: 404 everything on non-super-admin hosts."""
    if not g.get("is_super_admin_host"):
        abort(404)


bp.before_request(_require_super_admin_host)

from app.blueprints.super_admin import routes  # noqa: E402, F401
