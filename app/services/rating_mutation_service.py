import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RatingRecord
from app.entities.notification_models import (
    ControlPointMutationRequest,
    ControlPointMutationResponse,
    RatingMutationRequest,
    RatingMutationResponse,
)
from app.repository.notification_repository import NotificationRepository


class RatingMutationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._notifications = NotificationRepository(session)

    async def update_final_rating(self, request: RatingMutationRequest) -> RatingMutationResponse:
        value = str(request.final_rating).strip()
        row = await self._session.scalar(
            select(RatingRecord).where(
                RatingRecord.zach_number == request.zach_number,
                RatingRecord.ved_type == request.ved_type.value,
                RatingRecord.subject_name == request.subject_name,
            )
        )
        if row is None:
            row = RatingRecord(
                zach_number=request.zach_number,
                ved_type=request.ved_type.value,
                subject_name=request.subject_name,
                final_rating=value,
                control_points="[]",
            )
            self._session.add(row)
        else:
            row.final_rating = value

        queued = await self._notifications.enqueue_current_rating_changes(
            cycle_id=f"manual-{uuid4().hex}",
            zach_numbers=[request.zach_number],
        )
        await self._session.commit()
        return RatingMutationResponse(
            zach_number=request.zach_number,
            ved_type=request.ved_type.value,
            subject_name=request.subject_name,
            final_rating=value,
            queued_notifications=queued,
        )

    async def update_control_point_total(self, request: ControlPointMutationRequest) -> ControlPointMutationResponse:
        value = str(request.total).strip()
        row = await self._session.scalar(
            select(RatingRecord).where(
                RatingRecord.zach_number == request.zach_number,
                RatingRecord.ved_type == request.ved_type.value,
                RatingRecord.subject_name == request.subject_name,
            )
        )
        if row is None:
            row = RatingRecord(
                zach_number=request.zach_number,
                ved_type=request.ved_type.value,
                subject_name=request.subject_name,
                final_rating="-",
                control_points="[]",
            )
            self._session.add(row)

        points = _control_points(row.control_points)
        point = next((item for item in points if _kt_num(item) == request.kt_num), None)
        if point is None:
            point = _empty_control_point(request.kt_num)
            points.append(point)
            points.sort(key=lambda item: int(item.get("kt_num") or 0))

        point["total"] = value
        row.control_points = json.dumps(points, ensure_ascii=False)

        queued = await self._notifications.enqueue_current_rating_changes(
            cycle_id=f"manual-{uuid4().hex}",
            zach_numbers=[request.zach_number],
        )
        await self._session.commit()
        return ControlPointMutationResponse(
            zach_number=request.zach_number,
            ved_type=request.ved_type.value,
            subject_name=request.subject_name,
            kt_num=request.kt_num,
            total=value,
            queued_notifications=queued,
        )


def _control_points(raw: str) -> list[dict]:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _empty_control_point(kt_num: int) -> dict:
    empty_score = {"score": "-", "weight": "-"}
    return {
        "kt_num": kt_num,
        "lecture": dict(empty_score),
        "practice": dict(empty_score),
        "lab": dict(empty_score),
        "other": dict(empty_score),
        "total": "-",
    }


def _kt_num(point: dict) -> int | None:
    try:
        return int(point.get("kt_num"))
    except (TypeError, ValueError):
        return None
