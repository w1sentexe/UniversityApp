from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RatingRecord
from app.entities.notification_models import RatingMutationRequest, RatingMutationResponse
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
