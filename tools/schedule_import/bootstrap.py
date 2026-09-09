"""Перенос готового расписания из образа в постоянную БД перед запуском API."""

import os
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from app.entities.schemas.schedule import ScheduleModel

SEED_PATH = Path("/opt/vsuet/schedule.sqlite3")


def install_schedule(seed: Path, target: Path) -> int:
    """Заменить только расписание; вернуть число групп (0, если оно не изменилось).

    Проверяем источник до открытия целевой БД. BEGIN IMMEDIATE защищает
    сравнение и замену от другого писателя. Резервная копия читает прежнее
    зафиксированное состояние через отдельное соединение.
    """
    seed, target = seed.resolve(), target.resolve()
    if seed == target:
        raise ValueError("Источник расписания совпадает с рабочей БД")
    with closing(sqlite3.connect(f"{seed.as_uri()}?mode=ro", uri=True)) as source:
        if source.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Нарушена целостность БД расписания в образе")
        rows = source.execute("SELECT group_name, schedule FROM group_schedule ORDER BY group_name").fetchall()
    if not rows:
        raise ValueError("БД расписания в образе пуста")
    if len({name for name, _ in rows}) != len(rows):
        raise ValueError("В БД расписания повторяются группы")
    for name, raw in rows:
        if not name.strip():
            raise ValueError("Пустое название группы")
        ScheduleModel.model_validate_json(raw)

    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    with closing(sqlite3.connect(target, timeout=60)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        has_schedule = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='group_schedule'").fetchone()
        if (
            has_schedule
            and db.execute("SELECT group_name, schedule FROM group_schedule ORDER BY group_name").fetchall() == rows
        ):
            print(f"Schedule unchanged: {len(rows)} groups", flush=True)
            return 0

        if existed:
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            backup = target.parent / "backups" / f"{target.name}.before-schedule-{stamp}.bak"
            backup.parent.mkdir(parents=True, exist_ok=True)
            with (
                closing(sqlite3.connect(f"{target.as_uri()}?mode=ro", uri=True)) as current,
                closing(sqlite3.connect(backup)) as copy,
            ):
                current.backup(copy)
                if copy.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ValueError("Не удалось проверить резервную копию БД")
            print(f"Database backup: {backup}", flush=True)

        db.execute("CREATE TABLE IF NOT EXISTS group_schedule (group_name TEXT PRIMARY KEY, schedule TEXT NOT NULL)")
        db.execute("DELETE FROM group_schedule")
        db.executemany("INSERT INTO group_schedule (group_name, schedule) VALUES (?, ?)", rows)
    print(f"Schedule installed: {len(rows)} groups into {target}", flush=True)
    return len(rows)


def main() -> None:
    from app.config import settings

    if len(sys.argv) < 2:
        raise SystemExit("Не задана команда запуска приложения")
    install_schedule(SEED_PATH, settings.db.path)
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
