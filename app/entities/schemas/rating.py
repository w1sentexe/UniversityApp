"""Всё про рейтинг: виды ведомостей, оценки и две формы записи.

Одним файлом намеренно: тема одна, и типы отсюда почти всегда берутся вместе —
ведомость приходит либо рейтинговой, либо оценочной, а VedType нужен обеим.
"""

from enum import Enum

from pydantic import BaseModel


class VedType(str, Enum):
    """Название видов ведомостей с сайта ВГУИТ."""

    ZACHET = "Зачет"
    EKZAMEN = "Экзамен"
    VYPUSKNAYA_RABOTA = "Выпуская работа"  # «Выпуская работа» — без «н», это написание источника
    GOSEKZAMEN = "ГосЭкзамен"
    KONTROLNAYA_RABOTA = "Контрольная работа"
    KURSOVAYA_RABOTA = "Курсовая работа"
    KURSOVOY_PROEKT = "Курсовой проект"
    PRAKTIKA = "Практика"
    REFERAT = "Реферат"


RATING_VED_TYPES: frozenset[VedType] = frozenset(
    {
        VedType.ZACHET,
        VedType.EKZAMEN,
    }
)

NOT_RATING_VED_TYPES: frozenset[VedType] = frozenset(VedType) - RATING_VED_TYPES


class Grade(str, Enum):
    """Сокращённые оценки, как приходят с сайта."""

    OTLICHNO = "Отл"
    HOROSHO = "Хор"
    UDOVLETVORITELNO = "Удовл"
    NEUDOVLETVORITELNO = "Неуд"
    ZACHTENO = "Зачтено"
    NE_ZACHTENO = "Не зачтено"


class NotRatingVedModel(BaseModel):
    zach_number: str
    subject_name: str
    ved_type: VedType | str
    grade: Grade | str = "-"  # т.к может прийти -


class SubjectScore(BaseModel):
    score: int | str = "-"
    weight: int | str = "-"


class ControlPoint(BaseModel):
    kt_num: int
    lecture: SubjectScore
    practice: SubjectScore
    lab: SubjectScore
    other: SubjectScore
    total: int | str = "-"


class RatingVedModel(BaseModel):
    zach_number: str
    subject_name: str
    ved_type: VedType | str
    control_points: list[ControlPoint] = []
    final_rating: int | str = "-"
