# Makerspace Booking System — Brainstorm

This document captures the outcomes of the scope-brainstorming session that precedes the formal specification. It is the input to the spec, not the spec itself: it records decisions, constraints, edge cases, and explicitly-deferred concerns so the spec author has a single reference.

## 1. Problem

A shared makerspace / electronics lab needs a system for its members to browse and reserve shared resources (rooms, equipment, workbenches, coworking desks, books), and for administrators to manage the resource inventory and member access. The system must:

- Let members find and reserve resources within the rules configured by admins.
- Prevent double-booking through conflict detection.
- Notify members about their bookings (confirmations, reminders, downtime cancellations, book due/overdue).
- Enforce safety controls — members can only book risk-bearing equipment for which they hold the appropriate clearance.
- Give admins the tools to manage members, resources, categories, operating hours, and policies, and to audit activity.

## 2. User Roles

Two roles exist in v1:

### Member
- Self-registers; gains access only after admin approval.
- Browses and books resources.
- Manages their own bookings (cancel, edit within limits).
- Receives transactional emails; can opt out of non-critical types.

### Administrator
- Any member can be elevated to admin. Admin is a flat tier in v1 (no sub-roles).
- The first admin is seeded during installation.
- The system prevents demoting or freezing the last remaining admin.
- Admins perform all management actions and have access to reports and the audit log.

Tiered membership is **not** in scope for v1 but is anticipated as a future extension.

## 3. Resource Model

### 3.1 Single flexible category model

A single category model handles every kind of resource — including books — through configurable properties. The five categories listed below are pre-seeded examples; admins can create new categories at any time and can **clone** an existing category to copy its settings.

Pre-seeded categories:
- Meeting rooms
- Equipment (oscilloscopes, printers, power supplies, woodworking tools, etc.)
- Workbenches
- Hot spots (coworking desks)
- Books

### 3.2 Category properties

Each category carries the following configurable properties, all editable by admins:

| Property | Notes |
|---|---|
| Booking unit | `HOURS` or `DAYS` (books are `DAYS`; everything else seeded is `HOURS`) |
| Subject to opening hours | `true` for time-slotted categories; `false` for books (they leave the building) |
| Resource identifier field | Optional free-text label (e.g., `ISBN`, `Serial No.`) that resources in this category must populate |
| Booking horizon | How many days in advance a member can book |
| Buffer gap | Required gap between consecutive bookings of the same resource (relevant for `HOURS` categories) |
| Minimum booking duration | Floor enforced at booking time |
| Maximum booking duration | Ceiling enforced at booking time |
| Reminder schedule | For `HOURS`: N hours before start. For `DAYS`: due-soon offsets (default: 1 and 3 days before due) and overdue offsets (default: 1 and 3 days after due, then admin email) |

Cloning a category duplicates its settings, not the resources within it.

### 3.3 Resource properties

Each resource belongs to exactly one category and adds:
- Name and description
- The identifier value (if its category requires one)
- Optional required clearance (one or more clearance types a member must hold to book this resource)
- Availability state (`available`, `out-of-service`)

### 3.4 Clearances

- Clearance types are managed by admins.
- A member's clearances are recorded on their member profile and can only be edited by an admin.
- Clearances do **not** expire in v1. (Periodic recertification is a future concern.)
- If a clearance is removed from a member who already holds bookings requiring it, the bookings are retained; admins manually cancel them as needed (same pattern as account freeze).

## 4. Member Capabilities

- **Self-register** with email + password; account is `pending` until an admin approves or rejects.
- **Browse** resources, filtered by category and availability window.
  - Books with multiple copies of the same title are grouped under one title with a copy picker in the UI.
  - Workbenches and hot spots present quick-select buttons (`all day`, `morning`, `afternoon`) but produce ordinary slot bookings — no backend special case.
- **Reserve** a resource within the category's booking horizon, including spontaneous bookings (no minimum lead time, subject only to availability and any required clearance).
- **Hold multiple overlapping bookings** across *different* resources (e.g., workbench + oscilloscope + power supply for the same two hours).
- **Edit** a booking's start/end time, limited to a ±1-hour window relative to the *current* start time after the most recent edit, with a maximum of two edits per booking. The grace window is admin-configurable. Edits that change anything other than the time (e.g., the comment) do not count toward the limit. An edit that would create a conflict is rejected like a fresh booking.
- **Cancel** a booking at any time up to its start. Cancellations are logged against the member's account for admin review; no automatic penalty applies.
- **Add a comment** to a booking. The comment is a one-shot message to the admin (e.g., reporting condition issues or special requests), not a public review.
- **Borrow books** by date range. Members physically return books; the admin marks each return as `returned and available`.
- **Manage notification preferences** by email type. Opting out of reminder-type emails surfaces a warning that the member is responsible for tracking their own bookings.

## 5. Admin Capabilities

- **Member management**
  - Approve or reject registrations. Rejections capture a notes field; rejected applicants' records are retained so a re-applicant's prior rejection note is visible.
  - Freeze and unfreeze accounts. Frozen members cannot create or hold new bookings; existing bookings are retained and the admin can cancel them manually from the member's record.
  - View all of a member's bookings on the member record page.
  - Elevate any member to admin; demote any admin (subject to last-admin protection).
  - Grant or remove clearances.
