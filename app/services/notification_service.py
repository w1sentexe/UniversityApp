import asyncio
import json
from datetime import timedelta

from pywebpush import WebPushException, webpush

from app.config import settings
from app.db.models import NotificationOutbox, PushSubscription, utcnow
from app.logging_config import get_logger
from app.repository.notification_repository import NotificationRepository

log = get_logger(__name__)


class NotificationService:
    def __init__(self, repo: NotificationRepository) -> None:
        self._repo = repo

    async def subscribe(self, *, zach_number: str, endpoint: str, p256dh: str, auth: str) -> None:
        await self._repo.upsert_subscription(
            zach_number=zach_number,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
        )

    async def unsubscribe(self, endpoint: str) -> bool:
        return await self._repo.disable_subscription(endpoint)

    async def dispatch_pending(self, *, limit: int = 100) -> int:
        if not settings.notifications.vapid_private_key:
            log.debug("Push dispatch skipped: NOTIFICATIONS_VAPID_PRIVATE_KEY is not configured")
            return 0

        pending = await self._repo.pending_outbox(limit=limit)
        sent = 0
        for item, subscription in pending:
            try:
                await self._send(item, subscription)
            except WebPushException as exc:
                await self._handle_webpush_error(item, subscription, exc)
            except Exception as exc:
                await self._mark_retry_or_failed(item, str(exc))
            else:
                await self._repo.mark_sent(item)
                sent += 1

        if pending:
            await self._repo.commit()
            log.info("Push dispatch completed", attempted=len(pending), sent=sent)
        return sent

    async def _send(self, item: NotificationOutbox, subscription: PushSubscription) -> None:
        payload = json.loads(item.payload)
        subscription_info = {
            "endpoint": subscription.endpoint,
            "keys": {
                "p256dh": subscription.p256dh,
                "auth": subscription.auth,
            },
        }
        claims = {"sub": settings.notifications.vapid_subject}
        await asyncio.to_thread(
            webpush,
            subscription_info=subscription_info,
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=settings.notifications.vapid_private_key,
            vapid_claims=claims,
            ttl=settings.notifications.ttl_seconds,
            timeout=10,
        )

    async def _handle_webpush_error(
        self,
        item: NotificationOutbox,
        subscription: PushSubscription,
        exc: WebPushException,
    ) -> None:
        status_code = exc.response.status_code if exc.response is not None else None
        error = f"WebPushException status={status_code}: {exc}"
        if status_code in {404, 410}:
            await self._repo.disable_broken_subscription(subscription)
            await self._repo.mark_failed(item, error)
            return
        await self._mark_retry_or_failed(item, error)

    async def _mark_retry_or_failed(self, item: NotificationOutbox, error: str) -> None:
        if item.attempts + 1 >= settings.notifications.max_attempts:
            await self._repo.mark_failed(item, error)
            return
        delay = min(60 * 2**item.attempts, 3600)
        await self._repo.mark_retry(item, error, utcnow() + timedelta(seconds=delay))
