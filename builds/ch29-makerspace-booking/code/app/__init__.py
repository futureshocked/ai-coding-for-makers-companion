import os

from flask import Flask, abort, g, jsonify, redirect, request

from app.extensions import db, login_manager, migrate, limiter, scheduler
from config import config, validate_production_config


def create_app(config_name: str | None = None) -> Flask:
    if config_name is None:
        config_name = os.environ.get("FLASK_CONFIG", "default")
    if config_name == "production":
        validate_production_config()

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    from app.models import Tenant, User, Resource, Booking, NotificationLog, AuditEvent  # noqa: F401
    from app.models.tenant import TenantStatus

    # resolve_tenant must be registered before blueprints so it fires first
    @app.before_request
    def resolve_tenant():
        # Flask 3.x stores g on the app context, so in tests (which share a
        # single app context across multiple simulated requests) Flask-Login's
        # g._login_user can survive from one request to the next and bypass
        # user_loader.  Clear it explicitly so every request starts fresh.
        g.pop("_login_user", None)

        g.tenant = None
        g.is_apex = False
        g.is_super_admin_host = False

        if request.path == "/healthz" or request.endpoint == "static":
            return

        APEX = app.config["APEX_HOST"]
        SUPER = app.config["SUPER_ADMIN_HOST"]
        RESERVED = app.config["RESERVED_SUBDOMAINS"]

        hostname = request.host.split(":")[0].lower()

        if hostname in (APEX, f"www.{APEX}"):
            g.is_apex = True
            return
        if hostname == SUPER:
            g.is_super_admin_host = True
            if request.path == "/" and request.method == "GET":
                return redirect("/super/login")
            return
        if not hostname.endswith("." + APEX):
            abort(404)
        sub = hostname[:-(len(APEX) + 1)]
        if "." in sub or sub in RESERVED:
            abort(404)

        tenant = db.session.scalar(db.select(Tenant).where(Tenant.subdomain == sub))
        if not tenant or tenant.status != TenantStatus.active:
            abort(404)
        g.tenant = tenant

        if request.path == "/" and request.method == "GET":
            from flask_login import current_user
            if current_user.is_authenticated:
                return redirect("/home")
            return redirect("/auth/login")

    from app.blueprints.public import bp as public_bp
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.member import bp as member_bp
    from app.blueprints.admin import bp as admin_bp
    from app.blueprints.super_admin import bp as super_admin_bp

    from app.routes.bookings import bp as bookings_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(member_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(super_admin_bp)
    app.register_blueprint(bookings_bp)

    @login_manager.user_loader
    def load_user(user_id: str):
        user = db.session.get(User, int(user_id))
        if not user:
            return None
        if user.is_super_admin:
            return user if g.get("is_super_admin_host") else None
        if g.get("tenant") and user.tenant_id == g.tenant.id:
            return user
        return None

    @app.context_processor
    def inject_app_version():
        return {"app_version": app.config.get("APP_VERSION", "dev")}

    @app.route("/healthz")
    def healthz():
        return jsonify(status="ok", version=app.config.get("APP_VERSION", "dev"))

    from app.commands import seed_db, create_admin, create_super_admin, delete_seed_users
    app.cli.add_command(seed_db)
    app.cli.add_command(create_admin)
    app.cli.add_command(create_super_admin)
    app.cli.add_command(delete_seed_users)

    # In prod the scheduler runs in a separate container; the app service sets RUN_SCHEDULER=0
    # so it doesn't fire reminders N times (one per gunicorn worker). Default-on for dev.
    if not app.config.get("TESTING") and os.environ.get("RUN_SCHEDULER", "1") == "1":
        from app.services.reminders import send_due_reminders

        hours = app.config["REMINDER_INTERVAL_HOURS"]
        scheduler.add_job(
            send_due_reminders,
            "interval",
            hours=hours,
            args=[app],
            id="booking_reminders",
            replace_existing=True,
        )
        if not scheduler.running and (
            not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
        ):
            scheduler.start()

    return app
