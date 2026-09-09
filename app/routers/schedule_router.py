from fastapi import APIRouter, Depends

from app.entities.schemas.schedule import GroupScheduleModel
from app.services.schedule_service import ScheduleService, get_schedule_service

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.get("/groups")
async def groups(
    schedule_service: ScheduleService = Depends(get_schedule_service),
) -> list[str]:
    """Группы, для которых расписание загружено."""
    return await schedule_service.groups()


@router.get("/{group_name}")
async def by_group(
    group_name: str,
    schedule_service: ScheduleService = Depends(get_schedule_service),
) -> GroupScheduleModel:
    """Расписание группы: недели → дни → занятия, отсортированные по времени."""
    schedule = await schedule_service.for_group(group_name)
    return GroupScheduleModel(name=group_name, schedule=schedule)
