# Makerspace Booking System — Specification (v1)

This document is the formal specification for v1 of the Makerspace Booking System. It is derived from [brainstorm.md](brainstorm.md) and resolves every open item listed in brainstorm §11. Implementation must conform to this spec; deviations require a spec amendment.

---

## §1. Overview & Glossary

The Makerspace Booking System is a single-location, single-timezone web application that lets approved **members** of a makerspace browse and reserve shared **resources** — rooms, equipment, workbenches, coworking desks, and books — within policies set by **administrators**. The system enforces clearances on risk-bearing equipment, prevents double-booking through deterministic conflict detection, and sends transactional email for confirmations, reminders, and overdue notices.

**Glossary**

- **Member** — an approved end-user who can browse and book.
- **Administrator (admin)** — a member with elevated privileges; flat tier in v1.
- **Category** — a group of resources sharing the same booking policy (e.g., "Meeting rooms", "Books").
- **Resource** — an individually bookable item belonging to exactly one category.
- **Clearance** — a named permission attached to a member; required by some resources to book them.
- **Booking** — a held reservation by one member of one resource for one time interval.
- **Loan** — a booking on a `DAYS`-unit category (books); ends when an admin marks the item returned.
- **Time-slotted** — bookings measured in hours, bound by opening hours.
- **Date-range** — bookings measured in days, not bound by opening hours.
- **Audit event** — an immutable record of an admin-only state change.

---

## §2. Technology Stack

| Concern | Choice |
|---|---|
| Language / runtime | Python 3.12 |
| Web framework | Flask 3.x |
| ORM | SQLAlchemy 2.x via Flask-SQLAlchemy |
| Database | PostgreSQL 16 |
| Migrations | Alembic via Flask-Migrate |
| Auth | Flask-Login (server sessions) + passlib/bcrypt password hashing |
| Templating | Jinja2 + HTMX (progressive enhancement, no SPA) |
| Forms / CSRF | Flask-WTF + WTForms |
| Background jobs | APScheduler in-process; abstracted behind a `Scheduler` interface so a future Celery/RQ swap requires no domain-code changes |
| Email | **Resend API** via the `resend` Python SDK; sender wrapped behind a `Mailer` interface (prod = Resend, dev/test = console / in-memory). `RESEND_API_KEY` and `RESEND_FROM` from environment. |
| Rate limiting | Flask-Limiter |
| Tests | pytest + factory-boy |

All third-party effects (email, scheduling, password hashing) are accessed through narrow interfaces so tests can replace them without monkey-patching internals.

---

## §3. Roles & Permissions Matrix

The permission check for every protected action routes through a single `policy(actor, action, subject)` helper. The matrix below is exhaustive for v1.

| Action | Anon | Member | Admin | Notes |
|---|---|---|---|---|
| Register (self) | ✓ | — | — | |
| Log in | ✓ | ✓ | ✓ | |
| View resources | — | ✓ | ✓ | |
| Create booking (self) | — | ✓ (`status=active`) | ✓ | Frozen/pending/rejected blocked |
| Edit own booking | — | ✓ | ✓ | Per §9.3 |
| Edit any booking | — | — | ✓ | |
| Cancel own booking | — | ✓ | ✓ | |
| Cancel any booking | — | — | ✓ | Audited |
| Comment on own booking | — | ✓ | ✓ | |
| Update own notification prefs | — | ✓ | ✓ | |
| Approve / reject pending member | — | — | ✓ | Audited |
| Freeze / unfreeze member | — | — | ✓ | Self-freeze rejected; last-admin protected |
| Elevate member to admin | — | — | ✓ | Audited |
| Demote admin to member | — | — | ✓ | Cannot demote self if last admin; audited |
| Grant / remove clearance | — | — | ✓ | Audited |
| CRUD clearance types | — | — | ✓ | Audited |
| CRUD categories | — | — | ✓ | Audited |
| Clone category | — | — | ✓ | Audited |
| CRUD resources | — | — | ✓ | Audited |
| Toggle resource out-of-service | — | — | ✓ | Triggers cascade (§9.5); audited |
| Mark book returned | — | — | ✓ | |
| CRUD opening hours | — | — | ✓ | Audited |
| CRUD closures | — | — | ✓ | Audited |
| Update system settings | — | — | ✓ | Audited |
| View audit log | — | — | ✓ | Read-only |
| View reports | — | — | ✓ | |

**Explicit clarifications** (from brainstorm §11):

- An admin **cannot freeze themselves** under any circumstance — universal rule, simpler than reasoning about self-induced lockouts.
- An admin **cannot demote themselves** if they are the sole admin (last-admin protection).
- An admin **can** demote themselves to member if at least one other admin remains.
- An admin **can** cancel their own bookings the same way a regular member can.

---

## §4. Feature List by Role

### §4.1 Member features

- **F-M01** Self-register with email + password → §9.2
- **F-M02** Log in and out
- **F-M03** Browse resources, filtered by category and an availability window → §9.11
- **F-M04** View resource detail with availability slot picker → §9.11
- **F-M05** Create a booking (time-slotted or date-range) → §9.1
- **F-M06** Hold multiple overlapping bookings across *different* resources → §9.1
- **F-M07** Edit a booking's start/end time within limits → §9.3
- **F-M08** Edit a booking's comment without limits → §9.3
- **F-M09** Cancel an active booking before its start → §9.4
- **F-M10** Borrow books by date range → §9.7
- **F-M11** Manage notification opt-outs by email type → §9.8
- **F-M12** View own booking history (active, past, cancelled)

