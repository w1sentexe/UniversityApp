from datetime import time
from enum import Enum

from pydantic import BaseModel


class LessonType(str, Enum):
    lecture = "lecture"
    practice = "practice"
    lab = "lab"
    seminar = "seminar"
    other = "other"


class LessonModel(BaseModel):
    start_time: time
    end_time: time
    name: str
    lesson_type: LessonType
    teacher_name: str | None  # в расписании иногда это поле пропущено
    classroom: str | None  # в расписании иногда это поле пропущено
    subgroups: list[int]


class WeeklyScheduleModel(BaseModel):
    monday: list[LessonModel] = []
    tuesday: list[LessonModel] = []
    wednesday: list[LessonModel] = []
    thursday: list[LessonModel] = []
    friday: list[LessonModel] = []
    saturday: list[LessonModel] = []


class ScheduleModel(BaseModel):
    numerator: WeeklyScheduleModel
    denominator: WeeklyScheduleModel


class GroupScheduleModel(BaseModel):
    """Расписание группы.

    schedule = None означает, что для группы расписание ещё не загружено, —
    это не ошибка, поэтому роутер отвечает 200, а не 404: клиенту достаточно
    отличить «нет данных» от «нет группы», и он показывает разные экраны.
    """

    name: str
    schedule: ScheduleModel | None = None
