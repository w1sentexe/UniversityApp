from datetime import datetime

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.entities.models.base import Base, utcnow


class SnapshotMeta(Base):
    """Версия последнего успешно записанного снапшота рейтинга."""

    __tablename__ = "snapshot_meta"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    parsing_year: Mapped[str] = mapped_column(Text, nullable=False)
    parsing_semester: Mapped[str] = mapped_column(Text, nullable=False)
    rating_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    grade_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    group_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