### §4.2 Administrator features

- **F-A01** Approve, reject pending registrations → §9.2
- **F-A02** Freeze / unfreeze member accounts → §9.6
- **F-A03** View any member's bookings, cancellation history, and clearances
- **F-A04** Elevate any member to admin; demote any admin → §9.6
- **F-A05** Grant or remove clearances from a member
- **F-A06** CRUD clearance types
- **F-A07** CRUD resource categories; **clone** a category's settings
- **F-A08** CRUD resources within a category
- **F-A09** Toggle a resource out-of-service (with cascade) → §9.5
- **F-A10** Configure weekly opening hours and one-off closures
- **F-A11** Configure system-wide notification timing and edit-grace window
- **F-A12** Mark a returned book as available → §9.7
- **F-A13** Cancel any member's booking (manual cancellation) → §9.4
- **F-A14** View the audit log → §9.10
- **F-A15** View built-in reports → §9.9

---

## §5. Data Model

### §5.1 Entity overview

```
users ─┬─< user_clearances >─ clearance_types
       │
       └─< bookings >── resources >── categories
                                    └──< resource_required_clearances >─ clearance_types

opening_hours          closures           system_settings (singleton)
audit_events           notification_log   scheduled_jobs
```

### §5.2 Tables

All tables have surrogate integer PK `id` and `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` unless noted. Timestamps are stored UTC.

#### `users`

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| email | citext NOT NULL UNIQUE | |
| password_hash | text NOT NULL | bcrypt cost 12 |
| display_name | text NOT NULL | |
| status | enum(`pending`,`active`,`frozen`,`rejected`) NOT NULL | default `pending` |
| is_admin | bool NOT NULL DEFAULT false | |
| rejection_note | text | populated only when status=`rejected` |
| notification_prefs | jsonb NOT NULL DEFAULT `'{}'::jsonb` | map of `notification_type → bool` (missing key = opted in) |
| tier_id | bigint NULL | **Reserved** for future tiered membership; no FK target yet |
| approved_at | timestamptz NULL | |
| created_at | timestamptz | |

#### `clearance_types`

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| name | text NOT NULL UNIQUE | e.g., "Laser cutter", "Lathe" |
| description | text | |

#### `user_clearances`

| Column | Type | Notes |
|---|---|---|
| user_id | bigint FK users(id) | |
| clearance_type_id | bigint FK clearance_types(id) | |
| granted_at | timestamptz NOT NULL | |
| granted_by_user_id | bigint FK users(id) | |
| expires_at | timestamptz NULL | **Reserved** for future clearance expiry |

Composite PK `(user_id, clearance_type_id)`.

#### `categories`

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| name | text NOT NULL UNIQUE | |
| booking_unit | enum(`HOURS`,`DAYS`) NOT NULL | |
| subject_to_opening_hours | bool NOT NULL | |
| identifier_label | text NULL | e.g., "Serial No.", "ISBN" |
| booking_horizon_days | int NOT NULL | |
| buffer_gap_minutes | int NOT NULL DEFAULT 0 | applies to HOURS only |
| min_duration_minutes | int NOT NULL | |
| max_duration_minutes | int NOT NULL | |
| reminder_hours_before | int NULL | HOURS-only |
| due_soon_offsets_days | int[] NOT NULL DEFAULT `'{1,3}'` | DAYS-only |
| overdue_offsets_days | int[] NOT NULL DEFAULT `'{1,3}'` | DAYS-only |
| location_id | bigint NULL | **Reserved** for future multi-location |

#### `resources`

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| category_id | bigint FK categories(id) NOT NULL | |
| name | text NOT NULL | |
| description | text | |
| identifier_value | text NULL | required iff `categories.identifier_label IS NOT NULL` |
| state | enum(`available`,`out_of_service`) NOT NULL DEFAULT `available` | |

#### `resource_required_clearances`

`(resource_id, clearance_type_id)` composite PK; FKs to both parents.

#### `bookings`

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| user_id | bigint FK users(id) NOT NULL | |
| resource_id | bigint FK resources(id) NOT NULL | |
| starts_at | timestamptz NOT NULL | UTC |
| ends_at | timestamptz NOT NULL | UTC; check `ends_at > starts_at` |
| status | enum(`active`,`cancelled_by_member`,`cancelled_by_admin`,`cancelled_downtime`,`completed`,`returned`) NOT NULL DEFAULT `active` | `completed` for past HOURS bookings; `returned` for DAYS bookings closed by admin |
| edit_count | smallint NOT NULL DEFAULT 0 | |
| original_starts_at | timestamptz NOT NULL | captured at create time |
| original_ends_at | timestamptz NOT NULL | |
| comment | text NULL | one-shot member message to admin |
| cancelled_at | timestamptz NULL | |
| cancelled_by_user_id | bigint FK users(id) NULL | |
| returned_at | timestamptz NULL | DAYS bookings only |
| recurrence_id | bigint NULL | **Reserved** for future recurring bookings |

Indexes:
- `(resource_id, starts_at, ends_at)`
- partial index `WHERE status = 'active'` on `(resource_id, starts_at, ends_at)` for the conflict query

#### `opening_hours`

One row per weekday (0=Mon..6=Sun).

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| weekday | smallint NOT NULL UNIQUE | 0..6 |
| opens_at | time NULL | |
| closes_at | time NULL | |
| is_closed | bool NOT NULL DEFAULT false | |
| location_id | bigint NULL | **Reserved** for multi-location |

