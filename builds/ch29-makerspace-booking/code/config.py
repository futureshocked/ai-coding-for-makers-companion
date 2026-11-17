import os
from sqlalchemy.pool import NullPool


_DEV_SECRET = "dev-secret-change-me"


def _read_version_file() -> str:
    try:
        p = os.path.join(os.path.dirname(__file__), "VERSION")
        with open(p) as f:
            return f.read().strip()
    except FileNotFoundError:
        return "dev"


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://localhost/makerspace"
    )
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "app", "static", "uploads", "resources")
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024  # 4 MB
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
    RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "noreply@localhost")
    REMINDER_INTERVAL_HOURS = int(os.environ.get("REMINDER_INTERVAL_HOURS", 1))
    REMINDER_HOURS_BEFORE = int(os.environ.get("REMINDER_HOURS_BEFORE", 24))
    APP_VERSION = os.environ.get("APP_VERSION") or _read_version_file()
    APEX_HOST = os.environ.get("APEX_HOST", "makerbooking.com")
    SUPER_ADMIN_HOST = os.environ.get("SUPER_ADMIN_HOST", f"app.{APEX_HOST}")
    RESERVED_SUBDOMAINS = {"www", "app", "api", "admin", "mail", "register", "auth", "static"}
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Do NOT set SESSION_COOKIE_DOMAIN — per-subdomain isolation is the default


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    APEX_HOST = "lvh.me"
    SUPER_ADMIN_HOST = "app.lvh.me"
    SERVER_NAME = "lvh.me:5000"
    SESSION_COOKIE_SECURE = False


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL", "postgresql://localhost/makerspace_test"
    )
    RATELIMIT_ENABLED = False
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_ENGINE_OPTIONS = {"poolclass": NullPool}
    APEX_HOST = "lvh.me"
    SUPER_ADMIN_HOST = "app.lvh.me"
    SERVER_NAME = "lvh.me"
    SESSION_COOKIE_SECURE = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    # SERVER_NAME must NOT be set here — Docker healthcheck uses Host: app:8000


def validate_production_config() -> None:
    """Fail fast if production is misconfigured. Called from create_app()."""
    if not os.environ.get("SECRET_KEY") or os.environ.get("SECRET_KEY") == _DEV_SECRET:
        raise RuntimeError(
            "SECRET_KEY must be set to a strong unique value in production "
            "(unset or matches the dev default)."
        )
    if not os.environ.get("RESEND_API_KEY"):
        raise RuntimeError("RESEND_API_KEY must be set in production.")


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
