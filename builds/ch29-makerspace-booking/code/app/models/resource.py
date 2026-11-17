import enum
import os
from datetime import datetime, time
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def _env_time(var: str, fallback: time) -> time:
    val = os.environ.get(var, "")
    try:
        h, m = val.split(":")
        return time(int(h), int(m))
    except Exception:
        return fallback


DEFAULT_WEEKDAY_START = _env_time("DEFAULT_WEEKDAY_START", time(9, 0))
DEFAULT_WEEKDAY_END   = _env_time("DEFAULT_WEEKDAY_END",   time(18, 0))


class ResourceCategory(str, enum.Enum):
    meeting_room = "meeting_room"
    equipment = "equipment"
    workbench = "workbench"
    hot_spot = "hot_spot"
    book = "book"


class ResourceState(str, enum.Enum):
    available = "available"
    out_of_service = "out_of_service"


class Resource(db.Model):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    category: Mapped[ResourceCategory] = mapped_column(
        SAEnum(ResourceCategory, name="resource_category"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    identifier_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    weekday_start: Mapped[time]           = mapped_column(Time, nullable=False, default=DEFAULT_WEEKDAY_START)
    weekday_end:   Mapped[time]           = mapped_column(Time, nullable=False, default=DEFAULT_WEEKDAY_END)
    weekend_start: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    weekend_end:   Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    state: Mapped[ResourceState] = mapped_column(
        SAEnum(ResourceState, name="resource_state"),
        nullable=False,
        default=ResourceState.available,
    )
    thumbnail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    bookings: Mapped[list["Booking"]] = relationship(
        "Booking", back_populates="resource", lazy="dynamic"
    )
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant")
