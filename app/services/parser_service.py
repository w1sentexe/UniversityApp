"""ParserService — взаимодействие с rating.vsuet.ru.

Каркас обхода ASP.NET WebForms: скрытые поля (__VIEWSTATE и пр.), POST через
__EVENTTARGET, конкурентный обход факультетов → групп → ведомостей под общим
семафором, ретраи при сетевых ошибках и 429. Весь тюнинг (конкурентность,
таймауты, ретраи) и разметка сайта — в config: ScraperSettings, HtmlFormSettings,
RatingSiteSettings; здесь только логика обхода.

Здесь же разбор скачанного HTML в доменные модели: и служебный (viewstate,
селекты, ссылки на ведомости), и разбор самой ведомости — источник у них один,
поэтому и разметка его страниц описана в одном месте.
"""

import asyncio
import random
import re

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.entities.schemas.rating import RATING_VED_TYPES, ControlPoint, NotRatingVedModel, RatingVedModel, SubjectScore
from app.logging_config import get_logger

log = get_logger(__name__)

_PCT_RE = re.compile(r"^\d+%$")
_INT_RE = re.compile(r"^-?\d+$")

# Разметка ведомости (индексы колонок, id-маркеры) — config.HtmlVedSettings.
_VED = settings.html_ved


def _backoff_delay(attempt: int) -> float:
    """Экспоненциальный бэкофф с полным джиттером.

    Запросы, упавшие по таймауту одной волной (слабый сервер отдаёт их пачкой),
    без джиттера ретраятся синхронно и снова перегружают сервер. Случайная
    задержка из [0, base] размазывает повторы во времени.
    """
    cfg = settings.scraper
    base = min(cfg.retry_backoff_s * (2 ** (attempt - 1)), cfg.retry_max_delay_s)
    return random.uniform(0, base)


