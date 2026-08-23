/**
 * Вход в зачётку и выход из неё — переключение между экраном входа и приложением.
 *
 * Номер зачётки здесь единственное состояние «входа»: пока он запомнен,
 * сессия считается открытой и переживает перезагрузку страницы.
 */

import { $ } from "./utils.js";
import { apiGet } from "./api.js";
import { disableNotificationsForStoredSession } from "./notifications.js";
import { clearZach, getZach, savedZach, setGroup, setZach } from "./store.js";
import { switchTab } from "./nav.js";
import { clearRating, loadRating } from "./view-rating.js";
import { focusZachInput, resetLoginForm } from "./login.js";
import { renderSettings } from "./view-settings.js";

const viewLogin = $("#view-login");
const viewApp = $("#view-app");
const tabSettings = $("#tab-settings");
const RETURN_REFRESH_COOLDOWN_MS = 3000;

let lastReturnRefreshAt = 0;

export function openApp(zach) {
  setZach(zach);
  viewLogin.hidden = true;
  viewApp.hidden = false;
  switchTab("rating");
  refreshCurrentSession({ force: true });
}

function refreshCurrentSession({ force = false } = {}) {
  const zach = getZach();
  if (!zach || viewApp.hidden) return;

  const now = Date.now();
  if (!force && now - lastReturnRefreshAt < RETURN_REFRESH_COOLDOWN_MS) return;
  lastReturnRefreshAt = now;

  loadRating(zach);
  loadGroup(zach);
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
async function loadGroup(zach) {
  try {
    const data = await apiGet(`/students/${encodeURIComponent(zach)}/group`);
    setGroup(data && data.group_name ? data.group_name : null);
  } catch (_) {
    // Сеть или бек недоступны — группа останется прочерком, рейтинг это не ломает.
    setGroup(null);
  }
  // Экраны, ждавшие группу, перерисовываем по приходу ответа.
  if (tabSettings && !tabSettings.hidden) renderSettings();
}

export function closeApp() {
  disableNotificationsForStoredSession();
  lastReturnRefreshAt = 0;
  clearZach();
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
