"""Разбор расписания занятий из выгрузок Excel в структуру по группам.

Выгрузки приходят из деканатов, и единого формата у них нет. Разбирается один —
недельное расписание очного отделения (файлы факультетов): именно он ложится на
ScheduleModel с числителем и знаменателем. Файлы других разметок не разбираются,
а попадают в отчёт с причиной — молча возвращать по ним ноль занятий нельзя,
иначе пропажа целого факультета выглядела бы как «в файле пусто».

Формат разбираемой выгрузки (проверен на шести файлах факультетов):

* лист = курс, шапка с названиями групп — строка со словом «Дни» в столбце A;
* столбец A — день недели, объединён на весь свой блок строк;
* столбец B — пара вида «08.00-09.35», объединена ровно на ДВЕ строки:
  верхняя — числитель, нижняя — знаменатель;
* столбцы с третьего — группы. Группа занимает одну колонку (не делится) либо
  две объединённые (левая — первая подгруппа, правая — вторая);
* лекция на поток — одна ячейка, объединённая по колонкам нескольких групп;
  её значение лежит в левой верхней ячейке, остальные читаются как None,
  поэтому объединения приходится разворачивать вручную.

Ячейка занятия выглядит так:

    пр.Иностранный язык
    Мирошниченко Е.Н.   21           Павлова С.В.   11и

Первая строка — тип и название, вторая — преподаватель и аудитория. Если во
второй строке две пары «преподаватель + аудитория», значит занятие всё же
разведено по подгруппам внутри одной объединённой ячейки.

Модуль ничего не знает ни про БД, ни про сеть: на вход путь к файлу или папке,
на выход словарь {группа: ScheduleModel} и отчёт по каждому файлу.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Any

from openpyxl.worksheet.worksheet import Worksheet

from app.entities.schemas.schedule import LessonModel, LessonType, ScheduleModel, WeeklyScheduleModel
from app.logging_config import get_logger

log = get_logger(__name__)

# Старый бинарный формат Excel: openpyxl его не открывает в принципе, поэтому
# такие файлы отсеиваются с внятной причиной, а не с ошибкой ZIP-архива.
_LEGACY_SUFFIX = ".xls"
_SUFFIXES = (".xlsx", ".xlsm", _LEGACY_SUFFIX)

# Столбец A шапки; по нему находим строку с названиями групп.
_HEADER_MARKER = "Дни"
# Данные начинаются с третьей колонки: первые две заняты днём и временем.
_FIRST_GROUP_COL = 3

# Префикс в начале ячейки → тип занятия.
_LESSON_TYPES = {
    "л": LessonType.lecture,
    "пр": LessonType.practice,
    "лаб": LessonType.lab,
    "сем": LessonType.seminar,
}

# Ключи — как в шапке файла, значения — поля WeeklyScheduleModel.
_DAY_KEYS = {
    "ПОНЕДЕЛЬНИК": "monday",
    "ВТОРНИК": "tuesday",
    "СРЕДА": "wednesday",
    "ЧЕТВЕРГ": "thursday",
    "ПЯТНИЦА": "friday",
    "СУББОТА": "saturday",
}

# Поля ScheduleModel в том порядке, в каком недели лежат в файле:
# первая строка пары — числитель, вторая — знаменатель.
_WEEKS = ("numerator", "denominator")

# «08.00-09.35»; разделитель часов и минут в выгрузке точка, но точку с
# двоеточием не различаем — от источника к источнику написание плавает.
_SLOT_TIME = re.compile(r"(\d{1,2})[.:](\d{2})\s*-\s*(\d{1,2})[.:](\d{2})")
# «Мирошниченко Е.Н.   21» — фамилия с инициалами, затем аудитория.
# У второго преподавателя в ячейке тот же шаблон, поэтому ищем именно полные
# пары, а не режем строку по длинному отступу: в выгрузках встречается
# «Козыренко Е.В,    11и» и служебная метка «Z» после аудитории.
_TEACHER_ROOM = re.compile(r"(?P<teacher>[А-ЯЁA-Z][А-Яа-яЁёA-Za-z-]*(?:\s+[А-ЯЁA-Z]\.){1,2})[,.]?\s+(?P<room>\S+)")

# Расписание группы, пока оно собирается: недели → дни → занятия. В
# ScheduleModel накопитель превращается на выходе, когда все листы прочитаны.
_Draft = dict[str, dict[str, list[LessonModel]]]


class ScheduleParseError(RuntimeError):
    """Файл не удалось разобрать: разметка не совпала с ожидаемой."""


@dataclass(frozen=True)
class FileReport:
    """Итог по одному файлу выгрузки.

    skipped заполнен, если разметка не опознана: пустой результат сам по себе
    ничего не объясняет, а причина нужна — файлы обновляются в деканатах, и
    смена формата должна быть видна сразу, а не через пропавшие группы.
    """

    path: Path
    sheets: int = 0
    groups: int = 0
    lessons: int = 0
    skipped: str | None = None

    @property
    def ok(self) -> bool:
        return self.skipped is None


def _merged_lookup(sheet: Worksheet) -> dict[tuple[int, int], tuple[int, int, int]]:
    """Карта «ячейка → (строка якоря, колонка якоря, ширина объединения)».

    Нужна, чтобы развернуть объединения: значение лежит только в левой верхней
    ячейке, а занятие относится ко всем накрытым колонкам.
    """
    lookup: dict[tuple[int, int], tuple[int, int, int]] = {}
    for rng in sheet.merged_cells.ranges:
        width = rng.max_col - rng.min_col + 1
        for row in range(rng.min_row, rng.max_row + 1):
            for col in range(rng.min_col, rng.max_col + 1):
                lookup[(row, col)] = (rng.min_row, rng.min_col, width)
    return lookup


def _cell_value(sheet: Worksheet, merged: dict, row: int, col: int) -> tuple[Any, int]:
    """Значение ячейки с учётом объединений и ширина накрывающего блока."""
    anchor = merged.get((row, col))
    if anchor is None:
        return sheet.cell(row, col).value, 1
    anchor_row, anchor_col, width = anchor
    return sheet.cell(anchor_row, anchor_col).value, width


def _find_header_row(sheet: Worksheet) -> int | None:
    """Строка шапки с названиями групп либо None, если разметка не та."""
    for row in range(1, 20):
        if str(sheet.cell(row, 1).value or "").strip() == _HEADER_MARKER:
            return row
    return None


def _read_groups(sheet: Worksheet, header_row: int, merged: dict) -> list[tuple[str, int, int]]:
    """Список (название группы, первая колонка, число колонок).

    Две колонки означают деление на подгруппы.
    """
    groups: list[tuple[str, int, int]] = []
    col = _FIRST_GROUP_COL
    while col <= sheet.max_column:
        value, width = _cell_value(sheet, merged, header_row, col)
        name = str(value).strip() if value is not None else ""
        if name:
            groups.append((name, col, width))
        col += width
    return groups


def _read_day_blocks(sheet: Worksheet) -> list[tuple[str, int, int]]:
    """Дни недели: (поле WeeklyScheduleModel, первая строка блока, последняя)."""
    blocks: list[tuple[str, int, int]] = []
    for rng in sorted(sheet.merged_cells.ranges, key=lambda r: r.min_row):
        if rng.min_col != 1 or rng.max_row == rng.min_row:
            continue
        title = str(sheet.cell(rng.min_row, 1).value or "").strip().upper()
        key = _DAY_KEYS.get(title)
        if key:
            blocks.append((key, rng.min_row, rng.max_row))
    return blocks


def _read_slots(sheet: Worksheet, first_row: int, last_row: int) -> Iterator[tuple[time, time, int]]:
    """Пары внутри дня: (начало, конец, строка числителя).

    Строка знаменателя — следующая за ней: пара всегда занимает две строки.
    """
    for row in range(first_row, last_row + 1):
        raw = sheet.cell(row, 2).value
        if raw is None or not str(raw).strip():
            continue
        match = _SLOT_TIME.search(str(raw))
        if match is None:
            log.warning("Slot time skipped", sheet=sheet.title, row=row, value=str(raw).strip())
            continue
        start_h, start_m, end_h, end_m = (int(g) for g in match.groups())
        yield time(start_h, start_m), time(end_h, end_m), row


def _split_teacher_room(text: str) -> list[tuple[str | None, str | None]]:
    """Разбирает строку с преподавателями и аудиториями.

    Возвращает список пар: одна — занятие общее, две — разведено по подгруппам
    прямо внутри объединённой ячейки. Аудитории в источнике бывает не указано,
    поэтому вторая половина пары необязательна.
    """
    pairs = [(match["teacher"].strip(), match["room"].strip()) for match in _TEACHER_ROOM.finditer(text)]
    return pairs or [(text.strip(), None)]


def _parse_cell(raw: str) -> tuple[LessonType, str, list[tuple[str | None, str | None]]] | None:
    """Ячейка → (тип, название, список пар «преподаватель + аудитория»).

    Пар две, когда подгруппы разведены внутри одной ячейки; иначе одна.
    """
    lines = [line.strip() for line in str(raw).split("\n") if line.strip()]
    if not lines:
        return None

    head = lines[0]
    match = re.match(r"([А-Яа-яA-Za-z]+)\.(.+)", head)
    if match and match.group(1).lower() in _LESSON_TYPES:
        lesson_type = _LESSON_TYPES[match.group(1).lower()]
        name = match.group(2).strip()
    else:
        # Без префикса приходит, например, «Общая физическая подготовка».
        lesson_type = LessonType.other
        name = head

    if len(lines) < 2:
        return lesson_type, name, [(None, None)]
    return lesson_type, name, _split_teacher_room(lines[1])


def _new_draft() -> _Draft:
    return {week: {day: [] for day in _DAY_KEYS.values()} for week in _WEEKS}


def _to_model(draft: _Draft) -> ScheduleModel:
    """Накопитель → ScheduleModel; занятия дня выстраиваются по времени начала.

    Сортировка нужна не для порядка чтения файла (он и так по возрастанию), а
    чтобы клиент мог полагаться на порядок списка, не сортируя сам.
    """
    weeks = {
        week: WeeklyScheduleModel(
            **{day: sorted(lessons, key=lambda lesson: lesson.start_time) for day, lessons in days.items()}
        )
        for week, days in draft.items()
    }
    return ScheduleModel(**weeks)


def parse_file(path: str | Path) -> tuple[dict[str, ScheduleModel], FileReport]:
    """Разбирает одну выгрузку: {группа: расписание} и отчёт по файлу."""
    import openpyxl  # локальный импорт: нужен только этому инструменту, не бэкенду

    path = Path(path)
    if path.suffix.lower() == _LEGACY_SUFFIX:
        return {}, FileReport(path, skipped="старый формат .xls, openpyxl его не открывает")

    try:
        workbook = openpyxl.load_workbook(path, data_only=True, read_only=False)
    except Exception as exc:  # причину показываем в отчёте, файл пропускаем
        return {}, FileReport(path, skipped=f"файл не открылся: {exc}")

    drafts: dict[str, _Draft] = {}
    lessons_total = 0
    weekly_sheets = 0

    for sheet in workbook.worksheets:
        header_row = _find_header_row(sheet)
        days = _read_day_blocks(sheet) if header_row is not None else []
        # Шапки мало: слово «Дни» стоит и в сессионной выгрузке заочников, где
        # вместо дней недели даты («ПНД 15/06»). Лист считаем своим, только если
        # хотя бы один день опознан — иначе разберём чужую разметку в пустоту.
        if header_row is None or not days:
            log.debug("Sheet skipped", file=path.name, sheet=sheet.title)
            continue

        weekly_sheets += 1
        merged = _merged_lookup(sheet)
        groups = _read_groups(sheet, header_row, merged)
        log.debug("Sheet layout", file=path.name, sheet=sheet.title, groups=len(groups), days=len(days))

        for name, first_col, width in groups:
            draft = drafts.setdefault(name, _new_draft())

            for day_key, day_first, day_last in days:
                for start, end, slot_row in _read_slots(sheet, day_first, day_last):
                    for offset, week in enumerate(_WEEKS):
                        row = slot_row + offset
                        if row > day_last:
                            continue
                        lessons = _lessons_at(sheet, merged, row, first_col, width, start, end)
                        draft[week][day_key].extend(lessons)
                        lessons_total += len(lessons)

    if not weekly_sheets:
        return {}, FileReport(path, skipped="разметка не опознана: ни одного листа с днями недели")

    result = {name: _to_model(draft) for name, draft in drafts.items()}
    return result, FileReport(path, sheets=weekly_sheets, groups=len(result), lessons=lessons_total)


def parse_schedule(source: str | Path) -> tuple[dict[str, ScheduleModel], list[FileReport]]:
    """Разбирает файл или всю папку выгрузок.

    Группы из разных файлов сливаются в один словарь: один файл — один
    факультет, и пересечений между ними нет. Если они всё же появятся, повтор
    попадёт в лог: молча затирать чужое расписание нельзя.
    """
    source = Path(source)
    paths = (
        sorted(p for p in source.iterdir() if p.suffix.lower() in _SUFFIXES and not p.name.startswith("~$"))
        if source.is_dir()
        else [source]
    )
    if not paths:
        raise ScheduleParseError(f"В {source} нет файлов выгрузки")

    merged: dict[str, ScheduleModel] = {}
    reports: list[FileReport] = []

    for path in paths:
        schedules, report = parse_file(path)
        reports.append(report)
        if report.skipped:
            log.warning("File skipped", file=path.name, reason=report.skipped)
            continue
        for name, schedule in schedules.items():
            if name in merged:
                log.warning("Group already parsed from another file, keeping the first", group=name, file=path.name)
                continue
            merged[name] = schedule
        log.info("File parsed", file=path.name, groups=report.groups, lessons=report.lessons)

    log.info(
        "Schedule parsed",
        files=len(reports),
        parsed=sum(1 for r in reports if r.ok),
        skipped=sum(1 for r in reports if not r.ok),
        groups=len(merged),
        lessons=sum(r.lessons for r in reports),
    )
    return merged, reports


def _lessons_at(
    sheet: Worksheet,
    merged: dict,
    row: int,
    first_col: int,
    width: int,
    start_time: time,
    end_time: time,
) -> list[LessonModel]:
    """Занятия одной группы в конкретной строке (числитель или знаменатель)."""
    # Собираем именно ячейки, а не только их текст: две одинаково заполненные
    # соседние ячейки всё равно могут относиться к разным подгруппам. У
    # объединённой ячейки значение лежит в якоре, поэтому она попадёт сюда раз.
    seen: list[tuple[Any, int, int]] = []
    seen_anchors: set[tuple[int, int]] = set()
    for col in range(first_col, first_col + width):
        value, merge_width = _cell_value(sheet, merged, row, col)
        if value is None or not str(value).strip():
            continue
        anchor_row, anchor_col, _ = merged.get((row, col), (row, col, 1))
        if (anchor_row, anchor_col) in seen_anchors:
            continue
        seen_anchors.add((anchor_row, anchor_col))
        seen.append((value, anchor_col, merge_width))

    lessons: list[LessonModel] = []
    for value, cell_col, cell_width in seen:
        parsed = _parse_cell(value)
        if parsed is None:
            continue
        lesson_type, name, occupants = parsed

        # Группа в шапке занимает две колонки. Объединение на обе означает
        # общее занятие, а одиночная ячейка — занятие только своей подгруппы.
        # У одноколоночной группы разделение может быть записано двумя
        # преподавателями внутри одной ячейки, поэтому базово она общая.
        if width == 1:
            cell_subgroups = [1, 2]
        else:
            covered_first = max(first_col, cell_col)
            covered_last = min(first_col + width - 1, cell_col + cell_width - 1)
            cell_subgroups = list(range(covered_first - first_col + 1, covered_last - first_col + 2))

        for index, (teacher, room) in enumerate(occupants):
            # Две валидные пары в общей ячейке идут в порядке подгрупп. Если
            # ячейка уже ограничена одной колонкой, она относится к этой
            # подгруппе независимо от количества текстовых фрагментов.
            if len(occupants) == len(cell_subgroups) and len(cell_subgroups) > 1:
                subgroups = [index + 1]
            else:
                subgroups = cell_subgroups
            lessons.append(
                LessonModel(
                    start_time=start_time,
                    end_time=end_time,
                    name=name,
                    lesson_type=lesson_type,
                    teacher_name=teacher,
                    classroom=room,
                    subgroups=subgroups,
                )
            )
    return lessons
