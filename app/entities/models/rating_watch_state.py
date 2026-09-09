from datetime import datetime

from sqlalchemy import DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.entities.models.base import Base, utcnow


class RatingWatchState(Base):
    """Последнее известное значение рейтинга для подписанной зачётки."""

    __tablename__ = "rating_watch_state"

    zach_number: Mapped[str] = mapped_column(Text, primary_key=True)
    ved_type: Mapped[str] = mapped_column(Text, primary_key=True)
    subject_name: Mapped[str] = mapped_column(Text, primary_key=True)
    last_value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
