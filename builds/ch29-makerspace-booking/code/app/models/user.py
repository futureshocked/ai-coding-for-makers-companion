import enum
from datetime import datetime
from typing import Optional

from flask_login import UserMixin
from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class UserStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    frozen = "frozen"
    rejected = "rejected"


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_tenant_email",
            "tenant_id", text("lower(email)"),
            unique=True,
            postgresql_where=text("tenant_id IS NOT NULL"),
        ),
        Index(
            "uq_users_super_admin_email",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("tenant_id IS NULL AND is_super_admin = true"),
        ),
        CheckConstraint(
            "(tenant_id IS NULL) = is_super_admin",
            name="ck_users_super_admin_invariant",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tenants.id"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    avatar: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status"),
        nullable=False,
        default=UserStatus.pending,
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_super_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    rejection_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notification_prefs: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    tier_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    bookings: Mapped[list["Booking"]] = relationship(
        "Booking",
        foreign_keys="Booking.user_id",
        back_populates="user",
        lazy="dynamic",
    )
    sent_notifications: Mapped[list["NotificationLog"]] = relationship(
        "NotificationLog", back_populates="user", lazy="dynamic"
    )
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant")
