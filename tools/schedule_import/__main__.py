"""Загрузка расписания из выгрузок Excel в БД.

    python -m tools.schedule_import              # вся папка files/
    python -m tools.schedule_import --dry-run    # разобрать и показать отчёт
    python -m tools.schedule_import путь.xlsx    # один файл или своя папка

Инструмент запускается руками раз в семестр, поэтому и живёт вне app: бэкенд о
нём ничего не знает и работает без него. Обратная зависимость есть — писать в
таблицу через тот же репозиторий, что и читает API, надёжнее, чем повторять
здесь SQL.

Таблица расписания заменяется целиком: выгрузки — единственный источник правды.
Данных рейтинга инструмент не касается.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from app.logging_config import get_logger, setup_logging
from app.repository.schedule_repository import ScheduleRepository
from app.sqlite_conn import dispose_engine, init_models, session_scope
from tools.schedule_import.parser import FileReport, ScheduleParseError, parse_schedule

log = get_logger(__name__)

# Выгрузки лежат рядом с инструментом: без них расписание невоспроизводимо,
# а получить файлы заново можно только в деканатах.
DEFAULT_SOURCE = Path(__file__).resolve().parent / "files"


def _print_report(reports: list[FileReport], groups: int) -> None:
    """Табличка по файлам: что разобрано, что пропущено и почему."""
    width = max(len(r.path.name) for r in reports)
    for report in reports:
        if report.ok:
            counts = f"листов {report.sheets:>2}  групп {report.groups:>3}  занятий {report.lessons:>5}"
            print(f"  {report.path.name:<{width}}  {counts}")
        else:
            print(f"  {report.path.name:<{width}}  — пропущен: {report.skipped}")
    print(f"\n  итого групп: {groups}")


async def _write(schedules: dict) -> int:
    await init_models()
    try:
        async with session_scope() as session:
            count = await ScheduleRepository(session).replace_all(schedules)
            await session.commit()
        return count
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="Загрузить расписание групп из выгрузок Excel")
    parser.add_argument(
        "source",
        type=Path,
        nargs="?",
        default=DEFAULT_SOURCE,
        help=f"файл или папка с выгрузками; по умолчанию {DEFAULT_SOURCE.name}/ рядом с инструментом",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="только разобрать и показать отчёт, в БД ничего не писать",
    )
    args = parser.parse_args()

    if not args.source.exists():
        print(f"Не найдено: {args.source}", file=sys.stderr)
        raise SystemExit(1)

    setup_logging()
    try:
        schedules, reports = parse_schedule(args.source)
    except ScheduleParseError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    _print_report(reports, len(schedules))

    if args.dry_run:
        print("\n  --dry-run: в БД ничего не записано")
        return

    if not schedules:
        # Пустая запись стёрла бы всё расписание разом — при неопознанном
        # формате это худший исход, чем ничего не делать.
        print("\n  Ни одной группы не разобрано, запись отменена", file=sys.stderr)
        raise SystemExit(1)

    count = asyncio.run(_write(schedules))
    log.info("Done", groups=count)


if __name__ == "__main__":
    main()
