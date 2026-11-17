# Multi-Tenancy Refactor — v1.0.0 → v2.0.0

This document captures the design decisions, implementation patterns, and lessons learned from the multi-tenancy refactor that produced v2.0.0. It is intended for developers who need to understand the architecture, extend it, or debug it.

---

## Why multi-tenancy?

v1.0.0 was a single-tenant application — one set of members, one set of resources, one makerspace. The goal of v2.0.0 is to allow **multiple independent organisations** (each a "tenant") to share a single deployment. Each organisation:

- Gets a unique subdomain: `<subdomain>.makerbooking.com`
- Has its own isolated members, resources, bookings, and audit log
- Cannot see or access any data belonging to another organisation
- Signs up via a self-service form and is approved by a platform super-admin

The platform owner (super-admin) manages the lifecycle of all tenants from a dedicated console at `app.makerbooking.com`.

---

## Architecture overview

```
Request to acme.makerbooking.com
        │
        ▼
resolve_tenant() before_request hook
  → extracts "acme" from Host header
  → looks up Tenant(subdomain="acme", status=active)
  → sets g.tenant = <Tenant>
        │
        ▼
load_user() (Flask-Login)
  → loads user from session
  → verifies user.tenant_id == g.tenant.id
  → cross-tenant session → returns None (logs out silently)
        │
        ▼
Blueprint route
  → @member_required / @admin_required enforce login + g.tenant match
  → all queries: .where(Model.tenant_id == g.tenant.id)
  → PK lookups: get_for_tenant_or_404(Model, id)
```

### Three host types

| Host pattern | `g` state | Who uses it |
|---|---|---|
| `makerbooking.com`, `www.makerbooking.com` | `g.is_apex = True` | Landing page, org signup, apex-hosted password reset |
| `app.makerbooking.com` | `g.is_super_admin_host = True` | Platform super-admin console |
| `<subdomain>.makerbooking.com` | `g.tenant = <Tenant>` | Tenant members and admins |

Configured in `config.py`:
```python
APEX_HOST = os.environ.get("APEX_HOST", "makerbooking.com")
SUPER_ADMIN_HOST = os.environ.get("SUPER_ADMIN_HOST", f"app.{APEX_HOST}")
```

---

## Data model changes

### New model: `Tenant` (`app/models/tenant.py`)

```python
class Tenant(db.Model):
    id: int (primary key)
    name: str              # e.g. "Acme Makerspace"
    subdomain: str         # e.g. "acme" — lowercase, unique, 3–32 chars
    status: TenantStatus   # pending | active | suspended
    is_listed: bool        # show on landing page
    created_at: datetime
```

Subdomain rules: `^[a-z][a-z0-9-]{1,30}[a-z0-9]$`, not in `RESERVED_SUBDOMAINS = {"www", "app", "api", "admin", "mail", "register", "auth", "static"}`.

### Added `tenant_id` foreign key to five tables

`users`, `resources`, `bookings`, `notification_log`, `audit_events` — each now has:
```python
tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
```

Super-admins are the exception: their `tenant_id` is `NULL` (they belong to no tenant).

### Per-tenant email uniqueness (users table)

The global `UNIQUE(email)` constraint was replaced with two partial indexes:

```sql
-- tenant users: unique email within a tenant (case-insensitive)
CREATE UNIQUE INDEX uq_users_tenant_email
    ON users (tenant_id, lower(email))
    WHERE tenant_id IS NOT NULL;

-- super-admins: unique email globally across super-admins
CREATE UNIQUE INDEX uq_users_super_admin_email
    ON users (lower(email))
    WHERE tenant_id IS NULL AND is_super_admin = true;
```

### Super-admin invariant (CHECK constraint)

```sql
CONSTRAINT ck_users_super_admin_invariant
    CHECK ((tenant_id IS NULL) = is_super_admin)
```

This enforces: super-admins have no tenant, tenant users always have exactly one tenant. It is impossible to create a user that violates this at the database level.

---

## Two-phase migration strategy

The schema change was split into two migrations to avoid locking or data-loss risk:

**Revision A** (`a1f2b3c4d5e6_add_tenants_and_backfill.py`):
- Creates `tenants` table
- Adds `tenant_id` as **nullable** to all five tables (safe, no existing rows need updating)
- Backfill: if any data exists, creates a `Default` tenant and assigns all existing records to it

**Revision B** (`b2c3d4e5f6a7_tenant_constraints.py`):
- Makes `tenant_id` NOT NULL on `resources`, `bookings`, `notification_log` (data already backfilled)
- Drops global email uniqueness; adds the two partial indexes
- Adds the CHECK constraint

