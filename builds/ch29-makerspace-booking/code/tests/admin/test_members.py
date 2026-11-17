import pytest

from app.extensions import db as _db
from app.models import AuditEvent, User, UserStatus

PASSWORD = "testpassword1"


def _login(client, user):
    client.post("/auth/login", data={"email": user.email, "password": PASSWORD})


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

class TestAdminRequired:
    def test_list_anonymous(self, client):
        resp = client.get("/admin/members")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_list_non_admin(self, client, active_user):
        _login(client, active_user)
        resp = client.get("/admin/members")
        assert resp.status_code == 302
        assert "/auth/login" not in resp.headers["Location"]

    def test_approve_anonymous(self, client, pending_user):
        resp = client.post(f"/admin/members/{pending_user.id}/approve")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_reject_anonymous(self, client, pending_user):
        resp = client.get(f"/admin/members/{pending_user.id}/reject")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_freeze_anonymous(self, client, active_user):
        resp = client.post(f"/admin/members/{active_user.id}/freeze")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_unfreeze_anonymous(self, client, frozen_user):
        resp = client.post(f"/admin/members/{frozen_user.id}/unfreeze")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# Members list
# ---------------------------------------------------------------------------

class TestMembersList:
    def test_list_renders(self, client, admin_user, pending_user, active_user):
        _login(client, admin_user)
        resp = client.get("/admin/members")
        assert resp.status_code == 200
        assert pending_user.display_name.encode() in resp.data
        assert active_user.display_name.encode() in resp.data

    def test_status_filter_pending(self, client, admin_user, pending_user, active_user):
        _login(client, admin_user)
        resp = client.get("/admin/members?status=pending")
        assert resp.status_code == 200
        assert pending_user.email.encode() in resp.data
        assert active_user.email.encode() not in resp.data

    def test_status_filter_active(self, client, admin_user, pending_user, active_user):
        _login(client, admin_user)
        resp = client.get("/admin/members?status=active")
        assert resp.status_code == 200
        assert active_user.email.encode() in resp.data
        assert pending_user.email.encode() not in resp.data

    def test_invalid_status_filter_ignored(self, client, admin_user):
        _login(client, admin_user)
        resp = client.get("/admin/members?status=invalid")
        assert resp.status_code == 200

    def test_empty_state(self, client, admin_user):
        _login(client, admin_user)
        resp = client.get("/admin/members?status=pending")
        # Only admin_user exists and is active, not pending
        assert b"No members found" in resp.data


# ---------------------------------------------------------------------------
# Approve
# ---------------------------------------------------------------------------

class TestMemberApprove:
    def test_approve_pending_user(self, client, db, admin_user, pending_user):
        _login(client, admin_user)
        resp = client.post(f"/admin/members/{pending_user.id}/approve")
        assert resp.status_code == 302
        db.session.refresh(pending_user)
        assert pending_user.status == UserStatus.active
        assert pending_user.approved_at is not None

    def test_approve_logs_audit(self, client, db, admin_user, pending_user):
        _login(client, admin_user)
        client.post(f"/admin/members/{pending_user.id}/approve")
        event = db.session.execute(
            db.select(AuditEvent).where(AuditEvent.action == "member_approved")
        ).scalar_one_or_none()
        assert event is not None
        assert event.subject_id == pending_user.id
        assert event.payload["email"] == pending_user.email

    def test_approve_non_pending_fails(self, client, db, admin_user, active_user):
        _login(client, admin_user)
        resp = client.post(f"/admin/members/{active_user.id}/approve",
                           follow_redirects=True)
        assert b"not pending" in resp.data
        db.session.refresh(active_user)
        assert active_user.status == UserStatus.active  # unchanged


# ---------------------------------------------------------------------------
# Reject
# ---------------------------------------------------------------------------