#### `closures`

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| date_from | date NOT NULL | |
| date_to | date NOT NULL | inclusive |
| reason | text | |

#### `system_settings`

Singleton row enforced by a `CHECK (id = 1)` constraint.

| Column | Type | Default |
|---|---|---|
| id | smallint PK | always 1 |
| edit_grace_minutes | int | 60 |
| reminder_lead_hours | int | 24 |
| due_soon_offsets_days | int[] | `{1,3}` |
| overdue_offsets_days | int[] | `{1,3}` |
| escalation_after_days | int | 7 |

#### `audit_events`

Append-only. Application DB role is granted `INSERT, SELECT` only — no `UPDATE` or `DELETE`.

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| actor_user_id | bigint FK users(id) NULL | NULL for system actions (e.g., bootstrap) |
| action | text NOT NULL | controlled enum string, see §9.10 |
| subject_type | text NOT NULL | `user`, `resource`, `category`, `booking`, `clearance_type`, `system` |
| subject_id | bigint NULL | |
| payload | jsonb NOT NULL DEFAULT `'{}'::jsonb` | before/after values where relevant |
| created_at | timestamptz NOT NULL DEFAULT now() | |

#### `notification_log`

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| user_id | bigint FK users(id) | |
| booking_id | bigint FK bookings(id) NULL | |
| type | text NOT NULL | see notification taxonomy in §9.8 |
| sent_at | timestamptz NOT NULL | |
| status | enum(`sent`,`failed`,`suppressed`) NOT NULL | |
| provider_message_id | text NULL | Resend's message id when available |

#### `scheduled_jobs`

Durable queue for reminders / due-soon / overdue / escalation; survives restarts.

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| kind | enum(`reminder`,`due_soon`,`overdue`,`escalation`) | |
| booking_id | bigint FK bookings(id) | |
| fire_at | timestamptz NOT NULL | |
| fired_at | timestamptz NULL | |

Index on `(fire_at) WHERE fired_at IS NULL`.

### §5.3 Reserved columns for deferred features

Reserved columns sit unused in v1 but are present in the schema so future migrations are additive only:

| Future feature (brainstorm §10) | Reserved seam |
|---|---|
| Tiered membership | `users.tier_id` |
| Recurring bookings | `bookings.recurrence_id` |
| Multi-location | `categories.location_id`, `opening_hours.location_id` |
| Clearance expiry | `user_clearances.expires_at` |
| Waitlists | `bookings.status` is an enum that can grow a `waitlisted` value |

### §5.4 Books with multiple copies

Each physical copy is an independent `resources` row (sharing category=Books, sharing or differing on `identifier_value`/ISBN). The Browse UI groups by `(title := resources.name, isbn := identifier_value)` and presents a copy picker. The data model has no notion of "title group" in v1.

---

## §6. Route Table

Routes are organised under Flask blueprints. All non-`anon` routes require an authenticated session; `member` further requires `status='active'`; `admin` further requires `is_admin=true`; `owner-or-admin` allows the booking's owner OR any admin. CSRF is required on every state-changing request.

### §6.1 Public / auth blueprint (`/auth`)

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/` | anon | Landing → redirects to login or `/resources` |
| GET, POST | `/auth/register` | anon | Self-registration |
| GET, POST | `/auth/login` | anon | Session login |
| POST | `/auth/logout` | member | End session |
| GET | `/auth/pending` | logged-in pending user | "Awaiting approval" page |

### §6.2 Member blueprint

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/resources` | member | Browse, filter by `?category=&from=&to=` |
| GET | `/resources/<id>` | member | Resource detail |
| GET | `/resources/<id>/slots` | member | HTMX partial: available slots on a given date (`?date=YYYY-MM-DD`) |
| GET, POST | `/resources/<id>/book` | member | Create booking |
| GET | `/bookings` | member | My bookings (upcoming + past) |
| GET | `/bookings/<id>` | owner-or-admin | Booking detail |
| GET, POST | `/bookings/<id>/edit` | owner-or-admin | Edit time or comment |
| POST | `/bookings/<id>/cancel` | owner-or-admin | Cancel |
| GET, POST | `/account/notifications` | member | Manage opt-outs |

