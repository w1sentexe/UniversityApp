from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.entities.models.base import Base


class GradeRecord(Base):
    """Ведомость без контрольных точек — только итоговая оценка.

    Ключ и его свойства те же, что у RatingRecord: составной, и он же индекс
    запроса «записи студента по виду ведомости».

    grade объявлен текстом, хотя по смыслу оценка: источник присылает и числа,
    и прочерк «-», и словесные оценки вроде «зачтено».
    """

    __tablename__ = "grade_record"

    zach_number: Mapped[str] = mapped_column(Text, primary_key=True)
    ved_type: Mapped[str] = mapped_column(Text, primary_key=True)
    subject_name: Mapped[str] = mapped_column(Text, primary_key=True)
    grade: Mapped[str | None] = mapped_column(Text)
