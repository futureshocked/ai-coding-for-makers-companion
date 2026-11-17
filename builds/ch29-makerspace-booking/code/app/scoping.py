from flask import abort, g

from app.extensions import db


def get_for_tenant_or_404(model, id):
    obj = db.session.get(model, id)
    if obj is None or obj.tenant_id != g.tenant.id:
        abort(404)
    return obj
