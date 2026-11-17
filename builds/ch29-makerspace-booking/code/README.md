# Makerspace Booking System

**Version 2.1.0**

A Flask-based multi-tenant booking system for makerspaces. Multiple independent organisations each get their own isolated subdomain (`<org>.makerbooking.com`). Members register and await admin approval before booking shared resources. Admins manage their own organisation's members, resources, and bookings. A platform super-admin manages the lifecycle of all tenant organisations.

> _For production deployment to a Hetzner VPS (Cloudflare, Resend, GitHub Actions, nightly backups), see [README_DEPLOY.md](README_DEPLOY.md). This document covers local development only._
>
> _For a detailed account of the multi-tenancy refactor (architecture, patterns, lessons), see [docs/REFACTORING.md](docs/REFACTORING.md)._

---

## Architecture

The application resolves the current tenant from the HTTP `Host` header on every request:

| Host | Context | Who uses it |
|---|---|---|
| `makerbooking.com` / `www.makerbooking.com` | Apex | Landing page, org self-signup, password reset |
| `app.makerbooking.com` | Super-admin | Platform tenant management console |
| `<subdomain>.makerbooking.com` | Tenant | Members and admins of that organisation |

Sessions are not shared across subdomains. A user logged into `acme.makerbooking.com` has no session on `widgetco.makerbooking.com`.

---

## Features

### Member-facing
- Register at your organisation's subdomain and await admin approval; re-registration allowed for rejected accounts
- Browse available resources with category filter and thumbnail previews
- Book a resource by date and time slot; conflict detection prevents double-booking
- Edit a booking up to 2 times within a ±60-minute grace window; unlimited comment-only edits
- Cancel a booking up to 1 hour before it starts
- View upcoming and past bookings on a personal dashboard
- Edit profile: display name, email, password, avatar emoji
- Password reset via email (1-hour expiry link, handled on the apex host)

### Admin-facing
- **Members:** approve, reject, freeze, unfreeze; edit name/email/avatar/admin flag
- **Resources:** create, edit, archive (soft-delete); set category, capacity, location, availability windows (weekday/weekend), and thumbnail image
- **Bookings:** view all bookings; unrestricted edit; cancel with member notification
- **Audit log:** tracks 19 event types across resource and booking actions

### Platform-level (super-admin)
- Landing page lists all active, publicly-listed tenant organisations
- Organisations self-register via `/register/org`; super-admin approves or rejects
- Super-admin console (`app.makerbooking.com`) shows all tenants with member counts and lifecycle controls (approve, reject, suspend, toggle listing)
- Approval email sent to first org admin on activation; rejection email on rejection

### Background jobs (APScheduler)
- Booking reminder emails sent 24 hours before each booking (configurable)
- Public-holiday check skips reminders on holidays (configurable country code)

---

## UI / Design System

The front-end follows the **Maker Forge** design language — an industrial-but-modern aesthetic suited to maker communities.

### Design tokens

All visual variables are CSS custom properties in `:root` inside `app/static/css/main.css`. Key groups:

| Token group | Representative values |
|---|---|
| Brand (nav, links) | `--brand: #6366f1` (indigo); `--brand-dark: #4f46e5`; `--brand-light: #eef2ff` |
| Accent (CTAs, submit buttons) | `--accent: #f97316` (amber); `--accent-dark: #ea6d09` |
| Navigation background | `--nav-bg: #0f172a` (deep slate) |
| Surface | `--surface: #ffffff`; `--surface-alt: #f8fafc` |
| Text | `--text-1: #0f172a`; `--text-2: #475569`; `--text-3: #94a3b8` |
| Border | `--border: #e2e8f0`; `--border-strong: #cbd5e1` |

Primary CTAs (booking, saving, submitting) use amber (`--accent`) to make them visually distinct from the indigo brand nav links. The super-admin console gets an amber nav underline and gold brand colour, triggered by `<body class="super-admin-context">` set in `app/templates/super_admin/base.html`.

### Typography

