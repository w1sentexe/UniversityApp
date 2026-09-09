from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Общая база ORM-моделей; от неё же берётся metadata для создания таблиц.

    Каждая модель обязана наследоваться отсюда и быть импортирована в
    app/entities/models/__init__.py — иначе её таблицы не окажется в metadata
    и create_all её не создаст.
    """


def utcnow() -> datetime:
    return datetime.now(UTC)