- **Resource management**
  - Create, edit, clone, and remove resource categories.
  - Create and edit resources within categories.
  - Mark a resource as out-of-service. Doing so auto-cancels affected bookings and emails the affected members; members can rebook when the resource returns to service.
- **Operating hours**
  - Configure opening hours per day of week (e.g., closed Sunday, late open Friday).
  - Mark holidays and one-off closures.
  - Opening hours bound all time-slotted bookings. Book loans (date-range, not opening-hours-bound) are unaffected.
- **Notification settings**
  - Set system-wide reminder lead times (one set of values applies to all members).
- **Book returns** — mark a returned book as `returned and available`.
- **Reports** (see §7).
- **Audit log** — view immutable system records of admin actions.

## 6. Notifications

Email-only, transactional. Member-configurable opt-out by type.

Notification types:
- Registration **approved** / **rejected**
- Booking **confirmation**
- Booking **reminder** (N hours before start, for `HOURS` categories) — system-wide N, admin-configured
- Book **due-soon** (1 and 3 days before return date) — system-wide, admin-configured
- Book **overdue** (1 and 3 days after return date) — system-wide, admin-configured
- Book **escalation to admin** if a book remains unreturned after the overdue reminders
- **Downtime cancellation** (resource taken out of service)
- **Manual cancellation** (admin cancelled a member's booking)

## 7. Audit Log & Reports

### Audit log
Automatic, immutable. Admins can view but not edit or delete entries. Captures, at minimum:
- Member approvals and rejections
- Account freezes / unfreezes
- Clearance grants and removals
- Manual cancellations of bookings
- Admin elevations and demotions
- Resource out-of-service toggles
- Category and resource changes

### Reports
Built-in dashboards, viewable by admins. Examples:
- Cancellations over a date range
- Booking edits / extensions over a date range
- All members who booked a given resource within a date range (past or future)
- Late book returns by member

Member-facing reporting is out of scope for v1.

## 8. Edge Cases & Business Rules

| Situation | Rule |
|---|---|
| Frozen member with existing bookings | Bookings retained; admin can cancel manually from the member record page. |
| Clearance removed from a member with existing bookings requiring it | Bookings retained; admin can cancel manually. |
| Resource marked out-of-service with existing bookings | Auto-cancel all affected bookings; email each affected member. They may rebook when the resource is restored. |
| Member edits a booking into a conflict | Edit is rejected, same as a fresh booking would be. |
| Member edits only the comment | Does not count toward the 2-edit limit; ±1h window does not apply. |
| Member cancels a booking | Logged on member record. No automatic penalty. Admins may freeze the account if patterns warrant it. |
| Book overdue beyond all reminder windows | Email sent to admin. Late return logged against the member for reports. |
| Last remaining admin | System prevents demotion or freeze. |
| Rejected applicant re-applies | Record retained; prior rejection notes shown to admin reviewing the new application. |
| Books in browse with multiple copies | UI groups by title with copy picker; data model treats each copy as an independent resource. |
| Book loan and opening hours | Books are not bound by opening hours (they leave the building). |
| Member holds overlapping bookings across different resources | Allowed. Conflict detection applies per resource, not per member. |
| Spontaneous booking starting in five minutes | Allowed if the resource is available and clearances pass. No minimum lead time. |

## 9. Cross-cutting Assumptions

- **Single location**, single timezone.
- **No payments** or billing integration in v1.
- **Email + password** authentication. (Method may be revisited at the tech-stack stage.)
- All admin-only changes that affect a member or a resource are recorded in the audit log.
- Admin elevations and demotions are themselves audited.

## 10. Explicitly Out of Scope (Future Versions)

Recorded here so the spec can leave clean extension points without building scaffolding now.

- **Tiered membership** (e.g., day-pass, regular, key-holder). v1 is homogeneous.
- **Booking quotas** (max hours/week per resource, max concurrent book loans, etc.).
- **Member check-in flow.** v1 treats a booking as proof of use.
- **Cancellation / no-show penalties.** Admin freeze is the only enforcement lever in v1.
- **Recurring bookings** (e.g., weekly club meetings).
- **Resource bundles / dependencies** (e.g., projector implicitly booked with a meeting room).
- **Member-visible resource reviews or ratings.** Comments in v1 are addressed to the admin.
- **Multiple makerspace locations.**
- **Multiple admin tiers** (super-admin vs. resource-steward).
- **Tag-based or advanced search** beyond category + availability filtering.
- **Member-facing reports.**
- **Authentication methods beyond email + password** (e.g., SSO, magic link).
- **Clearance expiry and recertification.**
- **Waitlists** for popular resources or books.

## 11. Items to Resolve in the Specification

The spec should commit to specifics on the following, which the brainstorm intentionally left open:

- Exact data model and entity relationships.
- Technology stack (language, framework, database, email provider).
- UI flows and screen inventory.
- Validation rules and error message text.
- Default values for category properties on the five seeded categories.
- Default values for system-wide notification settings.
- Bootstrap procedure for the first admin during installation.
- Permission rules for admin actions (e.g., can an admin freeze themselves? — implied no by last-admin protection, but worth stating).