def _parse_viewstate(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    fields = {}
    for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        tag = soup.find("input", {"name": name})
        if tag:
            fields[name] = tag.get("value", "")
    return fields


def _parse_select(html: str, name: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    select = soup.find("select", {"name": name})
    if not select:
        return []
    return [{"id": o["value"], "name": o.text.strip()} for o in select.find_all("option") if o.get("value")]


def _parse_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", {"id": re.compile(settings.html_form.grid_id_pattern)})
    if not table:
        return []
    urls = []
    for a in table.find_all("a", href=True):
        m = re.search(r"id=(\d+)", a["href"])
        if m:
            urls.append(f"{settings.site.ved_url}?id={m.group(1)}")
    return urls


def _form_data(event_target: str, viewstate: dict, fac_id: str, group_id: str) -> dict:
    """POST-форма Default.aspx: событие + viewstate + текущие значения селектов."""
    form = settings.html_form
    return {
        "__EVENTTARGET": event_target,
        "__EVENTARGUMENT": "",
        **viewstate,
        form.faculty_select: fac_id,
        form.group_select: group_id,
        form.years_select: settings.parsing.year,
        form.semester_select: settings.parsing.semester,
    }


# --- разбор ведомости ---


def _cell(tds: list, idx: int) -> str:
    """Текст ячейки по индексу либо "-", если ячейки нет или она пуста."""
    if idx < len(tds):
        text = tds[idx].get_text(strip=True)
        if text:
            return text
    return "-"


def _score(tds: list, idx: int) -> str | int:
    """Балл из ячейки: int, если число, иначе исходный текст либо "-"."""
    text = _cell(tds, idx)
    if text == "-":
        return "-"
    if _INT_RE.match(text):
        return int(text)
    return text


def _is_ved_row(row) -> bool:
    """Возвращает True, если строка таблицы является строкой с оценками студентов."""
    classes = row.get("class") or []
    return any(cls in classes for cls in _VED.row_classes)


def _pct_cells(row) -> list[int]:
    """Значения процентов из строки шапки в порядке следования."""
    out = []
    for td in row.find_all("td"):
        text = td.get_text(strip=True)
        if _PCT_RE.match(text):
            out.append(int(text[:-1]))
    return out


def _at(values: list[int], idx: int):
    """Безопасное извлечение значения из списка по индексу. Если индекс выходит за пределы, возвращает заглушку '-'."""
    return values[idx] if idx < len(values) else "-"


def _parse_header_weights(table) -> tuple[int, list[int], list[int]]:
    """Извлекает количество контрольных точек (КТ) и их веса из шапки таблицы ведомости.

    Возвращает кортеж из трех элементов:
      - количество контрольных точек (КТ) на основе столбцов «Итог по КТ»;
      - список весов каждой контрольной точки (КТ);
      - плоский список весов для каждого вида учебной работы (по 4 на каждую КТ: Лек., Пр., Лаб., Др.).
    """
    header_rows = [r for r in table.find_all("tr") if not _is_ved_row(r)]
    if not header_rows:
        return 0, [], []

    num_kt = sum(1 for td in header_rows[0].find_all("td") if _VED.kt_total_marker in td.get_text())

    kt_weights: list[int] = []
    work_weights: list[int] = []
    for row in header_rows[1:]:
        texts = [td.get_text(strip=True) for td in row.find_all("td")]
        if not any(t for t in texts):
            continue
        # Строка весов КТ: содержит метку «Вес Точки,%».
        if any(_VED.kt_weight_marker in t for t in texts):
            kt_weights = _pct_cells(row)
        # Строка весов видов работ: только проценты (и пустые ячейки).
        elif all((not t) or _PCT_RE.match(t) for t in texts):
            work_weights = _pct_cells(row)

    return num_kt, kt_weights, work_weights


def _parse_rating(table, rows: list, ved_type: str, subject_name: str) -> list[RatingVedModel]:
    """Разбирает строки студентов рейтингового формата (с разбивкой по КТ и видам работ) в записи."""
    num_kt, _, work_weights = _parse_header_weights(table)

    records: list[RatingVedModel] = []
    for row in rows:
        tds = row.find_all("td")
        if not tds:
            continue

        control_points: list[ControlPoint] = []
        for i in range(num_kt):
            base = _VED.kt_first_col + i * _VED.kt_block_cells
            w = i * _VED.kt_works
            control_points.append(
                ControlPoint(
                    kt_num=i + 1,
                    lecture=SubjectScore(score=_score(tds, base), weight=_at(work_weights, w)),
                    practice=SubjectScore(score=_score(tds, base + 1), weight=_at(work_weights, w + 1)),
                    lab=SubjectScore(score=_score(tds, base + 2), weight=_at(work_weights, w + 2)),
                    other=SubjectScore(score=_score(tds, base + 3), weight=_at(work_weights, w + 3)),
                    total=_score(tds, base + 4),
                )
            )

        final_idx = _VED.kt_first_col + num_kt * _VED.kt_block_cells + _VED.final_rating_offset
        records.append(
            RatingVedModel(
                zach_number=_cell(tds, _VED.zach_col),
                subject_name=subject_name,
                ved_type=ved_type,
                control_points=control_points,
                final_rating=_score(tds, final_idx),
            )
        )
    return records


def _extract_grade(tds: list) -> str:
    """Оценка студента: приоритет — поздняя пересдача, затем основная оценка."""
    for idx in _VED.retake_cols:
        value = _cell(tds, idx)
        if value != "-":
            return value
    return _cell(tds, _VED.grade_col)


def _parse_grade(rows: list, ved_type: str, subject_name: str) -> list[NotRatingVedModel]:
    """Разбирает строки студентов оценочного формата (одна финальная оценка на запись)."""
    records: list[NotRatingVedModel] = []
    for row in rows:
        tds = row.find_all("td")
        if not tds:
            continue
        records.append(
            NotRatingVedModel(
                zach_number=_cell(tds, _VED.zach_col),
                subject_name=subject_name,
                ved_type=ved_type,
                grade=_extract_grade(tds),
            )
        )
    return records


def _parse_ved_html(html: str) -> list[RatingVedModel] | list[NotRatingVedModel]:
    """Разбирает HTML ведомости в список записей целевого формата.

    Возвращает пустой список для нерабочей ведомости (нет/пустой
    ucVedBox_lblTypeVed) — это штатная ситуация, не ошибка.
    """
    soup = BeautifulSoup(html, "lxml")

    type_tag = soup.find("span", id=_VED.type_span_id)
    if not type_tag or not type_tag.get_text(strip=True):
        log.debug("Skip: no ucVedBox_lblTypeVed (non-functional vedomost)")
        return []

    ved_type = type_tag.get_text(strip=True)
    dis_tag = soup.find("span", id=_VED.subject_span_id)
    subject_name = dis_tag.get_text(strip=True) if dis_tag and dis_tag.get_text(strip=True) else "-"

    rows = soup.find_all("tr", class_=list(_VED.row_classes))
    table = soup.find("table", id=_VED.table_id)

    has_kt = soup.find("input", id=_VED.kt_checkbox_id) is not None
    is_rating = ved_type in RATING_VED_TYPES and has_kt and table is not None

    fmt = "reitingoviy" if is_rating else "otsenochniy"
    log.debug("Parsing vedomost", type=ved_type, subject=subject_name, format=fmt, rows=len(rows))

    if is_rating:
        records = _parse_rating(table, rows, ved_type, subject_name)
    else:
        records = _parse_grade(rows, ved_type, subject_name)

    log.debug("Parsing result", records=len(records), type=ved_type, subject=subject_name)
    return records


class ParserService:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._sem = asyncio.Semaphore(settings.scraper.concurrency)
        # Пул клиентов для скачивания ведомостей. ASP.NET сериализует запросы
        # ОДНОЙ сессии (lock на ASP.NET_SessionId): через общий клиент
        # «конкурентные» GET выполняются сервером по одному. Отдельный клиент =
        # отдельная сессия; клиент выдаётся ровно одной корутине за раз, поэтому
        # внутри сессии конкуренции нет, а между сессиями сервер параллелит.
        self._ved_pool: asyncio.Queue[httpx.AsyncClient] = asyncio.Queue()

    async def __aenter__(self) -> "ParserService":
        cfg = settings.scraper
        timeout = httpx.Timeout(cfg.timeout_s)
        headers = {"User-Agent": cfg.user_agent, "Referer": settings.site.base_url}
        self._client = httpx.AsyncClient(
            headers=headers,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=cfg.concurrency, max_keepalive_connections=cfg.concurrency),
            timeout=timeout,
        )
        for _ in range(cfg.concurrency):
            self._ved_pool.put_nowait(
                httpx.AsyncClient(
                    headers=headers,
                    follow_redirects=True,
                    limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
                    timeout=timeout,
                )
            )
        log.debug(
            "HTTP clients opened",
            ved_pool=cfg.concurrency,
            concurrency=cfg.concurrency,
            timeout_s=cfg.timeout_s,
            retries=cfg.retries,
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        while not self._ved_pool.empty():
            await self._ved_pool.get_nowait().aclose()
        log.debug("HTTP clients closed")

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("ParserService используется вне async-контекста")
        return self._client

    async def _request(
        self, method: str, url: str, client: httpx.AsyncClient | None = None, **kwargs
    ) -> httpx.Response:
        retries = settings.scraper.retries
        http = client if client is not None else self.client
        for attempt in range(1, retries + 1):
            try:
                r = await http.request(method, url, **kwargs)
            except httpx.HTTPError as exc:
                if attempt == retries:
                    log.error("Request failed", method=method, url=url, attempts=retries, error=repr(exc))
                    raise
                delay = _backoff_delay(attempt)
                log.warning(
                    "Request retry",
                    method=method,
                    url=url,
                    attempt=f"{attempt}/{retries}",
                    error=repr(exc),
                    delay_s=round(delay, 1),
                )
                await asyncio.sleep(delay)
                continue

            if r.status_code == 429:
                if attempt == retries:
                    log.warning("429 retry limit exceeded", url=url)
                    return r
                retry_after = r.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after is not None else _backoff_delay(attempt)
                except ValueError:
                    delay = _backoff_delay(attempt)
                log.warning("429 received", url=url, attempt=f"{attempt}/{retries}", delay_s=round(delay, 1))
                await asyncio.sleep(delay)
                continue

            return r
        raise RuntimeError("unreachable")

    async def _post(self, data: dict) -> str:
        r = await self._request("POST", settings.site.base_url, data=data)
        r.encoding = settings.site.encoding
        return r.text

    # --- публичные методы ---

    async def check_site_availability(self) -> bool:
        """True, если сайт отвечает HTTP 200."""
        try:
            r = await self._request("GET", settings.site.base_url)
        except httpx.HTTPError:
            log.warning("Site is unavailable (network error)")
            return False
        available = r.status_code == 200
        if available:
            log.debug("Site is available", status=r.status_code)
        else:
            log.warning("Site is unavailable", status=r.status_code)
        return available

    async def _group_urls(self, fac_fields: dict, fac: dict, grp: dict) -> list[str]:
        try:
            async with self._sem:
                html = await self._post(_form_data(settings.html_form.group_select, fac_fields, fac["id"], grp["id"]))
            urls = await asyncio.to_thread(_parse_urls, html)
            log.debug("Group vedomosts collected", group=grp["name"], count=len(urls))
            return urls
        except Exception as exc:
            log.error("Error collecting group vedomosts", group=grp["name"], error=repr(exc))
            return []

    async def _faculty_groups(self, base_fields: dict, fac: dict) -> dict[str, list[str]]:
        async with self._sem:
            fac_html = await self._post(_form_data(settings.html_form.faculty_select, base_fields, fac["id"], ""))
        fac_fields = await asyncio.to_thread(_parse_viewstate, fac_html)
        groups = await asyncio.to_thread(_parse_select, fac_html, settings.html_form.group_select)
        log.debug("Faculty groups collected", faculty=fac["name"], count=len(groups))

        lists = await asyncio.gather(*(self._group_urls(fac_fields, fac, grp) for grp in groups))
        return {grp["name"]: urls for grp, urls in zip(groups, lists, strict=True)}

    async def collect_ved_links(self) -> dict[str, list[str]]:
        """Конкурентно собирает ссылки на ведомости по всем группам.

        Возвращает {название_группы: [url1, url2, ...]}.
        """
        r = await self._request("GET", settings.site.base_url)
        r.encoding = settings.site.encoding
        base_fields = await asyncio.to_thread(_parse_viewstate, r.text)
        faculties = await asyncio.to_thread(_parse_select, r.text, settings.html_form.faculty_select)
        log.debug("Start collecting links", faculties=len(faculties))

        per_faculty = await asyncio.gather(*(self._faculty_groups(base_fields, fac) for fac in faculties))

        result: dict[str, list[str]] = {}
        for mapping in per_faculty:
            for group_name, urls in mapping.items():
                result.setdefault(group_name, []).extend(urls)

        total_urls = sum(len(v) for v in result.values())
        log.debug("Link collection completed", groups=len(result), vedomosts=total_urls)
        return result

    async def parse_ved(self, url: str) -> list[RatingVedModel] | list[NotRatingVedModel] | None:
        """Скачивает и парсит одну ведомость в записи целевого формата.

        Возвращает готовые доменные модели, а не словари.

        Различаем два исхода с пустым результатом:
          * None  — ведомость **потеряна** (сетевая ошибка или 429 после всех
            ретраев); это и есть реальная потеря для метрики.
          * []    — ведомость нерабочая/пустая (HTTP != 200, нет маркера типа
            или в ней нет записей); это штатный пропуск, не потеря.
        """
        client = await self._ved_pool.get()
        try:
            r = await self._request("GET", url, client=client)
        except httpx.HTTPError as exc:
            log.warning("Failed to download vedomost", url=url, error=repr(exc))
            return None
        finally:
            self._ved_pool.put_nowait(client)
        # 429 после исчерпания ретраев — реальная потеря.
        if r.status_code == 429:
            log.warning("Vedomost lost after retries (HTTP 429)", url=url)
            return None
        # Ранний признак нерабочей ведомости — статус 500 (и любой иной не-200).
        if r.status_code != 200:
            log.debug("Non-functional vedomost", status=r.status_code, url=url)
            return []
        r.encoding = settings.site.encoding
        # bs4-разбор — CPU-bound; в потоке, чтобы не блокировать event loop
        # (в нём же живёт FastAPI: синхронный разбор подвешивал API на время цикла).
        records = await asyncio.to_thread(_parse_ved_html, r.text)
        log.debug("Vedomost parsed", records=len(records), url=url)
        return records
