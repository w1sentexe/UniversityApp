import json
from collections import defaultdict
from uuid import uuid4

from fastapi import Depends
from sqlalchemy import and_, distinct, func, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NotificationOutbox, PushSubscription, RatingRecord, RatingWatchState, utcnow
from app.db.session import get_session
from app.logging_config import get_logger

log = get_logger(__name__)

_DASH_VALUES = {"", "-", "—"}


def normalize_rating_value(value: str | int | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if normalized in _DASH_VALUES:
        return None
    return normalized


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def has_vapid_public_key(self, public_key: str | None) -> bool:
        return bool(public_key)

    async def upsert_subscription(
        self,
        *,
        zach_number: str,
        endpoint: str,
        p256dh: str,
        auth: str,
    ) -> PushSubscription:
        now = utcnow()
        subscription = await self._session.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
        if subscription is None:
            subscription = PushSubscription(
                zach_number=zach_number,
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
                enabled=True,
                created_at=now,
                updated_at=now,
            )
            self._session.add(subscription)
        else:
            subscription.zach_number = zach_number
            subscription.p256dh = p256dh
            subscription.auth = auth
            subscription.enabled = True
            subscription.failure_count = 0
            subscription.updated_at = now

        await self._seed_watch_state(zach_number)
        await self._session.commit()
        await self._session.refresh(subscription)
        log.info("Push subscription saved", zach_number=zach_number, subscription_id=subscription.id)
        return subscription

    async def disable_subscription(self, endpoint: str) -> bool:
        subscription = await self._session.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
        if subscription is None:
            return False
        subscription.enabled = False
        subscription.updated_at = utcnow()
        await self._session.commit()
        log.info("Push subscription disabled", subscription_id=subscription.id)
        return True

    async def debug_state(self, zach_number: str) -> dict[str, int | str]:
        enabled_subscriptions = await self._session.scalar(
            select(func.count())
            .select_from(PushSubscription)
            .where(PushSubscription.zach_number == zach_number, PushSubscription.enabled.is_(True))
        )
        disabled_subscriptions = await self._session.scalar(
            select(func.count())
            .select_from(PushSubscription)
            .where(PushSubscription.zach_number == zach_number, PushSubscription.enabled.is_(False))
        )
        watch_states = await self._session.scalar(
            select(func.count()).select_from(RatingWatchState).where(RatingWatchState.zach_number == zach_number)
        )
        outbox_counts = {
            status: int(total)
            for status, total in (
                await self._session.execute(
                    select(NotificationOutbox.status, func.count())
                    .join(PushSubscription, NotificationOutbox.subscription_id == PushSubscription.id)
                    .where(PushSubscription.zach_number == zach_number)
                    .group_by(NotificationOutbox.status)
                )
            ).all()
        }
        return {
            "zach_number": zach_number,
            "enabled_subscriptions": int(enabled_subscriptions or 0),
            "disabled_subscriptions": int(disabled_subscriptions or 0),
            "watch_states": int(watch_states or 0),
            "pending_outbox": outbox_counts.get("pending", 0),
            "sent_outbox": outbox_counts.get("sent", 0),
            "failed_outbox": outbox_counts.get("failed", 0),
        }

    async def enqueue_current_rating_changes(
        self,
        *,
        cycle_id: str | None = None,
        zach_numbers: list[str] | None = None,
    ) -> int:
        cycle = cycle_id or uuid4().hex
        zachs = await self._active_zachs(zach_numbers)
        if not zachs:
            return 0

        current_rows = (
            await self._session.execute(select(RatingRecord).where(RatingRecord.zach_number.in_(zachs)))
        ).scalars()
        current = list(current_rows)
        if not current:
            return 0

        states = await self._state_map(zachs)
        initialized = {key[0] for key in states}
        state_rows: list[dict] = []
        changes_by_zach: dict[str, list[dict]] = defaultdict(list)
        now = utcnow()

        for row in current:
            new_value = normalize_rating_value(row.final_rating)
            if new_value is None:
                continue

            key = (row.zach_number, row.ved_type, row.subject_name)
            old_value = states.get(key)
            if old_value is None and row.zach_number in initialized:
                changes_by_zach[row.zach_number].append(
                    {
                        "subject_name": row.subject_name,
                        "ved_type": row.ved_type,
                        "old_value": None,
                        "new_value": new_value,
                    }
                )
            elif old_value is not None and old_value != new_value:
                changes_by_zach[row.zach_number].append(
                    {
                        "subject_name": row.subject_name,
                        "ved_type": row.ved_type,
                        "old_value": old_value,
                        "new_value": new_value,
                    }
                )

            if old_value != new_value:
                state_rows.append(
                    {
                        "zach_number": row.zach_number,
                        "ved_type": row.ved_type,
                        "subject_name": row.subject_name,
                        "last_value": new_value,
                        "updated_at": now,
                    }
                )

        if state_rows:
            await self._session.execute(insert(RatingWatchState).prefix_with("OR REPLACE"), state_rows)

        if not changes_by_zach:
            return 0

        subscriptions = (
            await self._session.execute(
                select(PushSubscription).where(
                    PushSubscription.enabled.is_(True),
                    PushSubscription.zach_number.in_(changes_by_zach.keys()),
                )
            )
        ).scalars()
        outbox_rows = []
        for subscription in subscriptions:
            changes = changes_by_zach.get(subscription.zach_number)
            if not changes:
                continue
            outbox_rows.append(
                NotificationOutbox(
                    subscription_id=subscription.id,
                    cycle_id=cycle,
                    payload=json.dumps(_payload(subscription.zach_number, changes), ensure_ascii=False),
                    status="pending",
                    attempts=0,
                    created_at=now,
                    updated_at=now,
                )
            )

        self._session.add_all(outbox_rows)
        log.info("Rating notifications queued", cycle_id=cycle, notifications=len(outbox_rows))
        return len(outbox_rows)

    async def pending_outbox(self, limit: int = 100) -> list[tuple[NotificationOutbox, PushSubscription]]:
        now = utcnow()
        rows = await self._session.execute(
            select(NotificationOutbox, PushSubscription)
            .join(PushSubscription, NotificationOutbox.subscription_id == PushSubscription.id)
            .where(
                NotificationOutbox.status == "pending",
                PushSubscription.enabled.is_(True),
                or_(NotificationOutbox.next_attempt_at.is_(None), NotificationOutbox.next_attempt_at <= now),
            )
            .order_by(NotificationOutbox.created_at)
            .limit(limit)
        )
        return list(rows.all())

    async def mark_sent(self, item: NotificationOutbox) -> None:
        item.status = "sent"
        item.updated_at = utcnow()

    async def mark_retry(self, item: NotificationOutbox, error: str, next_attempt_at) -> None:
        item.attempts += 1
        item.last_error = error[:500]
        item.next_attempt_at = next_attempt_at
        item.updated_at = utcnow()

    async def mark_failed(self, item: NotificationOutbox, error: str) -> None:
        item.status = "failed"
        item.attempts += 1
        item.last_error = error[:500]
        item.updated_at = utcnow()

    async def disable_broken_subscription(self, subscription: PushSubscription) -> None:
        subscription.enabled = False
        subscription.failure_count += 1
        subscription.updated_at = utcnow()

    async def commit(self) -> None:
        await self._session.commit()

    async def _active_zachs(self, zach_numbers: list[str] | None) -> list[str]:
        filters = [PushSubscription.enabled.is_(True)]
        if zach_numbers is not None:
            filters.append(PushSubscription.zach_number.in_(zach_numbers))
        rows = await self._session.execute(select(distinct(PushSubscription.zach_number)).where(and_(*filters)))
        return [str(row[0]) for row in rows.all()]

    async def _state_map(self, zach_numbers: list[str]) -> dict[tuple[str, str, str], str]:
        rows = (
            await self._session.execute(select(RatingWatchState).where(RatingWatchState.zach_number.in_(zach_numbers)))
        ).scalars()
        return {(row.zach_number, row.ved_type, row.subject_name): row.last_value for row in rows}

    async def _seed_watch_state(self, zach_number: str) -> None:
        rows = (
            await self._session.execute(select(RatingRecord).where(RatingRecord.zach_number == zach_number))
        ).scalars()
        now = utcnow()
        state_rows = [
            {
                "zach_number": row.zach_number,
                "ved_type": row.ved_type,
                "subject_name": row.subject_name,
                "last_value": value,
                "updated_at": now,
            }
            for row in rows
            if (value := normalize_rating_value(row.final_rating)) is not None
        ]
        if state_rows:
            await self._session.execute(insert(RatingWatchState).prefix_with("OR IGNORE"), state_rows)


def _payload(zach_number: str, changes: list[dict]) -> dict:
    first = changes[0]
    title = "Выставлен новый рейтинг"
    if len(changes) == 1:
        old_value = first["old_value"]
        value_text = f"{old_value} → {first['new_value']}" if old_value is not None else str(first["new_value"])
        body = f"{first['subject_name']}: {value_text}"
    else:
        body = f"Обновлены дисциплины: {len(changes)}"

    return {
        "title": title,
        "body": body,
        "tag": f"rating-update-{zach_number}",
        "url": "/",
        "zach_number": zach_number,
        "changes": changes,
    }


def get_notification_repository(session: AsyncSession = Depends(get_session)) -> NotificationRepository:
    return NotificationRepository(session)
