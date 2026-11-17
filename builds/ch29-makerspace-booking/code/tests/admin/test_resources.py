import pytest
from datetime import time
from io import BytesIO

from app.extensions import db as _db
from app.models import Resource
from app.models.resource import DEFAULT_WEEKDAY_END, DEFAULT_WEEKDAY_START, ResourceCategory, ResourceState

PASSWORD = "testpassword1"


def _make_resource(db, tenant_id, **kwargs) -> Resource:
    defaults = dict(
        name="Test Resource",
        category=ResourceCategory.equipment,
        description=None,
        location=None,
        weekday_start=time(9, 0),
        weekday_end=time(18, 0),
        weekend_start=None,
        weekend_end=None,
        is_archived=False,
        state=ResourceState.available,
        tenant_id=tenant_id,
    )
    defaults.update(kwargs)
    r = Resource(**defaults)
    db.session.add(r)
    db.session.commit()
    return r


def _login(client, user):
    client.post("/auth/login", data={"email": user.email, "password": PASSWORD})


def _valid_form(**overrides):
    base = {
        "name": "Laser Cutter",
        "description": "High-power laser",
        "location": "Room 3",
        "category": "equipment",
        "weekday_start": "09:00",
        "weekday_end": "17:00",
        "weekend_start": "",
        "weekend_end": "",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

class TestAdminRequired:
    def test_list_anonymous(self, client):
        resp = client.get("/admin/resources")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_new_anonymous(self, client):
        resp = client.get("/admin/resources/new")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_edit_anonymous(self, client):
        resp = client.get("/admin/resources/1/edit")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_archive_anonymous(self, client):
        resp = client.post("/admin/resources/1/archive")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_list_non_admin(self, client, active_user):
        _login(client, active_user)
        resp = client.get("/admin/resources")
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/home"

    def test_new_non_admin(self, client, active_user):
        _login(client, active_user)
        resp = client.get("/admin/resources/new")
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/home"

    def test_non_admin_flash(self, client, active_user):
        _login(client, active_user)
        client.get("/admin/resources")
        with client.session_transaction() as sess:
            flashes = sess.get("_flashes", [])
        assert any("Admin access required" in msg for _, msg in flashes)


# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------

class TestAdminDashboard:
    def test_dashboard_anonymous(self, client):
        resp = client.get("/admin")
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_dashboard_non_admin_redirected(self, client, active_user):
        _login(client, active_user)
        resp = client.get("/admin")
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/home"

    def test_dashboard_renders_for_admin(self, client, admin_user):
        _login(client, admin_user)
        resp = client.get("/admin")
        assert resp.status_code == 200
        assert b"Admin Dashboard" in resp.data
        assert b"Resources" in resp.data


# ---------------------------------------------------------------------------
# Resource list
# ---------------------------------------------------------------------------

class TestResourcesList:
    def test_empty_list(self, client, admin_user):
        _login(client, admin_user)
        resp = client.get("/admin/resources")
        assert resp.status_code == 200
        assert b"No resources" in resp.data

    def test_shows_non_archived_resource(self, client, db, admin_user):
        _make_resource(db, admin_user.tenant_id, name="3D Printer")
        _login(client, admin_user)
        resp = client.get("/admin/resources")
        assert b"3D Printer" in resp.data

    def test_hides_archived_resource(self, client, db, admin_user):
        _make_resource(db, admin_user.tenant_id, name="Old Lathe", is_archived=True)
        _login(client, admin_user)
        resp = client.get("/admin/resources")
        assert b"Old Lathe" not in resp.data

    def test_shows_name_category_location(self, client, db, admin_user):
        _make_resource(
            db, admin_user.tenant_id,
            name="Workbench A",
            category=ResourceCategory.workbench,
            location="Bay 2",
        )
        _login(client, admin_user)
        resp = client.get("/admin/resources")
        assert b"Workbench A" in resp.data
        assert b"Bay 2" in resp.data

    def test_shows_weekday_availability(self, client, db, admin_user):
        _make_resource(db, admin_user.tenant_id, name="Scope", weekday_start=time(8, 0), weekday_end=time(20, 0))
        _login(client, admin_user)
        resp = client.get("/admin/resources")
        assert b"08:00" in resp.data
        assert b"20:00" in resp.data

    def test_shows_weekend_availability_when_set(self, client, db, admin_user):
        _make_resource(
            db, admin_user.tenant_id,
            name="Meeting Room",
            weekday_start=time(8, 0),
            weekday_end=time(21, 0),
            weekend_start=time(9, 0),
            weekend_end=time(15, 0),
        )
        _login(client, admin_user)
        resp = client.get("/admin/resources")
        assert b"09:00" in resp.data
        assert b"15:00" in resp.data

    def test_omits_weekend_row_when_not_set(self, client, db, admin_user):
        _make_resource(db, admin_user.tenant_id, name="Scope", weekend_start=None, weekend_end=None)
        _login(client, admin_user)
        resp = client.get("/admin/resources")
        assert b"Wkend" not in resp.data


# ---------------------------------------------------------------------------
# Add resource
# ---------------------------------------------------------------------------

class TestResourceNew:
    def test_get_renders_form(self, client, admin_user):
        _login(client, admin_user)
        resp = client.get("/admin/resources/new")
        assert resp.status_code == 200
        assert b"Add Resource" in resp.data

    def test_get_shows_category_options(self, client, admin_user):
        _login(client, admin_user)
        resp = client.get("/admin/resources/new")
        assert b"Equipment" in resp.data
        assert b"Meeting Room" in resp.data

    def test_post_valid_creates_resource(self, client, db, admin_user):
        _login(client, admin_user)
        resp = client.post("/admin/resources/new", data=_valid_form())
        assert resp.status_code == 302
        assert "/admin/resources" in resp.headers["Location"]
        resource = db.session.execute(
            db.select(Resource).where(Resource.name == "Laser Cutter")
        ).scalar_one()
        assert resource.location == "Room 3"
        assert resource.category.value == "equipment"
        assert resource.weekday_start == time(9, 0)
        assert resource.weekday_end == time(17, 0)

    def test_post_valid_flash(self, client, admin_user):
        _login(client, admin_user)
        resp = client.post("/admin/resources/new", data=_valid_form(), follow_redirects=True)
        assert b"added" in resp.data

    def test_post_missing_name_rerenders(self, client, admin_user):
        _login(client, admin_user)
        resp = client.post("/admin/resources/new", data=_valid_form(name=""))
        assert resp.status_code == 200
        assert b"Name is required" in resp.data

    def test_post_invalid_category_rerenders(self, client, admin_user):
        _login(client, admin_user)
        resp = client.post("/admin/resources/new", data=_valid_form(category="laser_beam"))
        assert resp.status_code == 200
        assert b"valid category" in resp.data

    def test_post_optional_fields_blank(self, client, db, admin_user):
        _login(client, admin_user)
        resp = client.post(
            "/admin/resources/new",
            data=_valid_form(
                description="", location="",
                weekday_start="", weekday_end="",
                weekend_start="", weekend_end="",
            ),
        )
        assert resp.status_code == 302
        resource = db.session.execute(
            db.select(Resource).where(Resource.name == "Laser Cutter")
        ).scalar_one()
        assert resource.description is None
        assert resource.location is None
        # blank weekday fields fall back to env-var defaults
        assert resource.weekday_start == DEFAULT_WEEKDAY_START
        assert resource.weekday_end == DEFAULT_WEEKDAY_END
        assert resource.weekend_start is None
        assert resource.weekend_end is None

    def test_post_weekend_hours_saved(self, client, db, admin_user):
        _login(client, admin_user)
        resp = client.post(
            "/admin/resources/new",
            data=_valid_form(weekend_start="09:00", weekend_end="15:00"),
        )
        assert resp.status_code == 302
        resource = db.session.execute(
            db.select(Resource).where(Resource.name == "Laser Cutter")
        ).scalar_one()
        assert resource.weekend_start == time(9, 0)
        assert resource.weekend_end == time(15, 0)

    def test_post_partial_weekend_rerenders(self, client, admin_user):
        _login(client, admin_user)
        resp = client.post(
            "/admin/resources/new",
            data=_valid_form(weekend_start="09:00", weekend_end=""),
        )
        assert resp.status_code == 200
        assert b"weekend start and end" in resp.data


# ---------------------------------------------------------------------------
# Edit resource
# ---------------------------------------------------------------------------

class TestResourceEdit:
    def test_get_prepopulates_form(self, client, db, admin_user):
        r = _make_resource(db, admin_user.tenant_id, name="Band Saw", location="Workshop")
        _login(client, admin_user)
        resp = client.get(f"/admin/resources/{r.id}/edit")
        assert resp.status_code == 200
        assert b"Band Saw" in resp.data
        assert b"Workshop" in resp.data

    def test_post_valid_updates_resource(self, client, db, admin_user):
        r = _make_resource(db, admin_user.tenant_id, name="Old Name")
        _login(client, admin_user)
        resp = client.post(
            f"/admin/resources/{r.id}/edit", data=_valid_form(name="New Name")
        )
        assert resp.status_code == 302
        db.session.refresh(r)
        assert r.name == "New Name"

    def test_post_valid_flash(self, client, db, admin_user):
        r = _make_resource(db, admin_user.tenant_id)
        _login(client, admin_user)
        resp = client.post(
            f"/admin/resources/{r.id}/edit",
            data=_valid_form(),
            follow_redirects=True,
        )
        assert b"updated" in resp.data

    def test_post_missing_name_rerenders(self, client, db, admin_user):
        r = _make_resource(db, admin_user.tenant_id)
        _login(client, admin_user)
        resp = client.post(f"/admin/resources/{r.id}/edit", data=_valid_form(name=""))
        assert resp.status_code == 200
        assert b"Name is required" in resp.data

    def test_post_updates_all_four_time_fields(self, client, db, admin_user):
        r = _make_resource(db, admin_user.tenant_id)
        _login(client, admin_user)
        client.post(
            f"/admin/resources/{r.id}/edit",
            data=_valid_form(
                weekday_start="08:00", weekday_end="21:00",
                weekend_start="09:00", weekend_end="15:00",
            ),
        )
        db.session.refresh(r)
        assert r.weekday_start == time(8, 0)
        assert r.weekday_end == time(21, 0)
        assert r.weekend_start == time(9, 0)
        assert r.weekend_end == time(15, 0)

    def test_post_partial_weekend_rerenders(self, client, db, admin_user):
        r = _make_resource(db, admin_user.tenant_id)
        _login(client, admin_user)
        resp = client.post(
            f"/admin/resources/{r.id}/edit",
            data=_valid_form(weekend_start="", weekend_end="14:00"),
        )
        assert resp.status_code == 200
        assert b"weekend start and end" in resp.data

    def test_post_clears_weekend_hours(self, client, db, admin_user):
        r = _make_resource(db, admin_user.tenant_id, weekend_start=time(9, 0), weekend_end=time(15, 0))
        _login(client, admin_user)
        client.post(
            f"/admin/resources/{r.id}/edit",
            data=_valid_form(weekend_start="", weekend_end=""),
        )
        db.session.refresh(r)
        assert r.weekend_start is None
        assert r.weekend_end is None

    def test_get_404(self, client, admin_user):
        _login(client, admin_user)
        resp = client.get("/admin/resources/9999/edit")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Archive resource
# ---------------------------------------------------------------------------

class TestResourceArchive:
    def test_archive_sets_flag(self, client, db, admin_user):
        r = _make_resource(db, admin_user.tenant_id, name="Drill Press")
        _login(client, admin_user)
        resp = client.post(f"/admin/resources/{r.id}/archive")
        assert resp.status_code == 302
        db.session.refresh(r)
        assert r.is_archived is True

    def test_archive_flash(self, client, db, admin_user):
        r = _make_resource(db, admin_user.tenant_id)
        _login(client, admin_user)
        resp = client.post(f"/admin/resources/{r.id}/archive", follow_redirects=True)
        assert b"archived" in resp.data

    def test_archive_404(self, client, admin_user):
        _login(client, admin_user)
        resp = client.post("/admin/resources/9999/archive")
        assert resp.status_code == 404

    def test_archived_absent_from_list(self, client, db, admin_user):
        r = _make_resource(db, admin_user.tenant_id, name="Vinyl Cutter")
        _login(client, admin_user)
        # follow_redirects consumes the "archived" flash so the next GET is clean
        client.post(f"/admin/resources/{r.id}/archive", follow_redirects=True)
        resp = client.get("/admin/resources")
        assert b"Vinyl Cutter" not in resp.data


# ---------------------------------------------------------------------------
# Thumbnail upload
# ---------------------------------------------------------------------------

class TestResourceThumbnail:
    def test_create_with_valid_jpg_saves_file_and_sets_db_field(self, client, db, admin_user, upload_dir):
        _login(client, admin_user)
        data = {**_valid_form(), "thumbnail": (BytesIO(b"\xff\xd8\xff"), "photo.jpg")}
        resp = client.post("/admin/resources/new", data=data, content_type="multipart/form-data")
        assert resp.status_code == 302
        r = db.session.execute(db.select(Resource).where(Resource.name == "Laser Cutter")).scalar_one()
        assert r.thumbnail is not None
        assert (upload_dir / r.thumbnail).exists()

    def test_create_with_invalid_extension_rerenders_with_error(self, client, admin_user, upload_dir):
        _login(client, admin_user)
        data = {**_valid_form(), "thumbnail": (BytesIO(b"BM"), "photo.bmp")}
        resp = client.post("/admin/resources/new", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
        assert b"JPG, PNG, GIF, or WebP" in resp.data

    def test_create_without_file_thumbnail_is_null(self, client, db, admin_user):
        _login(client, admin_user)
        client.post("/admin/resources/new", data=_valid_form())
        r = db.session.execute(db.select(Resource).where(Resource.name == "Laser Cutter")).scalar_one()
        assert r.thumbnail is None

    def test_edit_new_upload_replaces_old_thumbnail(self, client, db, admin_user, upload_dir):
        old_file = upload_dir / "old.jpg"
        old_file.write_bytes(b"old content")
        r = _make_resource(db, admin_user.tenant_id, thumbnail="old.jpg")
        _login(client, admin_user)
        data = {**_valid_form(), "thumbnail": (BytesIO(b"\xff\xd8\xff"), "new.jpg")}
        client.post(f"/admin/resources/{r.id}/edit", data=data, content_type="multipart/form-data")
        db.session.refresh(r)
        assert r.thumbnail != "old.jpg"
        assert not old_file.exists()
        assert (upload_dir / r.thumbnail).exists()

    def test_edit_remove_checkbox_clears_thumbnail_and_deletes_file(self, client, db, admin_user, upload_dir):
        old_file = upload_dir / "photo.png"
        old_file.write_bytes(b"img content")
        r = _make_resource(db, admin_user.tenant_id, thumbnail="photo.png")
        _login(client, admin_user)
        data = {**_valid_form(), "remove_thumbnail": "1"}
        client.post(f"/admin/resources/{r.id}/edit", data=data)
        db.session.refresh(r)
        assert r.thumbnail is None
        assert not old_file.exists()

    def test_edit_without_file_preserves_existing_thumbnail(self, client, db, admin_user):
        r = _make_resource(db, admin_user.tenant_id, thumbnail="kept.jpg")
        _login(client, admin_user)
        client.post(f"/admin/resources/{r.id}/edit", data=_valid_form())
        db.session.refresh(r)
        assert r.thumbnail == "kept.jpg"

    def test_admin_list_renders_thumbnail_img(self, client, db, admin_user):
        _make_resource(db, admin_user.tenant_id, thumbnail="abc123.jpg")
        _login(client, admin_user)
        resp = client.get("/admin/resources")
        assert b"uploads/resources/abc123.jpg" in resp.data

    def test_admin_list_renders_placeholder_when_no_thumbnail(self, client, db, admin_user):
        _make_resource(db, admin_user.tenant_id, name="Drill Press")
        _login(client, admin_user)
        resp = client.get("/admin/resources")
        assert b"resource_placeholder.svg" in resp.data
