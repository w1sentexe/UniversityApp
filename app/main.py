import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
from app.logging_config import get_logger, print_banner, setup_logging
from app.repository.notification_repository import NotificationRepository
from app.repository.rating_repository import RatingRepository
from app.repository.snapshot_meta_repository import SnapshotMetaRepository
from app.repository.snapshot_repository import SnapshotRepository
from app.routers import notifications_router, rating_router, schedule_router, students_router
from app.services.notification_service import NotificationService
from app.services.parser_service import ParserService
from app.services.parsing_pipeline import ParsingPipeline, PipelineError
from app.sqlite_conn import dispose_engine, init_models, session_scope
from app.time_utils import APP_TIMEZONE, local_now

print_banner()
setup_logging()
log = get_logger(__name__)

# Небольшая задержка первого («немедленного») цикла: даём uvicorn договорить свой
# стартовый баннер ("Uvicorn running on ...") до старта тяжёлого цикла — иначе job
# на том же event loop влезает в хвост стартовых логов.
_FIRST_RUN_DELAY_S = 3

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
        # Отдельная сессия для короткой записи снапшота и очереди уведомлений.
        # Сбор данных с сайта проходит до начала транзакции записи.
        async with session_scope() as session:
            snapshot = SnapshotRepository(session)
            reader = RatingRepository(session)
            notifications = NotificationRepository(session)
            metadata = SnapshotMetaRepository(session)
            try:
                async with ParserService() as parser:
                    report = await ParsingPipeline(parser, snapshot, reader, notifications, metadata).run()
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Application start up", year=settings.parsing.year, semester=settings.parsing.semester)
    log.info("Swagger UI documentation is available at: http://localhost:8000/docs")

    # Движок и недостающие таблицы. На существующей базе ничего не пересоздаётся.
    await init_models()

    # Сервисы больше не живут в app.state: их собирает цепочка зависимостей
    # сессия → репозиторий → сервис на каждый запрос (см. app/sqlite_conn.py).
    async with session_scope() as session:
        counts = await RatingRepository(session).counts()
    log.info("Snapshot on start", **counts)

    # Первый запуск парсинга всегда сразу после старта: даже существующий снапшот
    # нужно обновить после деплоя/рестарта, а затем продолжать по интервалу.
    first_run_delay = timedelta(seconds=_FIRST_RUN_DELAY_S)
    first_run = local_now() + first_run_delay
    log.info(
        "Parsing cycle will run shortly after startup",
        delay_s=_FIRST_RUN_DELAY_S,
        interval_min=settings.scheduler.interval_minutes,
        first_run_at=first_run.strftime("%Y-%m-%d %H:%M:%S"),
    )

    scheduler = AsyncIOScheduler(timezone=APP_TIMEZONE)
    scheduler.add_job(
        run_parsing_cycle,
        trigger="interval",
        minutes=settings.scheduler.interval_minutes,
        id="parsing_cycle",
        max_instances=1,
        coalesce=True,
        next_run_time=first_run,
    )
    scheduler.add_job(
        dispatch_pending_notifications,
        trigger="interval",
        seconds=settings.notifications.dispatch_interval_seconds,
        id="push_dispatch",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    app.state.scheduler = scheduler
    log.info("Scheduler started", interval_min=settings.scheduler.interval_minutes)

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await dispose_engine()
        log.info("Application stopped")


app = FastAPI(title="VSUET Rating", lifespan=lifespan)
# CORS для локального фронтенда (Vite/CRA/иные dev-серверы на localhost).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(students_router.router)
app.include_router(rating_router.router)
app.include_router(notifications_router.router)

app.include_router(schedule_router.router)
Instrumentator(
    should_group_status_codes=False,
).instrument(app).expose(app)
