"""Бизнес-логика расписания: чтение по группе.

Загрузки здесь нет намеренно: расписание приходит разовой ручной командой
(tools/schedule_import), а не запросом к API. Держать разбор Excel в сервисе
значило бы тянуть openpyxl и знание про разметку деканатских выгрузок в
рантайм, которому они не нужны.
"""

from fastapi import Depends

from app.entities.schemas.schedule import ScheduleModel
from app.repository.schedule_repository import ScheduleRepository, get_schedule_repository


class ScheduleService:
    def __init__(self, repo: ScheduleRepository) -> None:
        self._repo = repo

    async def for_group(self, group_name: str) -> ScheduleModel | None:
        """Расписание группы; None, если оно ещё не загружено."""
        return await self._repo.get(group_name)

    async def groups(self) -> list[str]:
        return await self._repo.groups()


def get_schedule_service(repo: ScheduleRepository = Depends(get_schedule_repository)) -> ScheduleService:
    """Зависимость FastAPI: сервис поверх репозитория текущего запроса."""
    return ScheduleService(repo)
