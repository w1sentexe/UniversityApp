from sqlalchemy import Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.entities.models.base import Base


class StudentGroup(Base):
    """Связка «зачётка → группа».

    Выводится из того же обхода, что и рейтинг: ссылки на ведомости собираются
    по группам, а номера зачёток есть в самих записях
    (см. app/services/group_extractor.py).
    """

    __tablename__ = "student_group"

    zach_number: Mapped[str] = mapped_column(Text, primary_key=True)
    group_name: Mapped[str] = mapped_column(Text, nullable=False)

    # Обратный разрез «кто в группе» — понадобится расписанию.
    __table_args__ = (Index("idx_student_group_name", "group_name"),)