Why two phases? Rev A is always safe — adding nullable columns never breaks existing queries. Rev B then tightens the constraints with the confidence that all data is already consistent. This pattern is the standard approach for zero-downtime schema migrations.

---

## Developer patterns: rules you must follow

### 1. Always use `get_for_tenant_or_404()` for PK lookups

```python
# WRONG — cross-tenant PK leakage: user in tenant A can read tenant B's resources by ID
resource = db.get_or_404(Resource, resource_id)

# CORRECT — returns 404 if the record belongs to a different tenant
from app.scoping import get_for_tenant_or_404
resource = get_for_tenant_or_404(Resource, resource_id)
```

`get_for_tenant_or_404` is in `app/scoping.py`. Use it everywhere in tenant-scoped blueprints.

### 2. Always scope list queries by `tenant_id`

```python
# WRONG — returns resources from ALL tenants
resources = db.session.scalars(db.select(Resource)).all()

# CORRECT — scoped to the current tenant
resources = db.session.scalars(
    db.select(Resource).where(Resource.tenant_id == g.tenant.id)
).all()
```

### 3. Never use `url_for()` in the scheduler context

The APScheduler runs outside a request context, so `url_for()` has no `SERVER_NAME` to work with. Build URLs as strings:

```python
# WRONG
url = url_for("member.my_bookings", _external=True)

# CORRECT
manage_url = f"https://{booking.user.tenant.subdomain}.{app.config['APEX_HOST']}/my-bookings"
```

This pattern is used throughout `app/services/reminders.py` and `app/blueprints/auth/routes.py`.

### 4. Wire `require_tenant` into every tenant-scoped blueprint

```python
from app.auth_decorators import require_tenant

bp = Blueprint("member", __name__)
bp.before_request(require_tenant)   # 404 on any non-tenant host
```

This prevents tenant routes from accidentally being reachable on the apex or super-admin host.

### 5. Do not set `SESSION_COOKIE_DOMAIN`

Flask's default (no `SESSION_COOKIE_DOMAIN`) scopes each session cookie to the exact hostname. This gives free per-subdomain isolation — a cookie issued for `acme.makerbooking.com` is not sent to `widgetco.makerbooking.com`. If you were to set `SESSION_COOKIE_DOMAIN = ".makerbooking.com"`, cookies would be shared across all subdomains and `load_user` would become the only isolation barrier.

---

## Auth decorators (`app/auth_decorators.py`)

All decorators are centralised — do not re-implement in blueprints.

| Decorator / Hook | Use on |
|---|---|
| `tenant_required` | Individual routes that need a tenant |
| `require_tenant()` | `bp.before_request(require_tenant)` — applies to all routes in a blueprint |
| `member_required` | Routes accessible by active tenant members |
| `admin_required` | Routes accessible by tenant admins |
| `super_admin_required` | Routes in the super-admin blueprint |
| `apex_only` | Routes that must only be reachable on the apex host |
| `require_apex()` | `bp.before_request(require_apex)` — applies to all routes in a blueprint |

---

## New blueprints

### Public blueprint (`app/blueprints/public/`)

Registered on the apex host. Contains:

| Route | Purpose |
|---|---|
| `GET /` | Landing page — lists active, publicly-listed tenants |
| `GET /register/org` | Org self-signup form |
| `POST /register/org` | Creates Tenant (status=pending) + first admin User (status=pending); logs audit event |
| `GET /auth/reset-password/<token>` | Apex-hosted password reset form |
| `POST /auth/reset-password/<token>` | Validates token (which includes `tenant_id`), resets password, redirects to tenant login |

Password reset was moved to the apex host because the auth blueprint is now tenant-scoped — a user who has forgotten their password cannot be expected to know their subdomain.

### Super-admin blueprint (`app/blueprints/super_admin/`)

Accessible only at `app.makerbooking.com`. All routes return 404 on any other host (enforced by `_require_super_admin_host` in `before_request`).

| Route | Purpose |
|---|---|
| `GET /super/login` | Super-admin login form |
| `POST /super/login` | Authenticates against `tenant_id=NULL, is_super_admin=True` users |
| `GET /super/` | Dashboard — all tenants with status, member count, actions |
| `POST /super/tenants/<id>/approve` | Activates tenant + first admin; sends approval email |
| `POST /super/tenants/<id>/reject` | Sets status=suspended; sends rejection email |
| `POST /super/tenants/<id>/suspend` | Suspends an active tenant |
| `POST /super/tenants/<id>/toggle_listed` | Toggles landing-page visibility |

