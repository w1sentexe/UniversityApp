from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.config import settings
from app.entities.notification_models import (
    NotificationDebugModel,
    NotificationStatusModel,
    SubscribeRequest,
    UnsubscribeRequest,
    VapidPublicKeyModel,
)
from app.repository.notification_repository import NotificationRepository, get_notification_repository
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/vapid-public-key")
async def vapid_public_key() -> VapidPublicKeyModel:
    public_key = settings.notifications.vapid_public_key
    if not public_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Web Push is not configured")
    return VapidPublicKeyModel(public_key=public_key)


@router.get("/status")
async def notification_status() -> NotificationStatusModel:
    configured = bool(settings.notifications.vapid_public_key and settings.notifications.vapid_private_key)
    return NotificationStatusModel(
        supported=configured,
        enabled=configured,
        reason=None if configured else "Web Push is not configured",
    )


@router.get("/test/debug/{zach_number}")
async def debug_notifications(
    zach_number: str,
    x_test_token: str | None = Header(default=None),
    repo: NotificationRepository = Depends(get_notification_repository),
) -> NotificationDebugModel:
    if not settings.test.mutation_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test endpoint is disabled")
    if x_test_token != settings.test.mutation_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid test token")
    return NotificationDebugModel(**await repo.debug_state(zach_number))


@router.post("/subscribe", status_code=status.HTTP_204_NO_CONTENT)
async def subscribe(
    request: SubscribeRequest,
    repo: NotificationRepository = Depends(get_notification_repository),
) -> None:
    if not settings.notifications.vapid_public_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Web Push is not configured")
    await NotificationService(repo).subscribe(
        zach_number=request.zach_number,
        endpoint=request.subscription.endpoint,
        p256dh=request.subscription.keys.p256dh,
        auth=request.subscription.keys.auth,
    )


@router.post("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(
    request: UnsubscribeRequest,
    repo: NotificationRepository = Depends(get_notification_repository),
) -> None:
    await NotificationService(repo).unsubscribe(request.endpoint)
