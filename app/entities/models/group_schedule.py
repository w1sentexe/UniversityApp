from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.entities.models.base import Base


class GroupSchedule(Base):
    """Расписание группы одним JSON-документом.

    Живёт отдельно от снапшота рейтинга: источник другой (выгрузка Excel),
    и обновляется вручную раз в семестр, а не каждые полчаса. Поэтому цикл
    парсинга эту таблицу не чистит — её нет в SNAPSHOT_MODELS.

    Документ хранится целиком, а не разложенным по строкам «занятие»: расписание
    группы всегда читается и заменяется целиком, выборок по отдельной паре нет.
    Структуру описывает ScheduleModel (app/entities/schemas/schedule.py).
    """

    __tablename__ = "group_schedule"

    group_name: Mapped[str] = mapped_column(Text, primary_key=True)
    schedule: Mapped[str] = mapped_column(Text, nullable=False)
