import asyncio
from datetime import timedelta

from app.config import settings
from app.db.session import session_scope
from app.logging_config import get_logger
from app.repository.notification_repository import NotificationRepository
from app.repository.rating_repository import RatingRepository
from app.repository.snapshot_repository import SnapshotRepository
from app.services.notification_service import NotificationService
from app.services.parser_service import ParserService
from app.services.parsing_pipeline import ParsingPipeline, PipelineError
from app.time_utils import local_now

log = get_logger(__name__)

# Гарантирует, что в один момент времени выполняется ровно один цикл парсинга
# (подстраховка к max_instances=1 планировщика на случай ручного запуска).
_running = asyncio.Lock()


async def run_parsing_cycle() -> None:
    """Полный цикл парсинга."""

    if _running.locked():
        log.info("Parsing cycle is already running, skipping")
        return

    async with _running:
        log.info("Start parsing cycle")
        # Отдельная сессия на весь цикл: её транзакция держит новый снапшот до
        # коммита, а запросы обслуживаются своими сессиями и видят прежний.
        async with session_scope() as session:
            snapshot = SnapshotRepository(session)
            reader = RatingRepository(session)
            notifications = NotificationRepository(session)
            try:
                async with ParserService() as parser:
                    report = await ParsingPipeline(parser, snapshot, reader, notifications).run()
            except PipelineError as exc:
                # Пайплайн уже откатил транзакцию — в БД остался прежний снапшот.
                log.exception("Parsing cycle failed, snapshot not committed", stage=exc.stage)
                return

        if not report.site_available:
            next_run = (local_now() + timedelta(minutes=settings.scheduler.interval_minutes)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            log.warning("Parsing cycle postponed", url=settings.site.base_url, next_run=next_run)
            return

        log.info("Parsing cycle completed", **report.summary())
        await dispatch_pending_notifications()


async def dispatch_pending_notifications() -> None:
    """Отправляет накопленные Web Push уведомления."""
    async with session_scope() as session:
        await NotificationService(NotificationRepository(session)).dispatch_pending()
