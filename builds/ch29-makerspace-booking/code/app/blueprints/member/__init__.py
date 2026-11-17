from flask import Blueprint

bp = Blueprint("member", __name__)

from app.blueprints.member import routes  # noqa: E402, F401
