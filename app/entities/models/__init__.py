"""ORM-модели — единственное описание структуры таблиц.

Файл на таблицу; здесь только сборка. Импорт всех моделей обязателен и в этом
его смысл: пока модуль модели не выполнен, её таблицы нет в Base.metadata,
и create_all про неё не знает.

Рейтинг и группы — снимок сайта, целиком заменяемый каждым циклом парсинга;
расписание живёт своей жизнью (см. GroupSchedule).
"""

from app.entities.models.base import Base, utcnow
from app.entities.models.grade_record import GradeRecord
from app.entities.models.group_schedule import GroupSchedule
from app.entities.models.notification_outbox import NotificationOutbox
from app.entities.models.push_subscription import PushSubscription
from app.entities.models.rating_record import RatingRecord
from app.entities.models.rating_watch_state import RatingWatchState
from app.entities.models.snapshot_meta import SnapshotMeta
from app.entities.models.student_group import StudentGroup

# Таблицы снапшота рейтинга в порядке очистки перед заливкой нового цикла.
# Расписание сюда намеренно не входит — у него свой цикл обновления.
SNAPSHOT_MODELS = (RatingRecord, GradeRecord, StudentGroup)

__all__ = [
    "SNAPSHOT_MODELS",
    "Base",
    "GradeRecord",
    "GroupSchedule",
    "NotificationOutbox",
    "PushSubscription",
    "RatingRecord",
    "RatingWatchState",
    "SnapshotMeta",
    "StudentGroup",
    "utcnow",
]
