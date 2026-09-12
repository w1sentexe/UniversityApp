/**
 * Вход в зачётку и выход из неё — переключение между экраном входа и приложением.
 *
 * Номер зачётки здесь единственное состояние «входа»: пока он запомнен,
 * сессия считается открытой и переживает перезагрузку страницы.
 */

import { $ } from "./utils.js";
import { apiGet } from "./api.js";
import { loadSnapshotStatus, snapshotVersion } from "./data/snapshot-status.js";
import { disableNotificationsForStoredSession } from "./notifications.js";
import {
  clearZach,
  getCachedGroup,
  getStartTab,
  getZach,
  savedZach,
  setCachedGroup,
  setGroup,
  setZach,
} from "./store.js";
import { switchTab } from "./nav.js";
import { clearRating, loadRating } from "./view-rating.js";
import { focusZachInput, resetLoginForm } from "./login.js";
import { renderSchedule, resetSchedule } from "./view-schedule.js";
import { forgetSchedule } from "./data/schedule.js";
import { renderSettings } from "./view-settings.js";

const viewLogin = $("#view-login");
const viewApp = $("#view-app");
const tabSchedule = $("#tab-schedule");
const tabSettings = $("#tab-settings");
const RETURN_REFRESH_COOLDOWN_MS = 60000;

let lastReturnRefreshAt = 0;

export function openApp(zach) {
  setZach(zach);
  viewLogin.hidden = true;
  viewApp.hidden = false;
  resetSchedule();
  forgetSchedule();
  switchTab(getStartTab());
  refreshCurrentSession({ force: true });
}

function refreshCurrentSession({ force = false } = {}) {
  const zach = getZach();
  if (!zach || viewApp.hidden) return;

  const now = Date.now();
  if (!force && now - lastReturnRefreshAt < RETURN_REFRESH_COOLDOWN_MS) return;
  lastReturnRefreshAt = now;

  loadRating(zach, { force });
  loadGroup(zach, { force });
}

function refreshWhenVisible({ force = false } = {}) {
  if (document.visibilityState && document.visibilityState !== "visible") return;
  refreshCurrentSession({ force });
}

/**
 * Группа студента — отдельный запрос к беку, не блокирующий показ рейтинга.
 *
 * Запрашиваем сразу на входе, а не при открытии настроек: так к моменту, когда
 * пользователь туда зайдёт, значение уже на месте. Если настройки открыты прямо
 * сейчас (вход → сразу вкладка), перерисовываем их по приходу ответа.
 */
async function loadGroup(zach, { force = false } = {}) {
  const cached = getCachedGroup(zach);
  if (cached) setGroup(cached.groupName || null);

  try {
    const status = await loadSnapshotStatus({ force });
    const version = snapshotVersion(status);
    if (!cached || cached.snapshotVersion !== version) {
      const data = await apiGet(`/students/${encodeURIComponent(zach)}/group`);
      const groupName = data && data.group_name ? data.group_name : null;
      setGroup(groupName);
      setCachedGroup(zach, groupName, version);
    }
  } catch (_) {
    // Сеть или бек недоступны — оставляем кешированную группу, если она была.
    if (!cached) setGroup(null);
  }
  // Экраны, ждавшие группу, перерисовываем по приходу ответа.
  if (tabSettings && !tabSettings.hidden) renderSettings();
  if (tabSchedule && !tabSchedule.hidden) renderSchedule();
}

export function closeApp() {
  disableNotificationsForStoredSession();
  lastReturnRefreshAt = 0;
  clearZach();
  forgetSchedule();
  viewApp.hidden = true;
  viewLogin.hidden = false;
  clearRating();
  resetLoginForm();
}

/**
 * Восстановление сессии при загрузке страницы.
 *
 * Если номер больше не действителен, loadRating покажет ошибку с повтором,
 * а «Выход» в тулбаре вернёт на экран входа и забудет номер.
 */
export function restoreSession() {
  const zach = savedZach();
  if (zach) {
    openApp(zach);
    return true;
  }
  // Расставляем hidden явно: сразу после этого main.js снимет data-boot,
  // и видимостью экранов будет управлять только он.
  viewApp.hidden = true;
  viewLogin.hidden = false;
  focusZachInput();
  return false;
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") refreshWhenVisible();
});

window.addEventListener("focus", () => refreshWhenVisible());
window.addEventListener("online", () => refreshWhenVisible({ force: true }));
window.addEventListener("pageshow", (event) => {
  if (event.persisted) refreshWhenVisible({ force: true });
});

export { getZach };
