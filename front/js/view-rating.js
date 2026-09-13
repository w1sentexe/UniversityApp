/**
 * Экран рейтинга: загрузка ведомостей и их отрисовка.
 *
 * Каждый вид ведомости — отдельный запрос; часть может не ответить, поэтому
 * идём через allSettled и показываем то, что пришло, с баннером о недогрузе.
 * Детализацию контрольной точки открывает js/kt-popup.js по клику на ячейку.
 */

import { DASH, VED_TYPES, WORK_LABELS } from "./config.js";
import { apiGet } from "./api.js";
import {
  RATING_REFRESH_COOLDOWN_MS,
  cacheHasVersion,
  mergeRatingCache,
  readRatingCache,
  sectionsFromCache,
  typesNeedingRefresh,
  writeRatingCache,
} from "./data/rating-cache.js";
import { loadSnapshotStatus, snapshotVersion } from "./data/snapshot-status.js";
import {
  $,
  disciplines,
  escapeHtml,
  gradeClass,
  isBlank,
  isRatingRecord,
  sealSvg,
  showNum,
} from "./utils.js";

const ratingContent = $("#rating-content");
const lastRefreshByZach = new Map();

function numericValue(value) {
  if (isBlank(value)) return null;
  const normalized = String(value).trim().replace(",", ".");
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function calculatedFinalRating(record) {
  const totals = (record.control_points || [])
    .map((cp) => numericValue(cp.total))
    .filter((value) => value !== null);
  if (totals.length === 0) return DASH;

  const average = totals.reduce((sum, value) => sum + value, 0) / totals.length;
  return Number.isInteger(average) ? String(average) : String(Number(average.toFixed(2)));
}

function hasControlPointDetails(point) {
  return Object.keys(WORK_LABELS).some((key) => !isBlank(point?.[key]?.weight));
}

/** Очистка при выходе из зачётки. */
export function clearRating() {
  ratingContent.innerHTML = "";
}

function renderState(kind, title, text, retry) {
  const cls = kind === "loading" ? "state loading" : "state";
  ratingContent.innerHTML = `
    <div class="${cls}">
      ${sealSvg}
      <h2 class="state__title">${escapeHtml(title)}</h2>
      <p class="state__text">${escapeHtml(text)}</p>
      ${retry ? '<button class="btn" type="button" id="state-retry">Повторить</button>' : ""}
    </div>`;
  if (retry) $("#state-retry").addEventListener("click", retry);
}

export async function loadRating(zach, { force = false, reloadSections = false } = {}) {
  let cache = readRatingCache(zach);
  if (cache) {
    renderRating(zach, cache, { failedTypes: [] });
  } else {
    renderState("loading", "Открываем зачётную книжку", `№ ${zach} · собираем ведомости…`);
  }

  const now = Date.now();
  const lastRefresh = lastRefreshByZach.get(zach) || 0;
  if (!force && cache && now - lastRefresh < RATING_REFRESH_COOLDOWN_MS) return;
  lastRefreshByZach.set(zach, now);

  let status;
  try {
    status = await loadSnapshotStatus({ force });
  } catch (_) {
    if (!cache) {
      renderState("error", "Не удалось загрузить данные", "Сервер недоступен или вернул ошибку.", () =>
        loadRating(zach, { force: true, reloadSections: true }),
      );
    }
    return;
  }

  const version = snapshotVersion(status);
  if (!reloadSections && cacheHasVersion(cache, version, VED_TYPES)) return;

  const types = reloadSections ? VED_TYPES : typesNeedingRefresh(cache, version, VED_TYPES);
  const results = await Promise.allSettled(
    types.map((t) => apiGet(`/rating/${encodeURIComponent(zach)}/${t.segment}`)),
  );

  const updates = [];
  const failedTypes = [];
  results.forEach((res, i) => {
    const type = types[i];
    if (res.status === "fulfilled") {
      const records = Array.isArray(res.value) ? res.value : [];
      updates.push({ type, records });
    } else {
      failedTypes.push(type);
    }
  });

  if (updates.length > 0) {
    cache = mergeRatingCache(cache, updates, version);
    writeRatingCache(zach, cache);
  }

  if (!cache && failedTypes.length === types.length) {
    renderState("error", "Не удалось загрузить данные", "Сервер недоступен или вернул ошибку.", () =>
      loadRating(zach, { force: true, reloadSections: true }),
    );
    return;
  }

  renderRating(zach, cache, { failedTypes });
}

function renderRating(zach, cache, { failedTypes }) {
  const sections = sectionsFromCache(cache, VED_TYPES);
  if (sections.length === 0) {
    renderState("empty", "Ведомостей пока нет", `По зачётной книжке № ${zach} данные об успеваемости отсутствуют.`);
    return;
  }

  let html = "";
  if (failedTypes.length > 0) {
    html += `
      <div class="banner" role="status">
        <span>Некоторые разделы не обновились (${failedTypes.length}).</span>
        <button class="btn btn--ghost banner__retry" type="button" id="banner-retry">Повторить</button>
      </div>`;
  }
  html += sections.map((s, idx) => renderSection(s, idx)).join("");
  ratingContent.innerHTML = html;

  const bannerRetry = $("#banner-retry");
  if (bannerRetry) {
    bannerRetry.addEventListener("click", () => loadRating(zach, { force: true, reloadSections: true }));
  }
}

function renderSection(section, index) {
  const { type, records } = section;
  const rating = isRatingRecord(records[0]);
  const table  = rating ? renderRatingTable(records) : renderGradeTable(records);

  return `
    <section class="section" style="animation-delay:${Math.min(index, 8) * 55}ms">
      <div class="section__head">
        <h2 class="section__title">${escapeHtml(type.title)}</h2>
        <span class="section__count">${disciplines(records.length)}</span>
      </div>
      ${table}
    </section>`;
}

// ---- рейтинговая таблица со sticky-колонкой ----
function renderRatingTable(records) {
  const maxKt = records.reduce((m, r) => Math.max(m, (r.control_points || []).length), 0);

  // Заголовок: sticky-ячейка «Дисциплина» + КТ-колонки + «Рейтинг»
  let head = '<tr><th class="rt-subject">Дисциплина</th>';
  for (let k = 1; k <= maxKt; k++) {
    head += `<th class="kt-result">КТ ${k}</th>`;
  }
  head += '<th class="rt-final">Рейтинг</th></tr>';

  const body = records.map((rec) => {
    const cps = rec.control_points || [];
    // sticky-ячейка названия
    let row = `<td class="rt-subject">${escapeHtml(rec.subject_name)}</td>`;

    for (let k = 0; k < maxKt; k++) {
      const cp = cps[k];
      const total = cp ? showNum(cp.total) : DASH;
      const hasDetails = cp && hasControlPointDetails(cp);

      if (hasDetails) {
        const cpJson = escapeHtml(JSON.stringify(cp));
        row += `<td class="rt-total rt-total--clickable"
                    data-cp="${cpJson}"
                    data-kt="${k + 1}"
                    data-subject="${escapeHtml(rec.subject_name)}"
                    title="Нажмите для деталей"
                    tabindex="0"
                    role="button">${total}</td>`;
      } else {
        row += `<td class="rt-total">${total}</td>`;
      }
    }

    row += `<td class="rt-rating">${escapeHtml(calculatedFinalRating(rec))}</td>`;
    return `<tr>${row}</tr>`;
  }).join("");

  // rt-scroll — новая обёртка вместо table-scroll, содержит тени-подсказки
  return `
    <div class="rt-scroll">
      <table class="rt">
        <thead>${head}</thead>
        <tbody>${body}</tbody>
      </table>
    </div>
    <p class="rt-caption">Нажмите на балл КТ, чтобы увидеть детализацию по видам работ.</p>`;
}

// ---- оценочная таблица ----
function renderGradeTable(records) {
  const rows = records.map((rec) => {
    const grade = isBlank(rec.grade) ? DASH : rec.grade;
    return `
      <tr>
        <td class="gt-subject">${escapeHtml(rec.subject_name)}</td>
        <td><span class="chip ${gradeClass(rec.grade)}">${escapeHtml(grade)}</span></td>
      </tr>`;
  }).join("");

  return `
    <div class="table-scroll">
      <table class="gt">
        <thead><tr><th>Дисциплина</th><th>Оценка</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}
