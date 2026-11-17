import enum
import re
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SAEnum, Index, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class TenantStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    suspended = "suspended"


SUBDOMAIN_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,30}[a-z0-9]$")


class Tenant(db.Model):
    __tablename__ = "tenants"
    __table_args__ = (
        Index("uq_tenants_subdomain_lower", text("lower(subdomain)"), unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    subdomain: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TenantStatus] = mapped_column(
        SAEnum(TenantStatus, name="tenant_status"),
        nullable=False,
        default=TenantStatus.pending,
    )
    is_listed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
