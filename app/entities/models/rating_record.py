from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.entities.models.base import Base


class RatingRecord(Base):
    """Ведомость с контрольными точками (обычно зачёт или экзамен).

    Отдельная таблица от GradeRecord, а не общая с nullable-колонками: форму
    записи выбирает не вид ведомости, а наличие колонок КТ в источнике
    (см. is_rating в app/parser/html_parser.py), поэтому зачёт может оказаться
    и здесь, и там.

    control_points хранится одним JSON-полем, а не отдельной таблицей.
    Контрольные точки всегда читаются целиком вместе со своей записью и по
    отдельности не запрашиваются, поэтому нормализация дала бы соединение на
    каждый показ рейтинга без выигрыша. Понадобится выборка по КТ — в SQLite
    есть json_extract, схему менять не придётся.

    Составной первичный ключ заодно работает индексом основного запроса
    «записи студента по виду ведомости»: два первых поля — его левый префикс.

    final_rating объявлен текстом, хотя по смыслу число: источник присылает и
    числа, и прочерк «-». Приведение делает pydantic на выходе из сервиса.
    """

    __tablename__ = "rating_record"

    zach_number: Mapped[str] = mapped_column(Text, primary_key=True)
    ved_type: Mapped[str] = mapped_column(Text, primary_key=True)
    subject_name: Mapped[str] = mapped_column(Text, primary_key=True)
    final_rating: Mapped[str | None] = mapped_column(Text)
    control_points: Mapped[str] = mapped_column(Text, nullable=False)
