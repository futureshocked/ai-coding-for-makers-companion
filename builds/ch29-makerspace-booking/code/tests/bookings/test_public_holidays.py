import json
from datetime import date, time
from urllib.error import URLError

import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db as _db
from app.models import Booking, Resource
from app.models.booking import BookingStatus
from app.models.public_holiday import PublicHoliday
from app.models.resource import ResourceCategory, ResourceState
from app.models.user import User, UserStatus
from app.services.holidays import (
    _cached_holidays,
    _fetch_and_cache,
    _get_country_code,
    is_public_holiday,
)

PASSWORD = "testpassword1"
HOLIDAY_DATE = date(2026, 1, 1)    # Thursday — within the default weekday window
NON_HOLIDAY_DATE = date(2026, 5, 25)  # Monday — no holiday


class _FakeResponse:
    """Minimal urllib response stub for monkeypatching urlopen."""

    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _fake_urlopen(payload: list):
    """Return a urlopen replacement that always yields *payload* as JSON."""
    def _open(url, timeout=5):
        return _FakeResponse(json.dumps(payload).encode())
    return _open


def _insert_holiday(holiday_date=HOLIDAY_DATE, country_code="AU", name="New Year's Day"):
    h = PublicHoliday(date=holiday_date, country_code=country_code, name=name)
    _db.session.add(h)
    _db.session.commit()
    return h


def _make_active_user(email="active@example.com", tenant_id=None):
    u = User(
        email=email,
        password_hash=generate_password_hash(PASSWORD),
        display_name="Active User",
        status=UserStatus.active,
        is_admin=False,
        notification_prefs={},
        tenant_id=tenant_id,
    )
    _db.session.add(u)
    _db.session.commit()
    return u


def _make_resource(tenant_id=None, **kwargs):
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
    _db.session.add(r)
    _db.session.commit()
    return r


def _login(client, user):
    client.post("/auth/login", data={"email": user.email, "password": PASSWORD})


# ---------------------------------------------------------------------------
# _get_country_code
# ---------------------------------------------------------------------------

class TestGetCountryCode:
    def test_defaults_to_au(self, app, monkeypatch):
        monkeypatch.delenv("NAGER_DATE_COUNTRY", raising=False)
        assert _get_country_code() == "AU"

    def test_reads_env_var(self, app, monkeypatch):
        monkeypatch.setenv("NAGER_DATE_COUNTRY", "US")
        assert _get_country_code() == "US"


# ---------------------------------------------------------------------------
# _cached_holidays
# ---------------------------------------------------------------------------

class TestCachedHolidays:
    def test_empty_when_no_rows(self, db):
        assert _cached_holidays("AU", 2026) == []

    def test_returns_rows_matching_country_and_year(self, db):
        _insert_holiday(date(2026, 1, 1), "AU", "New Year's Day")
        results = _cached_holidays("AU", 2026)
        assert len(results) == 1
        assert results[0].name == "New Year's Day"

    def test_excludes_different_country(self, db):
        _insert_holiday(date(2026, 1, 1), "NZ", "New Year's Day")
        assert _cached_holidays("AU", 2026) == []

    def test_excludes_different_year(self, db):
        _insert_holiday(date(2025, 1, 1), "AU", "New Year's Day 2025")
        assert _cached_holidays("AU", 2026) == []


# ---------------------------------------------------------------------------
# _fetch_and_cache
# ---------------------------------------------------------------------------

class TestFetchAndCache:
    def test_inserts_and_returns_holidays(self, db, monkeypatch):
        payload = [
            {"date": "2026-01-01", "localName": "New Year's Day", "name": "New Year's Day"},
            {"date": "2026-04-25", "localName": "Anzac Day", "name": "Anzac Day"},
        ]
        monkeypatch.setattr("app.services.holidays.urlopen", _fake_urlopen(payload))
        results = _fetch_and_cache("AU", 2026)
        assert len(results) == 2
        names = {r.name for r in results}
        assert "New Year's Day" in names
        assert "Anzac Day" in names
        rows = _db.session.execute(_db.select(PublicHoliday)).scalars().all()
        assert len(rows) == 2

    def test_on_conflict_do_nothing_prevents_duplicates(self, db, monkeypatch):
        payload = [
            {"date": "2026-01-01", "localName": "New Year's Day", "name": "New Year's Day"}
        ]
        monkeypatch.setattr("app.services.holidays.urlopen", _fake_urlopen(payload))
        _fetch_and_cache("AU", 2026)
        _fetch_and_cache("AU", 2026)
        rows = _db.session.execute(_db.select(PublicHoliday)).scalars().all()
        assert len(rows) == 1

    def test_url_error_returns_empty_list(self, db, monkeypatch):
        def _raise(url, timeout=5):
            raise URLError("connection failed")
        monkeypatch.setattr("app.services.holidays.urlopen", _raise)
        assert _fetch_and_cache("AU", 2026) == []

    def test_malformed_json_returns_empty_list(self, db, monkeypatch):
        monkeypatch.setattr(
            "app.services.holidays.urlopen",
            lambda url, timeout=5: _FakeResponse(b"not-json"),
        )
        assert _fetch_and_cache("AU", 2026) == []

    def test_local_name_preferred_over_name(self, db, monkeypatch):
        payload = [
            {"date": "2026-01-01", "localName": "Jour de l'An", "name": "New Year's Day"}
        ]
        monkeypatch.setattr("app.services.holidays.urlopen", _fake_urlopen(payload))
        results = _fetch_and_cache("AU", 2026)
        assert results[0].name == "Jour de l'An"


