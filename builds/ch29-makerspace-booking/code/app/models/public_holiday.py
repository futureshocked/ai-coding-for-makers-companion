from datetime import date as date_type

from sqlalchemy import BigInteger, Date, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class PublicHoliday(db.Model):
    __tablename__ = "public_holidays"
    __table_args__ = (UniqueConstraint("country_code", "date", "name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    country_code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
