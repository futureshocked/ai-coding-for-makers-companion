import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class BookingStatus(str, enum.Enum):
    active = "active"
    cancelled_by_member = "cancelled_by_member"
    cancelled_by_admin = "cancelled_by_admin"
    cancelled_downtime = "cancelled_downtime"
    completed = "completed"
    returned = "returned"


class Booking(db.Model):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_bookings_ends_after_starts"),
        Index("ix_bookings_resource_time", "resource_id", "starts_at", "ends_at"),
        Index(
            "ix_bookings_active_resource_time",
            "tenant_id",
            "resource_id",
            "starts_at",
            "ends_at",
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[BookingStatus] = mapped_column(
        SAEnum(BookingStatus, name="booking_status"),
        nullable=False,
        default=BookingStatus.active,
    )
    edit_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    original_starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    original_ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    returned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recurrence_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], back_populates="bookings"
    )
    resource: Mapped["Resource"] = relationship(
        "Resource", back_populates="bookings"
    )
    cancelled_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[cancelled_by_user_id]
    )
    notifications: Mapped[list["NotificationLog"]] = relationship(
        "NotificationLog", back_populates="booking", lazy="dynamic"
    )
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant")