class TestMemberReject:
    def test_reject_form_renders(self, client, admin_user, pending_user):
        _login(client, admin_user)
        resp = client.get(f"/admin/members/{pending_user.id}/reject")
        assert resp.status_code == 200
        assert pending_user.display_name.encode() in resp.data
        assert b"Reason for rejection" in resp.data

    def test_reject_with_note(self, client, db, admin_user, pending_user):
        _login(client, admin_user)
        resp = client.post(
            f"/admin/members/{pending_user.id}/reject",
            data={"note": "Not eligible at this time."},
        )
        assert resp.status_code == 302
        db.session.refresh(pending_user)
        assert pending_user.status == UserStatus.rejected
        assert pending_user.rejection_note == "Not eligible at this time."

    def test_reject_blank_note_fails(self, client, db, admin_user, pending_user):
        _login(client, admin_user)
        resp = client.post(
            f"/admin/members/{pending_user.id}/reject",
            data={"note": ""},
            follow_redirects=True,
        )
        assert b"rejection reason is required" in resp.data
        db.session.refresh(pending_user)
        assert pending_user.status == UserStatus.pending  # unchanged

    def test_reject_logs_audit(self, client, db, admin_user, pending_user):
        _login(client, admin_user)
        client.post(
            f"/admin/members/{pending_user.id}/reject",
            data={"note": "Does not meet requirements."},
        )
        event = db.session.execute(
            db.select(AuditEvent).where(AuditEvent.action == "member_rejected")
        ).scalar_one_or_none()
        assert event is not None
        assert event.subject_id == pending_user.id
        assert event.payload["note"] == "Does not meet requirements."


# ---------------------------------------------------------------------------
# Freeze
# ---------------------------------------------------------------------------

class TestMemberFreeze:
    def test_freeze_active_user(self, client, db, admin_user, active_user):
        _login(client, admin_user)
        resp = client.post(f"/admin/members/{active_user.id}/freeze")
        assert resp.status_code == 302
        db.session.refresh(active_user)
        assert active_user.status == UserStatus.frozen

    def test_freeze_logs_audit(self, client, db, admin_user, active_user):
        _login(client, admin_user)
        client.post(f"/admin/members/{active_user.id}/freeze")
        event = db.session.execute(
            db.select(AuditEvent).where(AuditEvent.action == "member_frozen")
        ).scalar_one_or_none()
        assert event is not None
        assert event.subject_id == active_user.id

    def test_freeze_non_active_fails(self, client, db, admin_user, pending_user):
        _login(client, admin_user)
        resp = client.post(f"/admin/members/{pending_user.id}/freeze",
                           follow_redirects=True)
        assert b"not active" in resp.data
        db.session.refresh(pending_user)
        assert pending_user.status == UserStatus.pending  # unchanged


# ---------------------------------------------------------------------------
# Unfreeze
# ---------------------------------------------------------------------------

class TestMemberUnfreeze:
    def test_unfreeze_frozen_user(self, client, db, admin_user, frozen_user):
        _login(client, admin_user)
        resp = client.post(f"/admin/members/{frozen_user.id}/unfreeze")
        assert resp.status_code == 302
        db.session.refresh(frozen_user)
        assert frozen_user.status == UserStatus.active

    def test_unfreeze_logs_audit(self, client, db, admin_user, frozen_user):
        _login(client, admin_user)
        client.post(f"/admin/members/{frozen_user.id}/unfreeze")
        event = db.session.execute(
            db.select(AuditEvent).where(AuditEvent.action == "member_unfrozen")
        ).scalar_one_or_none()
        assert event is not None
        assert event.subject_id == frozen_user.id

    def test_unfreeze_non_frozen_fails(self, client, db, admin_user, active_user):
        _login(client, admin_user)
        resp = client.post(f"/admin/members/{active_user.id}/unfreeze",
                           follow_redirects=True)
        assert b"not frozen" in resp.data
        db.session.refresh(active_user)
        assert active_user.status == UserStatus.active  # unchanged


# ---------------------------------------------------------------------------
# Self-protection
# ---------------------------------------------------------------------------

class TestSelfProtection:
    def test_cannot_approve_self(self, client, db, admin_user):
        _login(client, admin_user)
        resp = client.post(f"/admin/members/{admin_user.id}/approve",
                           follow_redirects=True)
        assert b"cannot change your own" in resp.data

    def test_cannot_reject_self(self, client, db, admin_user):
        _login(client, admin_user)
        resp = client.post(
            f"/admin/members/{admin_user.id}/reject",
            data={"note": "self-rejection"},
            follow_redirects=True,
        )
        assert b"cannot change your own" in resp.data

    def test_cannot_freeze_self(self, client, db, admin_user):
        _login(client, admin_user)
        resp = client.post(f"/admin/members/{admin_user.id}/freeze",
                           follow_redirects=True)
        assert b"cannot change your own" in resp.data

    def test_cannot_unfreeze_self(self, client, db, admin_user):
        _login(client, admin_user)
        resp = client.post(f"/admin/members/{admin_user.id}/unfreeze",
                           follow_redirects=True)
        assert b"cannot change your own" in resp.data


