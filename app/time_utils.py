from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import settings


def _load_app_timezone():
    try:
        return ZoneInfo(settings.logging.timezone)
    except ZoneInfoNotFoundError:
        if settings.logging.timezone == "Europe/Moscow":
            return timezone(timedelta(hours=3), "MSK")
        return UTC


APP_TIMEZONE = _load_app_timezone()


def local_now() -> datetime:
    return datetime.now(tz=APP_TIMEZONE)
