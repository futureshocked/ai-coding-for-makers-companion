"""Tests for the resolve_tenant before_request hook."""
import pytest

from app.models.tenant import Tenant, TenantStatus
from tests.conftest import HostedFlaskClient


def _client_for(app, host):
    return HostedFlaskClient(app, default_host=host)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def pending_tenant(db):
    t = Tenant(name="Pending Org", subdomain="pending", status=TenantStatus.pending, is_listed=True)
    db.session.add(t)
    db.session.commit()
    return t


@pytest.fixture
def suspended_tenant(db):
    t = Tenant(name="Suspended Org", subdomain="suspended", status=TenantStatus.suspended, is_listed=True)
    db.session.add(t)
    db.session.commit()
    return t


# ---------------------------------------------------------------------------
# /healthz is exempt from tenant resolution
# ---------------------------------------------------------------------------

def test_healthz_exempt_on_tenant_host(app, tenant):
    c = _client_for(app, f"{tenant.subdomain}.lvh.me")
    assert c.get("/healthz").status_code == 200


def test_healthz_exempt_on_unknown_host(app):
    c = _client_for(app, "ghost.lvh.me")
    assert c.get("/healthz").status_code == 200


def test_healthz_exempt_on_apex(app):
    c = _client_for(app, "lvh.me")
    assert c.get("/healthz").status_code == 200


# ---------------------------------------------------------------------------
# Apex host
# ---------------------------------------------------------------------------

def test_apex_host_serves_routes(app):
    # On the apex host g.is_apex=True; public blueprint routes render
    c = _client_for(app, "lvh.me")
    assert c.get("/").status_code == 200
    assert c.get("/register/org").status_code == 200


def test_www_apex_host_serves_routes(app):
    c = _client_for(app, "www.lvh.me")
    assert c.get("/").status_code == 200


# ---------------------------------------------------------------------------
# Super-admin host
# ---------------------------------------------------------------------------

def test_super_admin_host_healthz_ok(app):
    c = _client_for(app, "app.lvh.me")
    assert c.get("/healthz").status_code == 200


# ---------------------------------------------------------------------------
# Active tenant subdomain resolves
# ---------------------------------------------------------------------------

def test_active_tenant_resolves(app, tenant):
    c = _client_for(app, f"{tenant.subdomain}.lvh.me")
    assert c.get("/auth/login").status_code == 200


# ---------------------------------------------------------------------------
# Non-existent subdomain → 404
# ---------------------------------------------------------------------------

def test_nonexistent_subdomain_404(app):
    c = _client_for(app, "ghost.lvh.me")
    assert c.get("/auth/login").status_code == 404


# ---------------------------------------------------------------------------
# Pending tenant → 404 (don't leak existence)
# ---------------------------------------------------------------------------

def test_pending_tenant_404(app, pending_tenant):
    c = _client_for(app, f"{pending_tenant.subdomain}.lvh.me")
    assert c.get("/auth/login").status_code == 404


# ---------------------------------------------------------------------------
# Suspended tenant → 404
# ---------------------------------------------------------------------------

def test_suspended_tenant_404(app, suspended_tenant):
    c = _client_for(app, f"{suspended_tenant.subdomain}.lvh.me")
    assert c.get("/auth/login").status_code == 404


# ---------------------------------------------------------------------------
# Reserved subdomains → 404
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("subdomain", ["admin", "api", "mail", "register", "auth", "static"])
def test_reserved_subdomain_404(app, subdomain):
    c = _client_for(app, f"{subdomain}.lvh.me")
    assert c.get("/auth/login").status_code == 404


# ---------------------------------------------------------------------------
# Multi-level subdomain → 404
# ---------------------------------------------------------------------------

def test_multilevel_subdomain_404(app):
    c = _client_for(app, "a.b.lvh.me")
    assert c.get("/auth/login").status_code == 404


# ---------------------------------------------------------------------------
# Completely unrelated host → 404
# ---------------------------------------------------------------------------

def test_unrelated_host_404(app):
    c = _client_for(app, "evil.com")
    assert c.get("/auth/login").status_code == 404