`activate_tenant()` in `app/services/tenants.py` handles the approve logic atomically.

---

## Deployment changes

### Custom Caddy image

Wildcard TLS (`*.makerbooking.com`) requires a DNS-01 ACME challenge because HTTP-01 cannot prove ownership of a wildcard. Caddy's standard image does not include DNS provider plugins, so a custom image is built:

```dockerfile
# caddy/Dockerfile
FROM caddy:builder AS builder
RUN xcaddy build --with github.com/caddy-dns/cloudflare

FROM caddy:latest
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
```

The deploy workflow builds and pushes this image to GHCR alongside the app image.

### CLOUDFLARE_API_TOKEN

The Cloudflare API token is needed by Caddy to create DNS TXT records during the DNS-01 challenge. It is passed to the caddy service via `env_file` in `docker-compose.yml`:

```yaml
caddy:
  env_file: /opt/makerbooking/.env
  environment:
    - CLOUDFLARE_API_TOKEN
```

Add to `/opt/makerbooking/.env` on the VPS:
```
CLOUDFLARE_API_TOKEN=<token with Zone:DNS Edit permission>
```

### Caddyfile — wildcard TLS

```
*.makerbooking.com {
    tls {
        dns cloudflare {env.CLOUDFLARE_API_TOKEN}
    }
    reverse_proxy app:8000
    ...
}
```

---

## Local development

`DevelopmentConfig` overrides APEX_HOST to use `lvh.me` — a public DNS name that always resolves to `127.0.0.1`:

```python
class DevelopmentConfig(BaseConfig):
    APEX_HOST = "lvh.me"
    SUPER_ADMIN_HOST = "app.lvh.me"
    SERVER_NAME = "lvh.me:5000"
    SESSION_COOKIE_SECURE = False
```

Set `FLASK_CONFIG=development` in your `.env`. Then:

- Landing page: `http://lvh.me:5000`
- Tenant `acme` (seeded): `http://acme.lvh.me:5000`
- Tenant `widgetco` (seeded): `http://widgetco.lvh.me:5000`
- Super-admin console: `http://app.lvh.me:5000`

No `/etc/hosts` edits needed — `lvh.me` is a real domain owned by a community project for exactly this purpose.

---

## Testing

Four new test suites live in `tests/tenancy/`:

| File | What it covers |
|---|---|
| `test_resolution.py` | Tenant resolved from hostname, 404 on invalid/suspended subdomain, reserved subdomain rejection, apex and super-admin host routing |
| `test_cross_tenant_isolation.py` | Member cannot read another tenant's bookings by ID, admin cannot access another tenant's resources, conflict detection is tenant-scoped, login/session isolation |
| `test_signup_flow.py` | Landing page content, org signup form validation (subdomain format, reserved words, uniqueness), pending state after signup, apex-hosted password reset |
| `test_super_admin.py` | Login/logout, dashboard access control, approve/reject lifecycle, member count display, audit logging |

Key fixtures (in `tests/conftest.py`):

```python
@pytest.fixture
def tenant(db):          # creates an active Tenant + its test client
def other_tenant(db):    # second isolated Tenant for cross-tenant tests
def tenant_client(app, tenant):   # test client scoped to tenant's subdomain
def other_tenant_client(app, other_tenant):
```

Always write cross-tenant isolation tests when adding routes that look up records by primary key. The pattern: create a record for `tenant`, try to access it via `other_tenant_client`, assert 404.

---

## Lessons learned

**Two-phase migrations are worth the extra file.** Rev A (nullable) is always safe to run on a live database. Rev B (constraints) runs once all data is confirmed consistent. Trying to do it in one step risks either a failed migration on non-empty data or a long table lock.

**Partial unique indexes are the right tool for per-tenant uniqueness.** A regular `UNIQUE(tenant_id, email)` would work but doesn't handle NULL (super-admins have no tenant). Partial indexes let you express "unique within this subset" cleanly and are supported natively by PostgreSQL.

**`SESSION_COOKIE_DOMAIN` is a trap.** Setting it to `.makerbooking.com` breaks per-subdomain isolation and turns cross-tenant session confusion from "impossible" into "likely". The default (no setting) is correct for a subdomain-per-tenant design.

**Build scheduler URLs as strings, not `url_for()`.** Flask's `url_for` needs a request context to know the host. Schedulers run in application context only. Using `f"https://{tenant.subdomain}.{app.config['APEX_HOST']}/..."` is explicit and testable.

**`lvh.me` eliminates `/etc/hosts` friction.** Using a public domain that resolves to 127.0.0.1 lets every developer (and CI) test subdomain routing without machine-specific configuration.
