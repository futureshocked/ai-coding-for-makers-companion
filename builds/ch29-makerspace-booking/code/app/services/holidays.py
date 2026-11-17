import json
import os
from datetime import date
from urllib.error import URLError
from urllib.request import urlopen

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.extensions import db
from app.models.public_holiday import PublicHoliday

_NAGER_BASE = "https://date.nager.at/api/v3/PublicHolidays"


def _get_country_code() -> str:
    return os.environ.get("NAGER_DATE_COUNTRY", "AU")


def _cached_holidays(country_code: str, year: int) -> list[PublicHoliday]:
    return db.session.execute(
        db.select(PublicHoliday).where(
            PublicHoliday.country_code == country_code,
            db.extract("year", PublicHoliday.date) == year,
        )
    ).scalars().all()


def _fetch_and_cache(country_code: str, year: int) -> list[PublicHoliday]:
    url = f"{_NAGER_BASE}/{year}/{country_code}"
    try:
        with urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except (URLError, OSError, ValueError):
        return []

    rows = [
        {
            "date": date.fromisoformat(item["date"]),
            "country_code": country_code,
            "name": item.get("localName") or item.get("name", "Public Holiday"),
        }
        for item in data
    ]

    if rows:
        db.session.execute(
            pg_insert(PublicHoliday).values(rows).on_conflict_do_nothing()
        )
        db.session.commit()

    return _cached_holidays(country_code, year)


def is_public_holiday(check_date: date) -> str | None:
    """Return the holiday name if check_date is a public holiday, else None."""
    country_code = _get_country_code()
    year = check_date.year

    holidays = _cached_holidays(country_code, year)
    if not holidays:
        holidays = _fetch_and_cache(country_code, year)

    for h in holidays:
        if h.date == check_date:
            return h.name

    return None