# ---------------------------------------------------------------------------
# Edit member
# ---------------------------------------------------------------------------

def _edit_form(client, member_id, **overrides):
    base = {
        "display_name": "Updated Name",
        "email": "updated@example.com",
        "avatar": "",
    }
    base.update(overrides)
    return client.post(f"/admin/members/{member_id}/edit", data=base)


class TestMemberEdit:
    def test_edit_anonymous_redirected(self, client, active_user):
        resp = client.get(f"/admin/members/{active_user.id}/edit")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_edit_non_admin_redirected(self, client, active_user):
        _login(client, active_user)
        resp = client.get(f"/admin/members/{active_user.id}/edit")
        assert resp.status_code == 302
        assert "/auth/login" not in resp.headers["Location"]

    def test_edit_form_renders(self, client, admin_user, active_user):
        _login(client, admin_user)
        resp = client.get(f"/admin/members/{active_user.id}/edit")
        assert resp.status_code == 200
        assert active_user.display_name.encode() in resp.data
        assert active_user.email.encode() in resp.data

    def test_edit_updates_display_name(self, client, db, admin_user, active_user):
        _login(client, admin_user)
        _edit_form(client, active_user.id, display_name="New Name", email=active_user.email)
        db.session.refresh(active_user)
        assert active_user.display_name == "New Name"

    def test_edit_updates_email(self, client, db, admin_user, active_user):
        _login(client, admin_user)
        _edit_form(client, active_user.id, display_name=active_user.display_name, email="newemail@example.com")
        db.session.refresh(active_user)
        assert active_user.email == "newemail@example.com"

    def test_edit_duplicate_email_fails(self, client, db, admin_user, active_user, pending_user):
        _login(client, admin_user)
        resp = _edit_form(client, active_user.id,
                          display_name=active_user.display_name,
                          email=pending_user.email,
                          follow_redirects=True)
        assert b"already in use" in resp.data
        db.session.refresh(active_user)
        assert active_user.email != pending_user.email

    def test_edit_blank_name_fails(self, client, db, admin_user, active_user):
        _login(client, admin_user)
        resp = client.post(
            f"/admin/members/{active_user.id}/edit",
            data={"display_name": "", "email": active_user.email, "avatar": ""},
            follow_redirects=True,
        )
        assert b"Display name is required" in resp.data
        db.session.refresh(active_user)
        assert active_user.display_name != ""

    def test_edit_grants_admin(self, client, db, admin_user, active_user):
        assert not active_user.is_admin
        _login(client, admin_user)
        _edit_form(client, active_user.id,
                   display_name=active_user.display_name,
                   email=active_user.email,
                   is_admin="on")
        db.session.refresh(active_user)
        assert active_user.is_admin is True

    def test_edit_revokes_admin(self, client, db, admin_user, active_user):
        active_user.is_admin = True
        db.session.commit()
        _login(client, admin_user)
        _edit_form(client, active_user.id,
                   display_name=active_user.display_name,
                   email=active_user.email)
        db.session.refresh(active_user)
        assert active_user.is_admin is False

    def test_edit_cannot_change_own_admin(self, client, db, admin_user):
        _login(client, admin_user)
        # POST without is_admin — would demote if self-edit were allowed
        _edit_form(client, admin_user.id,
                   display_name=admin_user.display_name,
                   email=admin_user.email)
        db.session.refresh(admin_user)
        assert admin_user.is_admin is True  # unchanged

    def test_edit_logs_audit(self, client, db, admin_user, active_user):
        _login(client, admin_user)
        _edit_form(client, active_user.id,
                   display_name="Audited Name",
                   email=active_user.email)
        event = db.session.execute(
            db.select(AuditEvent).where(AuditEvent.action == "member_updated")
        ).scalar_one_or_none()
        assert event is not None
        assert event.subject_id == active_user.id
        assert event.payload["after"]["display_name"] == "Audited Name"

    def test_edit_redirects_on_success(self, client, admin_user, active_user):
        _login(client, admin_user)
        resp = _edit_form(client, active_user.id,
                          display_name=active_user.display_name,
                          email=active_user.email)
        assert resp.status_code == 302
        assert "/admin/members" in resp.headers["Location"]