- **Headings** — [Space Grotesk](https://fonts.google.com/specimen/Space+Grotesk) (geometric, technical)
- **Body** — [Inter](https://fonts.google.com/specimen/Inter) (readable, professional)

Both loaded from Google Fonts via `<link rel="preconnect">` in `base.html`.

### Static assets

| File | Purpose |
|---|---|
| `app/static/css/main.css` | Complete custom stylesheet (~900 lines). No CSS framework. |
| `app/static/js/main.js` | Vanilla JS (~70 lines): flash auto-dismiss (5 s), mobile hamburger nav, tab switching. |

### Key UI components

| Component | Where used |
|---|---|
| Resource card grid (`.resource-grid`) | Member resource browser — replaces a flat table; 16:9 thumbnail, category badge overlay, hover lift effect |
| Category filter pills (`.filter-pills`) | GET link-based `?category=` navigation; no JS or form submit needed |
| Auth split-panel (`.auth-split`) | Login and register pages; dark brand panel left, form right; stacks vertically on mobile |
| Timeline audit log (`.timeline`) | Admin and super-admin audit log pages; collapsible JSON payload via `<details>` |
| Stat summary cards (`.stat-card`) | Super-admin stats page; aggregate totals row above the per-tenant breakdown table |
| Tab UI (`.tab-bar` / `.tab-panel`) | My Bookings page — Upcoming / Past & Cancelled tabs, switched by JS in `main.js` |
| Form sections (`.form-section`) | Groups related fields into card-style sections on profile, resource form, and org registration pages |

### Category and status badge colours

Category badges use a CSS attribute selector pattern — no extra Python required:

```html
<span class="category-badge" data-cat="{{ r.category.value }}">Equipment</span>
```

```css
[data-cat="equipment"] { background: var(--cat-equipment-bg); color: var(--cat-equipment-color); }
```

Status badges use global classes: `.status-badge` combined with `.badge-active`, `.badge-pending`, `.badge-frozen`, `.badge-rejected`, `.badge-cancelled`, or `.badge-suspended`.

---

## Starting the application

### Prerequisites

- Python 3.12+
- PostgreSQL (running in Docker or locally)
- [uv](https://github.com/astral-sh/uv) for dependency management
- A [Resend](https://resend.com) account and API key (for email delivery)

### First-time setup

```bash
# 1. Clone the repository
git clone <repo-url> makerspace_booking_system
cd makerspace_booking_system

# 2. Copy and configure environment variables
cp .env.example .env
# Edit .env — set DATABASE_URL, SECRET_KEY, RESEND_API_KEY, RESEND_FROM_EMAIL
# Also set FLASK_CONFIG=development (required for subdomain routing in dev)

# 3. Install dependencies (choose one)
# With uv (recommended — faster):
uv venv && uv pip install -r requirements.txt
# Or with plain pip:
python -m venv .venv && .venv/bin/pip install -r requirements.txt

# 4. Create the development database
createdb makerspace
# or via Docker:
# docker exec <container> psql -U <user> -c "CREATE DATABASE makerspace;"

# 5. Apply migrations
flask db upgrade

# 6. (Optional) Seed the database with two demo tenants and sample data
flask seed-db
```

### Local subdomain routing

The `DevelopmentConfig` uses `lvh.me` as the apex host — a public DNS name that always resolves to `127.0.0.1`. This means subdomain routing works in development without editing `/etc/hosts`.

**`FLASK_CONFIG=development` must be set in your `.env`.** Without it, `create_app()` loads `ProductionConfig`, which has no `SERVER_NAME` and cannot route subdomains.

With seed data loaded:

| URL | What you see |
|---|---|
| `http://lvh.me:5000` | Landing page (lists acme and widgetco) |
| `http://acme.lvh.me:5000` | Acme Makerspace tenant |
| `http://widgetco.lvh.me:5000` | Widgetco Makerspace tenant |
| `http://app.lvh.me:5000/super/login` | Super-admin console |

### Environment variables

| Variable | Description |
|----------|-------------|
| `FLASK_APP` | Entry point — set to `wsgi.py` |
| `FLASK_CONFIG` | Config profile: `development`, `testing`, or `production` |
| `SECRET_KEY` | Flask session signing key |
| `DATABASE_URL` | PostgreSQL connection string |
| `TEST_DATABASE_URL` | PostgreSQL connection string for tests |
| `RESEND_API_KEY` | API key from resend.com |
| `RESEND_FROM_EMAIL` | Sender address for outgoing emails |
| `REMINDER_INTERVAL_HOURS` | How often the reminder job runs (default `1`) |
| `REMINDER_HOURS_BEFORE` | How many hours before a booking to send reminder (default `24`) |
| `NAGER_DATE_COUNTRY` | ISO country code for public holiday checks (default `AU`) |
| `RUN_SCHEDULER` | Set to `0` to disable the in-process reminder scheduler (default `1`) |
| `APEX_HOST` | Base domain (default `makerbooking.com`; `lvh.me` in development) |
| `SUPER_ADMIN_HOST` | Super-admin console hostname (default `app.<APEX_HOST>`) |
| `APP_VERSION` | Version string displayed in the admin footer (default reads `VERSION` file; baked into Docker image in prod) |
| `CLOUDFLARE_API_TOKEN` | Required in production for wildcard TLS via Caddy DNS-01 challenge |

### Running the dev server

```bash
flask run
```

The app is available at `http://lvh.me:5000` (development config). The `.env` file is loaded automatically by `wsgi.py` via `python-dotenv`.

---

## Flask commands

| Command | Description |
|---------|-------------|
| `flask db upgrade` | Apply all pending migrations |
| `flask seed-db` | Create two demo tenants (`acme`, `widgetco`) with sample users and resources. Idempotent. |
| `flask create-admin --tenant-subdomain <subdomain>` | Create an admin user for a specific tenant |
| `flask create-super-admin` | Create the platform super-admin (tenant_id=NULL, is_super_admin=True) |
| `flask delete-seed-users` | Remove seed test users across all tenants |

---

## Running the reminder job

The reminder job sends a "your booking is in N hours" email to each member ahead of their booking. In development it runs **in-process** alongside the web server — no extra command needed.

### Default (in-process)

When you run `flask run`, the in-process APScheduler starts automatically. It polls every `REMINDER_INTERVAL_HOURS` and emails members whose booking starts in `REMINDER_HOURS_BEFORE` hours.

| Variable | Effect |
|----------|--------|
| `REMINDER_INTERVAL_HOURS` | How often the job checks for due reminders (default `1`) |
| `REMINDER_HOURS_BEFORE` | How many hours before a booking the email is sent (default `24`) |
| `NAGER_DATE_COUNTRY` | Reminders for bookings that fall on a public holiday in this country are skipped (default `AU`) |
| `RUN_SCHEDULER` | Set to `0` to suppress the in-process scheduler |

### Standalone scheduler process

To mirror the production layout (a separate `scheduler` container):

```bash
# Terminal 1 — web only, no in-process scheduler
RUN_SCHEDULER=0 flask run

# Terminal 2 — scheduler only
python -m app.scheduler
```

---

## Running the unit tests

### One-time test database setup

```bash
createdb makerspace_test
# or via Docker: docker exec <container> psql -U <user> -c "CREATE DATABASE makerspace_test;"
```

Make sure `TEST_DATABASE_URL` is set in `.env`.

### Run all tests

```bash
.venv/bin/python -m pytest tests/ -v
```

Run a specific test file or directory:

```bash
.venv/bin/python -m pytest tests/tenancy/ -v
.venv/bin/python -m pytest tests/auth/test_login.py -v
```

---

## Available routes

### Public (apex host: `lvh.me:5000` in dev, `makerbooking.com` in prod)

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/` | Landing page — lists active, publicly-listed tenant organisations |
| GET | `/register/org` | Organisation self-signup form |
| POST | `/register/org` | Create new org + first admin (tenant status: pending) |
| GET | `/auth/reset-password/<token>` | Password reset form (token valid 1 hour) |
| POST | `/auth/reset-password/<token>` | Submit new password; redirects to tenant login |

### Super-admin (host: `app.lvh.me:5000` in dev, `app.makerbooking.com` in prod)

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/super/login` | Super-admin login form |
| POST | `/super/login` | Authenticate super-admin |
| POST | `/super/logout` | Log out super-admin |
| GET | `/super/` | Dashboard — all tenants, member counts, lifecycle actions |
| POST | `/super/tenants/<id>/approve` | Activate tenant + first admin; send approval email |
| POST | `/super/tenants/<id>/reject` | Reject (suspend) tenant; send rejection email |
| POST | `/super/tenants/<id>/suspend` | Suspend an active tenant |
| POST | `/super/tenants/<id>/toggle_listed` | Toggle landing-page visibility |

### Tenant: Unauthenticated (host: `<subdomain>.lvh.me:5000`)

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/auth/login` | Login form |
| POST | `/auth/login` | Submit login (rate-limited: 5/min) |
| GET | `/auth/register` | Registration form |
| POST | `/auth/register` | Submit registration (account starts as pending) |
| GET | `/auth/forgot-password` | Request a password reset link |
| POST | `/auth/forgot-password` | Send reset email via Resend |

### Tenant: Member (active users)

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/home` | Resource browser with category filter |
| GET | `/resources/<id>/book` | Booking form for a resource |
| POST | `/resources/<id>/book` | Create booking (conflict detection) |
| GET | `/my-bookings` | Upcoming and past bookings |
| GET/POST | `/bookings/<id>/edit` | Edit booking (max 2 time edits; unlimited comment edits) |
| POST | `/bookings/<id>/cancel` | Cancel booking (≥1 hour before start) |
| GET/POST | `/profile` | Edit display name, email, password, avatar |
| POST | `/auth/logout` | Log out |

### Tenant: Admin

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/admin` | Admin dashboard |
| GET | `/admin/audit-log` | Audit log (19 event types) |
| GET | `/admin/resources` | Resource list |
| GET/POST | `/admin/resources/new` | Create resource |
| GET/POST | `/admin/resources/<id>/edit` | Edit resource (incl. thumbnail upload) |
| POST | `/admin/resources/<id>/archive` | Archive (soft-delete) resource |
| GET | `/admin/members` | Member list with status badges |
| POST | `/admin/members/<id>/approve` | Approve pending member |
| GET/POST | `/admin/members/<id>/reject` | Reject member |
| POST | `/admin/members/<id>/freeze` | Freeze active member |
| POST | `/admin/members/<id>/unfreeze` | Unfreeze frozen member |
| GET/POST | `/admin/members/<id>/edit` | Edit member details |
| GET | `/admin/bookings` | All bookings |
| GET/POST | `/admin/bookings/<id>/edit` | Edit any booking (no edit-count cap) |
| POST | `/admin/bookings/<id>/cancel` | Cancel booking and notify member |

---

## Seed data

`flask seed-db` creates two demo tenants with identical sample data:

| Tenant | Subdomain | Admin | Members |
|--------|-----------|-------|---------|
| Acme Makerspace | `acme` | `admin@acme.example.com` / `adminpass` | `alice@acme.example.com`, `bob@acme.example.com` |
| Widgetco Makerspace | `widgetco` | `admin@widgetco.example.com` / `adminpass` | `alice@widgetco.example.com`, `bob@widgetco.example.com` |

Each tenant gets 10 resources spanning all 5 categories (meeting room, equipment, workbench, hot spot, book).

The command is idempotent — re-running it skips records that already exist.

---

## Version history

- **2.1.0** — full front-end overhaul with the "Maker Forge" design language. Space Grotesk + Inter typography via Google Fonts; CSS custom-property token system (brand indigo, amber CTAs, deep-slate nav); resource card grid replacing the flat member table; auth split-panel layout; timeline component for audit logs; mobile hamburger nav; tab UI for My Bookings; stat summary cards for the super-admin dashboard. Zero Python or route modifications — purely presentational.

- **2.0.0** — multi-tenancy refactor. Each organisation is isolated by subdomain; all queries scoped by `tenant_id`; cross-tenant PK leakage prevented by `get_for_tenant_or_404`. New public blueprint (landing page, org self-signup, apex-hosted password reset). New super-admin blueprint at `app.makerbooking.com` for tenant lifecycle management. Two-phase migration strategy for zero-downtime schema changes. Wildcard TLS via Caddy with Cloudflare DNS-01 challenge. 301 tests.

- **1.0.0** — first production-ready release. Member auth with admin approval, resource CRUD with thumbnails and weekday/weekend availability windows, booking flow with conflict detection and edit/cancel rules (max 2 time edits, ±60 min grace, 1-hour cancellation cutoff), admin dashboards for members/resources/bookings, 19-event audit log, password reset by email, and booking reminder emails with public-holiday skip.
