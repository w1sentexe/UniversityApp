/**
 * Состояние сессии: чей рейтинг сейчас открыт и с какого раздела начинать.
 *
 * Вынесено отдельным модулем без импортов намеренно. Номер зачётки нужен и
 * экрану настроек, и экрану рейтинга, и логике входа. Если бы его хранил
 * session.js, получилось бы кольцо импортов: session → nav → settings → session.
 */

import { DEFAULT_START_TAB, START_TABS, STORAGE_KEYS } from "./config.js";

let currentZach = "";
// Группа приходит с бека отдельным запросом и живёт только в памяти:
// на диск её не кладём, чтобы после смены группы не показывать устаревшую.
// undefined — ещё не запрашивали, null — бек ответил, что группы нет.
let currentGroup;

export function getZach() {
  return currentZach;
}

export function getGroup() {
  return currentGroup;
}

export function setGroup(groupName) {
  currentGroup = groupName;
}

/** Запоминает номер и в памяти, и на диске: сессия должна пережить перезагрузку. */
export function setZach(zach) {
  currentZach = zach;
  try {
    localStorage.setItem(STORAGE_KEYS.zach, zach);
  } catch (_) {
    /* приватный режим — работаем без сохранения */
  }
}

export function clearZach() {
  currentZach = "";
  currentGroup = undefined;
  try {
    localStorage.removeItem(STORAGE_KEYS.zach);
  } catch (_) {
    /* см. выше */
  }
}

/** Номер из прошлой сессии либо null. */
export function savedZach() {
  try {
    return localStorage.getItem(STORAGE_KEYS.zach);
  } catch (_) {
    return null;
  }
}

/**
 * Раздел, который открывается сразу после входа.
 *
 * Читается с проверкой по списку: в localStorage могло остаться имя раздела,
 * которого больше нет, и switchTab тогда спрятал бы все панели разом.
 */
export function getStartTab() {
  let saved = null;
  try {
    saved = localStorage.getItem(STORAGE_KEYS.startTab);
  } catch (_) {
    /* приватный режим — остаёмся на разделе по умолчанию */
  }
  return START_TABS.some((tab) => tab.id === saved) ? saved : DEFAULT_START_TAB;
}

export function setStartTab(name) {
  try {
    localStorage.setItem(STORAGE_KEYS.startTab, name);
  } catch (_) {
    /* приватный режим — выбор не запомнится */
  }
}