# ---------------------------------------------------------------------------
# is_public_holiday
# ---------------------------------------------------------------------------

class TestIsPublicHoliday:
    def test_returns_none_for_non_matching_date(self, db, monkeypatch):
        monkeypatch.delenv("NAGER_DATE_COUNTRY", raising=False)
        _insert_holiday(date(2026, 1, 1), "AU", "New Year's Day")
        assert is_public_holiday(date(2026, 1, 2)) is None

    def test_returns_name_from_cache(self, db, monkeypatch):
        monkeypatch.delenv("NAGER_DATE_COUNTRY", raising=False)
        _insert_holiday(date(2026, 1, 1), "AU", "New Year's Day")
        assert is_public_holiday(date(2026, 1, 1)) == "New Year's Day"

    def test_fetches_from_api_on_cache_miss(self, db, monkeypatch):
        monkeypatch.delenv("NAGER_DATE_COUNTRY", raising=False)
        payload = [
            {"date": "2026-01-01", "localName": "New Year's Day", "name": "New Year's Day"}
        ]
        monkeypatch.setattr("app.services.holidays.urlopen", _fake_urlopen(payload))
        assert is_public_holiday(date(2026, 1, 1)) == "New Year's Day"

    def test_returns_none_when_api_returns_no_match(self, db, monkeypatch):
        monkeypatch.delenv("NAGER_DATE_COUNTRY", raising=False)
        payload = [
            {"date": "2026-01-01", "localName": "New Year's Day", "name": "New Year's Day"}
        ]
        monkeypatch.setattr("app.services.holidays.urlopen", _fake_urlopen(payload))
        assert is_public_holiday(date(2026, 6, 15)) is None

    def test_respects_country_env_var(self, db, monkeypatch):
        monkeypatch.setenv("NAGER_DATE_COUNTRY", "US")
        _insert_holiday(date(2026, 7, 4), "US", "Independence Day")
        assert is_public_holiday(date(2026, 7, 4)) == "Independence Day"


# ---------------------------------------------------------------------------
# Route: public holiday acknowledgment flow
# ---------------------------------------------------------------------------

class TestHolidayBookingFlow:
    def test_warning_shown_without_acknowledgment(self, client, tenant, db, monkeypatch):
        monkeypatch.delenv("NAGER_DATE_COUNTRY", raising=False)
        user = _make_active_user(tenant_id=tenant.id)
        r = _make_resource(tenant_id=tenant.id)
        _insert_holiday(HOLIDAY_DATE, "AU", "New Year's Day")
        _login(client, user)
        resp = client.post(
            f"/resources/{r.id}/book",
            data={
                "start_datetime": f"{HOLIDAY_DATE}T10:00",
                "end_datetime": f"{HOLIDAY_DATE}T12:00",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"public holiday" in resp.data
        assert b"New Year" in resp.data
        assert b'name="holiday_acknowledged"' in resp.data
        bookings = _db.session.execute(_db.select(Booking)).scalars().all()
        assert bookings == []

    def test_booking_created_with_acknowledgment(self, client, tenant, db, monkeypatch):
        monkeypatch.delenv("NAGER_DATE_COUNTRY", raising=False)
        user = _make_active_user(tenant_id=tenant.id)
        r = _make_resource(tenant_id=tenant.id)
        _insert_holiday(HOLIDAY_DATE, "AU", "New Year's Day")
        _login(client, user)
        resp = client.post(
            f"/resources/{r.id}/book",
            data={
                "start_datetime": f"{HOLIDAY_DATE}T10:00",
                "end_datetime": f"{HOLIDAY_DATE}T12:00",
                "holiday_acknowledged": "1",
            },
        )
        assert resp.status_code == 302
        assert "/my-bookings" in resp.headers["Location"]
        booking = _db.session.execute(_db.select(Booking)).scalar_one()
        assert booking.user_id == user.id
        assert booking.resource_id == r.id
        assert booking.status == BookingStatus.active

    def test_non_holiday_booking_skips_warning(self, client, tenant, db, monkeypatch):
        monkeypatch.delenv("NAGER_DATE_COUNTRY", raising=False)
        # Prime the cache with a holiday on a different date so _fetch_and_cache
        # is never called (avoids a real network request).
        _insert_holiday(HOLIDAY_DATE, "AU", "New Year's Day")
        user = _make_active_user(tenant_id=tenant.id)
        r = _make_resource(tenant_id=tenant.id)
        _login(client, user)
        resp = client.post(
            f"/resources/{r.id}/book",
            data={
                "start_datetime": f"{NON_HOLIDAY_DATE}T10:00",
                "end_datetime": f"{NON_HOLIDAY_DATE}T12:00",
            },
        )
        assert resp.status_code == 302
        assert "/my-bookings" in resp.headers["Location"]
        booking = _db.session.execute(_db.select(Booking)).scalar_one()
        assert booking.status == BookingStatus.active