### §6.3 Admin blueprint (`/admin`)

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/admin` | admin | Dashboard (pending approvals count, today's bookings, overdue books) |
| GET | `/admin/members` | admin | Member roster, filter by status |
| GET | `/admin/members/<id>` | admin | Member detail |
| POST | `/admin/members/<id>/approve` | admin | Approve pending |
| POST | `/admin/members/<id>/reject` | admin | Reject with note |
| POST | `/admin/members/<id>/freeze` | admin | Freeze account |
| POST | `/admin/members/<id>/unfreeze` | admin | Unfreeze account |
| POST | `/admin/members/<id>/elevate` | admin | Promote to admin |
| POST | `/admin/members/<id>/demote` | admin | Demote from admin |
| POST | `/admin/members/<id>/clearances` | admin | Grant a clearance |
| DELETE | `/admin/members/<id>/clearances/<ct_id>` | admin | Remove a clearance |
| POST | `/admin/bookings/<id>/cancel` | admin | Admin-cancel a booking |
| GET, POST | `/admin/clearances` | admin | List + create clearance types |
| GET, POST, DELETE | `/admin/clearances/<id>` | admin | Edit / delete clearance type |
| GET, POST | `/admin/categories` | admin | List + create categories |
| GET, POST | `/admin/categories/<id>` | admin | Edit category |
| POST | `/admin/categories/<id>/clone` | admin | Clone settings into new category |
| GET, POST | `/admin/categories/<id>/resources` | admin | List + create resources in category |
| GET, POST | `/admin/resources/<id>` | admin | Edit resource |
| POST | `/admin/resources/<id>/out-of-service` | admin | Mark out-of-service (cascade) |
| POST | `/admin/resources/<id>/restore` | admin | Mark available again |
| POST | `/admin/bookings/<id>/return` | admin | Mark book returned |
| GET, POST | `/admin/opening-hours` | admin | Weekly hours |
| GET, POST | `/admin/closures` | admin | List + create closures |
| DELETE | `/admin/closures/<id>` | admin | Remove a closure |
| GET, POST | `/admin/settings` | admin | System-wide settings |
| GET | `/admin/audit` | admin | Audit log (paginated, filterable by action/subject) |
| GET | `/admin/reports/cancellations` | admin | Cancellations report (`?from=&to=`) |
| GET | `/admin/reports/edits` | admin | Booking edits report |
| GET | `/admin/reports/resource-history` | admin | Members who booked a given resource (`?resource_id=&from=&to=`) |
| GET | `/admin/reports/late-returns` | admin | Late book returns by member |

### §6.4 HTMX partials

Any path ending in `/slots`, or returning a fragment, sets `HX-Trigger`/`HX-Reswap` headers as needed. Slot picker response:

```json
{
  "date": "2026-06-12",
  "slots": [
    { "starts_at": "2026-06-12T09:00:00Z", "ends_at": "2026-06-12T10:00:00Z", "available": true },
    { "starts_at": "2026-06-12T10:00:00Z", "ends_at": "2026-06-12T11:00:00Z", "available": false, "reason": "booked" }
  ]
}
```

Renders as an HTML partial in production; the JSON shape above is the contract for the template.

---

## §7. Default Values

### §7.1 Seeded categories

`flask seed` populates these five categories with the following values. Admins may edit them post-install.

| Category | Unit | Hours-bound | Identifier | Horizon (days) | Min | Max | Buffer | Reminder |
|---|---|---|---|---|---|---|---|---|
| Meeting rooms | HOURS | yes | — | 14 | 60 min | 240 min | 15 min | 24 h before |
| Equipment | HOURS | yes | Serial No. | 14 | 30 min | 480 min | 15 min | 24 h before |
| Workbenches | HOURS | yes | — | 7 | 60 min | 600 min (10 h) | 0 min | 12 h before |
| Hot spots | HOURS | yes | — | 7 | 60 min | 600 min | 0 min | 12 h before |
| Books | DAYS | no | ISBN | 30 | 1 day | 14 days | — | due-soon `[1,3]`, overdue `[1,3]`, escalate at 7 |

### §7.2 Seeded opening hours

| Weekday | Opens | Closes |
|---|---|---|
| Mon–Fri | 09:00 | 18:00 |
| Sat | 10:00 | 16:00 |
| Sun | closed | — |

### §7.3 Seeded system settings

| Key | Value |
|---|---|
| `edit_grace_minutes` | 60 |
| `reminder_lead_hours` | 24 |
| `due_soon_offsets_days` | `[1, 3]` |
| `overdue_offsets_days` | `[1, 3]` |
| `escalation_after_days` | 7 |

### §7.4 Seeded clearance types

None. The fixture leaves `clearance_types` empty; admins create them as needed.

---

## §8. Bootstrap & First-Admin Procedure

1. **Install.** `pip install -r requirements.txt`, set environment variables (`DATABASE_URL`, `SECRET_KEY`, `RESEND_API_KEY`, `RESEND_FROM`, `APP_TIMEZONE`).
2. **Migrate.** `flask db upgrade` runs Alembic migrations to the current head.
3. **Seed.** `flask seed` populates categories, opening hours, and system settings as in §7. Idempotent — re-running has no effect if rows exist.
4. **First admin.** `flask create-admin --email <e>` prompts twice for a password (min 10 chars), creates a user with `status='active'`, `is_admin=true`, and writes one audit event:
   - `actor_user_id = NULL`, `action = 'admin_bootstrap'`, `subject_type='user'`, `subject_id=<new id>`.
5. **First login.** The bootstrap admin logs in via the normal `/auth/login` flow. Subsequent admins are elevated through the UI.

The bootstrap command refuses to run if any user already exists with `is_admin=true`.

---

## §9. Acceptance Criteria

Every v1 feature in §4 has an acceptance subsection below. Each uses **Given / When / Then** form. The conflict-detection section (§9.1) is the most detailed.

### §9.1 Conflict detection (centerpiece)

A candidate booking `C` of resource `R` over the half-open interval `[C.starts_at, C.ends_at)` made by user `U` is **accepted** only if every rule below holds. Otherwise it is rejected with a specific error.

#### Rules

**R1 — Same-resource overlap.**
- Reject if there exists an `active` booking `B` on `R` with `B.starts_at < C.ends_at AND B.ends_at > C.starts_at`.
- Half-open intervals: back-to-back bookings where `B.ends_at == C.starts_at` do **not** overlap.

**R2 — Buffer gap (HOURS only).**
- Reject if any `active` booking `B` on `R` exists with `0 < |C - B gap| < category.buffer_gap_minutes` (taking the gap as the time between the latter's start and the former's end, in whichever order).
- Does not apply to DAYS categories.

**R3 — Opening hours.**
- For categories with `subject_to_opening_hours=true`: every minute of `[C.starts_at, C.ends_at)` must fall within an `opening_hours` open window for its weekday AND must not fall within any `closures` row.
- DAYS-unit categories with `subject_to_opening_hours=false` (books) bypass this rule.

**R4 — Booking horizon.**
- Reject if `C.starts_at > now() + category.booking_horizon_days`.
- No minimum lead time: spontaneous bookings starting "now + 5 minutes" are allowed.

**R5 — Min/max duration.**
- Reject if `(C.ends_at - C.starts_at) < category.min_duration_minutes` OR `> category.max_duration_minutes`.

**R6 — Clearances.**
- Reject if `R.required_clearances ⊄ U.clearances`.

**R7 — Resource state.**
- Reject if `R.state != 'available'`.

**R8 — Member status.**
- Reject if `U.status != 'active'`. (`pending`, `frozen`, `rejected` all blocked.)

**R9 — Atomicity / concurrency.**
- All checks plus the INSERT execute inside a single transaction at isolation `REPEATABLE READ` or stronger, with `SELECT ... FOR UPDATE` taken on the candidate-overlapping rows in `bookings (resource_id, starts_at, ends_at)`.
- On serialization failure, retry once. If the second attempt also fails, return a 409 with a friendly "try again" message.
- This guarantees two simultaneous requests for the same slot cannot both succeed.

**R10 — Edit re-validation.**
- A time-edit re-runs R1–R8 against the *new* `[starts_at, ends_at)`, plus the edit limits in §9.3.

#### Worked examples

**Same-resource overlap (R1)**

> *Given* an `active` booking of resource X for 14:00–15:00,
> *When* user Y submits a booking of resource X for 14:30–15:30,
> *Then* the system rejects with "This slot conflicts with an existing booking."

**Back-to-back (R1, accepted)**

> *Given* an `active` booking of resource X for 14:00–15:00 and X's category buffer_gap=0,
> *When* user Y submits a booking of resource X for 15:00–16:00,
> *Then* the booking is accepted.

**Buffer gap (R2)**

> *Given* an `active` booking of resource X for 14:00–15:00 and X's category buffer_gap=15 min,
> *When* user Y submits a booking of resource X for 15:10–16:00,
> *Then* the system rejects with "Requires a 15-minute gap from the booking ending at 15:00."

**Opening hours (R3)**

> *Given* Sunday is closed and category Meeting rooms is hours-bound,
> *When* user Y submits a booking of a meeting room for Sunday 10:00–11:00,
> *Then* the system rejects with "The makerspace is closed at that time."

**Closure (R3)**

> *Given* a closure on 2026-12-25,
> *When* user Y books a workbench for 2026-12-25 11:00–12:00,
> *Then* the system rejects with "The makerspace is closed at that time."

**Horizon (R4)**

> *Given* Meeting rooms horizon=14 days and today is 2026-06-01,
> *When* user Y books a meeting room for 2026-06-20 10:00–11:00,
> *Then* the system rejects with "You can only book up to 14 days ahead."

**Duration (R5)**

> *Given* Equipment min=30 min,
> *When* user Y books a soldering station for 14:00–14:15,
> *Then* the system rejects with "Minimum booking is 30 minutes."

**Clearances (R6)**

> *Given* the laser cutter requires the "Laser cutter" clearance and user Y does not hold it,
> *When* user Y books the laser cutter,
> *Then* the system rejects with "You don't hold the required clearance: Laser cutter."

**Resource state (R7)**

> *Given* resource X is `out_of_service`,
> *When* any member tries to book X,
> *Then* X does not appear in `/resources` Browse and a direct POST is rejected with "This resource is currently out of service."

**Member status (R8)**

> *Given* user Y is `frozen`,
> *When* Y submits any booking,
> *Then* the system rejects with "Your account is currently frozen. Contact an administrator."

**Concurrency (R9)**

> *Given* one open slot on resource X at 14:00–15:00,
> *When* two members submit competing bookings for that slot simultaneously,
> *Then* exactly one is accepted and the other receives "This slot conflicts with an existing booking."

**Overlap across resources is allowed**

> *Given* user Y holds a booking on workbench A for 14:00–16:00,
> *When* Y books oscilloscope B for 14:30–15:30,
> *Then* the booking is accepted (R1 is per-resource, not per-member).

### §9.2 Self-registration → approval

- *Given* an anonymous visitor, *When* they POST `/auth/register` with a valid email + password, *Then* a `users` row is created with `status='pending'`; no session cookie is issued; the user is shown the "Awaiting approval" page.
- *Given* a pending user, *When* an admin POSTs `/admin/members/<id>/approve`, *Then* status becomes `active`, `approved_at` is set, an approval email is sent via Resend, and an `audit_events` row is written (`action='member_approved'`).
- *Given* a pending user, *When* an admin POSTs `/admin/members/<id>/reject` with a `note`, *Then* status becomes `rejected`, `rejection_note` is stored, a rejection email is sent, and an audit event is written.
- *Given* a rejected applicant with stored `rejection_note`, *When* the same email re-registers, *Then* the existing row's status returns to `pending` (notes retained); the admin member-detail page displays prior `rejection_note` text in a "Previous rejection" block.

### §9.3 Booking edits

- **Time edit limit.** *Given* `bookings.edit_count < 2`, *When* the member submits new `starts_at`/`ends_at` whose new `starts_at` is within `±system_settings.edit_grace_minutes` of the *current* `starts_at`, *Then* R1–R8 are re-evaluated; on success the row updates and `edit_count` increments.
- **Comment-only edit.** *Given* a member submits a change to `comment` with `starts_at`/`ends_at` unchanged, *Then* the row updates and `edit_count` does **not** increment; the grace window does not apply.
- **Beyond limit.** *Given* `edit_count == 2`, *When* the member submits a time edit, *Then* the system rejects with "You've already edited this booking twice."
- **Outside grace window.** *Given* current `starts_at` is 14:00 and `edit_grace_minutes=60`, *When* the member submits new `starts_at=12:30`, *Then* the system rejects with "Edits must stay within 60 minutes of the current start time."
- **Edit causing conflict.** *Given* an edit would create a conflict per R1–R8, *Then* the edit is rejected with the same error that would apply to a fresh booking.

### §9.4 Cancellations

- *Given* an `active` booking with `starts_at > now()`, *When* the owner POSTs `/bookings/<id>/cancel`, *Then* status becomes `cancelled_by_member`, `cancelled_at` is set, and the cancellation appears in the member's history.
- *Given* an `active` booking, *When* an admin POSTs `/admin/bookings/<id>/cancel`, *Then* status becomes `cancelled_by_admin`, `cancelled_by_user_id` is the admin, a manual-cancellation email is sent to the booking's owner, and an audit event is written.
- *Given* `now() >= starts_at`, *When* a cancellation is attempted, *Then* the system rejects with "Past bookings cannot be cancelled."

### §9.5 Out-of-service cascade

- *Given* resource X is `available` with `N` active bookings whose `ends_at > now()`, *When* an admin POSTs `/admin/resources/<id>/out-of-service`, *Then* all `N` are set to `cancelled_downtime`, a downtime-cancellation email is queued for each affected member (subject to opt-out per §9.8), one audit event is written for the resource toggle, and X's `state` becomes `out_of_service`.
- *Given* X is `out_of_service`, *When* an admin POSTs `/admin/resources/<id>/restore`, *Then* X becomes `available`. Cancelled bookings are **not** auto-restored.

### §9.6 Last-admin protection & self-restrictions

- *Given* `users` has exactly one row with `is_admin=true`, *When* anyone (including that admin) attempts to demote or freeze that user, *Then* the system rejects with "Cannot demote the last administrator." / "Cannot freeze the last administrator."
- *Given* any admin A, *When* A attempts to freeze themselves, *Then* the system rejects with "You cannot freeze your own account." (universal rule).
- *Given* two or more admins exist, *When* one of them demotes themselves, *Then* the demotion succeeds and `is_admin=false`.

### §9.7 Book loans

- **Create.** *Given* category Books, *When* a member books copy C for `[date_from, date_to]` inclusive, *Then* a row is created with `starts_at` = `date_from` at 00:00 local, `ends_at` = `date_to` at 23:59:59 local (converted to UTC); R3 is skipped because `subject_to_opening_hours=false`.
- **Job scheduling.** On accept, `scheduled_jobs` rows are inserted for each `due_soon_offsets_days` (e.g., `date_to - 3` and `date_to - 1`) and each `overdue_offsets_days` (`date_to + 1`, `date_to + 3`), plus one `escalation` job at `date_to + escalation_after_days`.
- **Marking returned.** *Given* a DAYS booking, *When* an admin POSTs `/admin/bookings/<id>/return`, *Then* status becomes `returned`, `returned_at = now()`, and all unfired `scheduled_jobs` for that booking are deleted.
- **Escalation.** *Given* a DAYS booking still active at `escalation_after_days` past due, *When* the scheduler fires the escalation job, *Then* an email is sent to every admin and a `notification_log` entry is written.

### §9.8 Notifications & opt-outs

**Notification taxonomy** (keys for `notification_prefs`):

| Type | Critical? | Trigger |
|---|---|---|
| `registration_approved` | yes | Admin approves a pending member |
| `registration_rejected` | yes | Admin rejects a pending member |
| `booking_confirmation` | no | Booking accepted |
| `booking_reminder` | no | `reminder_lead_hours` before start (HOURS) |
| `book_due_soon` | no | At `due_soon_offsets_days` before `date_to` |
| `book_overdue` | no | At `overdue_offsets_days` after `date_to` |
| `book_escalation_admin` | yes | At `escalation_after_days` past due — sent to all admins |
| `downtime_cancellation` | yes | Resource taken out-of-service |
| `manual_cancellation` | yes | Admin-cancelled a member's booking |

**Rules:**

- *Given* `notification_prefs[type] == false`, *When* a non-critical notification of `type` would fire, *Then* it is skipped and a `notification_log` row is written with `status='suppressed'`.
- *Given* `notification_prefs[type] == false` for a **critical** type, *Then* the preference is ignored and the email is sent anyway.
- *Given* a member opts out of `booking_reminder`, *When* they view `/account/notifications`, *Then* a warning is shown: "You will not receive reminders. You are responsible for tracking your own bookings."
- All email send/failure outcomes write to `notification_log`. Provider message ids from Resend are stored when available.

### §9.9 Reports

Each report endpoint returns an HTML table and a CSV download (`?format=csv`). All accept `from` and `to` query parameters (ISO dates) where applicable.

- **Cancellations.** Lists bookings where `status IN ('cancelled_by_member','cancelled_by_admin','cancelled_downtime')` within `[from,to]`. Columns: member, resource, original interval, cancelled_at, status.
- **Booking edits.** Lists bookings where `edit_count > 0` and the booking was created or edited in `[from,to]`. Columns: member, resource, original→new interval, edit_count.
- **Resource history.** Given a `resource_id` and a window, lists every booking touching that window. Columns: member, interval, status.
- **Late returns.** Lists DAYS bookings where `(returned_at IS NULL AND now() > ends_at)` OR `(returned_at > ends_at)`. Columns: member, book, due date, returned_at (or "still out"), days late.

Each report renders within 2 s for a dataset of 10 000 bookings.

### §9.10 Audit log immutability

- The application's PostgreSQL role is granted **only** `INSERT, SELECT` on `audit_events`; `UPDATE` and `DELETE` are revoked. Any attempt to mutate raises a database error.
- The following admin-only actions write exactly one audit event each:

| Action constant | Triggered by |
|---|---|
| `admin_bootstrap` | First-admin CLI |
| `member_approved` | POST `/admin/members/<id>/approve` |
| `member_rejected` | POST `/admin/members/<id>/reject` |
| `member_frozen` | POST `/admin/members/<id>/freeze` |
| `member_unfrozen` | POST `/admin/members/<id>/unfreeze` |
| `member_elevated` | POST `/admin/members/<id>/elevate` |
| `member_demoted` | POST `/admin/members/<id>/demote` |
| `clearance_granted` | POST `/admin/members/<id>/clearances` |
| `clearance_removed` | DELETE `/admin/members/<id>/clearances/<ct_id>` |
| `clearance_type_created` / `_updated` / `_deleted` | `/admin/clearances*` |
| `category_created` / `_updated` / `_deleted` / `_cloned` | `/admin/categories*` |
| `resource_created` / `_updated` / `_deleted` | `/admin/resources*` |
| `resource_out_of_service` / `_restored` | `/admin/resources/<id>/out-of-service` / `/restore` |
| `booking_cancelled_by_admin` | POST `/admin/bookings/<id>/cancel` |
| `opening_hours_updated` | `/admin/opening-hours` |
| `closure_created` / `_deleted` | `/admin/closures*` |
| `system_settings_updated` | POST `/admin/settings` |

`payload` carries before/after JSON for state-changing actions.

### §9.11 Browse & slot picker

- *Given* the Browse page is loaded with `?category=&from=&to=`, *Then* only `available` resources whose category matches and which have at least one minute of unbooked time within `[from,to]` are listed.
- *Given* a Books category resource with multiple copies sharing the same `name`, *Then* the Browse page collapses them into a single card with a copy picker.
- *Given* a workbench or hot-spot resource detail page, *Then* the UI presents quick-select buttons "All day", "Morning" (open→13:00), "Afternoon" (13:00→close) that pre-fill the booking form but otherwise produce ordinary bookings (no backend special case).

---

## §10. UI — Screen Inventory & Key Flows

### §10.1 Screen inventory

| # | Screen | Purpose |
|---|---|---|
| 1 | Landing / login redirect | Entry point |
| 2 | Login | Email + password |
| 3 | Register | Self-registration |
| 4 | Awaiting approval | Shown to logged-in pending users |
| 5 | Browse | Resource list with category + window filter |
| 6 | Resource detail | Description, identifier, slot picker, book button |
| 7 | Booking form | Confirm interval, add comment |
| 8 | My bookings | Upcoming + past, with edit/cancel actions |
| 9 | Booking detail | Edit time, edit comment, cancel |
| 10 | Account → notification preferences | Per-type opt-out toggles |
| 11 | Admin dashboard | Pending approvals, today's bookings, overdue books |
| 12 | Admin → Members list | Filter by status |
| 13 | Admin → Member detail | Approve/reject/freeze/clearances/elevate/demote; member's bookings & cancellation history |
| 14 | Admin → Categories list | |
| 15 | Admin → Category detail | Edit properties; clone button |
| 16 | Admin → Resources list (per category) | |
| 17 | Admin → Resource detail | Edit; out-of-service toggle |
| 18 | Admin → Clearance types | CRUD |
| 19 | Admin → Opening hours | One row per weekday |
| 20 | Admin → Closures | List + add |
| 21 | Admin → System settings | Edit-grace, reminder lead, due-soon offsets, etc. |
| 22 | Admin → Audit log | Paginated, filterable |
| 23 | Admin → Report: Cancellations | |
| 24 | Admin → Report: Booking edits | |
| 25 | Admin → Report: Resource history | |
| 26 | Admin → Report: Late returns | |

### §10.2 Key flow: registration → approval → first booking

1. Visitor opens Landing; clicks "Register".
2. Submits email + password; sees "Awaiting approval".
3. Admin opens `/admin/members`, filters Pending, opens the new applicant's detail.
4. Admin sees any prior rejection note (re-applicant case) and clicks Approve.
5. Approval email is sent via Resend. Member clicks the link, logs in.
6. Member opens Browse, picks "Meeting rooms", selects a date window, clicks a room.
7. Slot picker (HTMX partial on date selection) shows available slots.
8. Member clicks a slot → Booking form pre-filled → adds comment → Confirm.
9. Booking row created, confirmation email sent, member sees the booking on My bookings.

### §10.3 Key flow: browse → book

1. Member opens `/resources?category=Equipment&from=2026-06-12&to=2026-06-19`.
2. Eligible resources render. Resources requiring a clearance the member lacks display a lock badge but remain visible.
3. Member opens a resource. Slot picker loads (HTMX) for the chosen date.
4. Submission goes through `/resources/<id>/book` POST → R1–R9 evaluated → on success, redirect to booking detail with a confirmation flash.

### §10.4 Key flow: out-of-service cascade

1. Admin opens `/admin/resources/<id>`. Clicks "Mark out of service" (with confirm dialog showing the count of bookings about to be cancelled).
2. On confirm, server transaction: load active future bookings → set each to `cancelled_downtime` → flip resource state → write one audit event → enqueue downtime emails.
3. Each affected member receives a downtime-cancellation email; the member's My bookings shows the cancellation.
4. The resource is hidden from Browse until restored.

### §10.5 Key flow: book loan lifecycle

1. Member books book copy C for `[date_from, date_to]`.
2. `scheduled_jobs` rows inserted for due-soon, overdue, escalation.
3. APScheduler fires due-soon jobs → due-soon emails sent.
4. If not returned by `date_to`, overdue jobs fire on schedule.
5. If still not returned at `date_to + escalation_after_days`, escalation email goes to all admins.
6. Admin meets the member, takes the book back, opens the booking, clicks "Mark returned" → unfired jobs deleted, booking status → `returned`.

---

## §11. Cross-cutting Concerns

- **Timezone.** Single timezone configured via `APP_TIMEZONE`. All times stored UTC; templates render in `APP_TIMEZONE`. Date-range bookings interpret `date_from`/`date_to` in local time.
- **Errors.** Validation errors → flash messages + form re-render. 403 / 404 / 500 each have dedicated templates. Errors log at `WARNING` (4xx) or `ERROR` (5xx) with structured fields (`request_id`, `user_id`).
- **CSRF.** Every state-changing route validates a Flask-WTF token.
- **Sessions.** `Secure`, `HttpOnly`, `SameSite=Lax` cookies; 14-day rolling expiry; logout clears the session and rotates the session id.
- **Password policy.** Minimum 10 characters; bcrypt cost 12; no maximum length below bcrypt's 72-byte cap (truncation documented).
- **Rate limiting.** `/auth/login` and `/auth/register` capped at 5 requests/minute/IP via Flask-Limiter.
- **Logging.** Standard library `logging` with JSON formatter in prod, key-value in dev. Email sends, scheduled-job firings, and audit events log at INFO.
- **Email failures.** Resend API errors mark the `notification_log` row `status='failed'` but never block the originating action. A retry job re-attempts failed sends up to 3 times with exponential backoff.

---

## §12. Extension Points for Deferred Features

Each item below is from brainstorm §10. The spec carries it as a documented seam — no code, no UI, no test coverage in v1.

- **Tiered membership.** `users.tier_id` column reserved. Permission checks route through `policy(actor, action, subject)`; a future tier table joins through `tier_id` without touching call sites.
- **Booking quotas.** No table reserved; the planned implementation slots into the conflict-check pipeline after R8 — a single function point.
- **Member check-in flow.** Would add a `bookings.checked_in_at` column and a member-facing check-in route. Existing `status` enum accommodates a future `no_show` value if needed.
- **Cancellation / no-show penalties.** Would consume `notification_log` and the cancellations report; no schema change needed beyond what's above.
- **Recurring bookings.** `bookings.recurrence_id` reserved. Booking creation already routes through a `BookingFactory` whose interface a future scheduler can call in a loop, applying the same R1–R9 to each occurrence.
- **Resource bundles / dependencies.** Would add a join table `category_dependencies` or `resource_dependencies`. Booking creation already happens through a service object that can fan out atomic dependent inserts.
- **Member-visible reviews / ratings.** Out of scope; comments in v1 are admin-directed and not displayed elsewhere.
- **Multiple locations.** `categories.location_id` and `opening_hours.location_id` reserved. Routes would gain a location selector; conflict rules are already per-resource so they remain correct.
- **Multiple admin tiers.** `policy()` already centralises authorization; a future role table joins through `users` without touching most routes.
- **Tag-based / advanced search.** Browse query is centralised in one repository function; a future search backend (e.g., PostgreSQL `tsvector`) drops in there.
- **Member-facing reports.** Reports inherit from a `Report` base class. Member-restricted variants subclass and override the authorization check.
- **Authentication methods beyond email + password.** Auth wrapped behind an `AuthBackend` protocol; v1 ships `PasswordBackend`. SSO / magic-link backends slot in alongside without changing session handling.
- **Clearance expiry & recertification.** `user_clearances.expires_at` reserved. The clearance check in R6 would gain a `WHERE expires_at IS NULL OR expires_at > now()` filter.
- **Waitlists.** `bookings.status` enum can grow a `waitlisted` value. The conflict-detection pipeline is the only place that would need a "promote next waitlisted on cancellation" hook.

---

## §13. Open Questions Deferred to Implementation

The following decisions are deliberately not made in this spec; they are tactical and the implementation team may choose. Any choice must remain consistent with §2–§12.

- Exact CSS framework (Bootstrap, Tailwind, or hand-rolled). HTMX is fixed; the styling layer is not.
- Pagination page size for `/admin/audit` and report tables.
- Specific Resend template/from-address conventions (subject lines, plain-text vs HTML balance) — covered by a separate "Email content" appendix authored alongside implementation.
- Exact wording of error messages (the spec gives indicative copy; the final strings live in a translation catalogue).
