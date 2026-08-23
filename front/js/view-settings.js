/**
 * Экран настроек: карточка профиля и выбор темы.
 *
 * Перерисовывается целиком при каждом открытии вкладки и после смены темы —
 * состояния тут нет, всё берётся из store и theme.
 */

import { $, escapeHtml } from "./utils.js";
import {
  disableNotifications,
  enableNotifications,
  notificationState,
  syncExistingNotificationSubscription,
} from "./notifications.js";
import { getGroup, getZach } from "./store.js";
import { applyTheme, currentTheme } from "./theme.js";

/**
 * Группу подгружает session.js при входе.
 * undefined — ответ ещё не пришёл, null — бек ответил, что связки нет.
 */
function groupLabel() {
  const group = getGroup();
  if (group === undefined) return "…";
  return group || "—";
}

export function renderSettings() {
  const el = $("#settings-content");
  const theme = currentTheme();

  el.innerHTML = `
    <div class="settings">
      <div class="set-card">
        <p class="set-card__label">Профиль</p>
        <div class="set-list">
          <div class="set-row">
            <span class="set-row__k">Зачётная книжка</span>
            <span class="set-row__v set-row__v--code">№ ${escapeHtml(getZach() || "—")}</span>
          </div>
          <div class="set-row">
            <span class="set-row__k">Группа</span>
            <span class="set-row__v set-row__v--code">${escapeHtml(groupLabel())}</span>
          </div>
        </div>
      </div>

      <div class="set-card">
        <p class="set-card__label">Оформление</p>
        <div class="set-row set-row--control">
          <span class="set-row__k">Тема</span>
          <div class="seg" role="group" aria-label="Тема оформления">
            <button class="seg__btn ${theme === "light" ? "is-active" : ""}" type="button" data-set-theme="light">Светлая</button>
            <button class="seg__btn ${theme === "dark" ? "is-active" : ""}" type="button" data-set-theme="dark">Тёмная</button>
          </div>
        </div>
      </div>

      <div class="set-card">
        <p class="set-card__label">Уведомления</p>
        <div class="set-row set-row--control">
          <span class="set-row__k">Новый рейтинг</span>
          <button class="btn btn--ghost set-action" type="button" data-push-toggle disabled>Проверяем…</button>
        </div>
      </div>
    </div>`;

  el.querySelectorAll("[data-set-theme]").forEach((b) =>
    b.addEventListener("click", () => {
      applyTheme(b.dataset.setTheme);
      renderSettings();
    }),
  );

  syncNotificationControl();
}

async function syncNotificationControl() {
  const button = document.querySelector("[data-push-toggle]");
  if (!button) return;

  try {
    const state = await notificationState();
    const zach = getZach();
    if (state.enabled && zach) await syncExistingNotificationSubscription(zach);

    button.disabled = !state.supported || state.permission === "denied";
    button.dataset.enabled = state.enabled ? "true" : "false";
    button.textContent = state.enabled ? "Выключить" : state.label;
    if (state.supported && !state.enabled && state.permission !== "denied") {
      button.textContent = "Включить";
    }
  } catch (_) {
    button.disabled = true;
    button.textContent = "Недоступно";
  }

  button.addEventListener("click", async () => {
    const zach = getZach();
    if (!zach) return;
    button.disabled = true;
    const enabled = button.dataset.enabled === "true";
    button.textContent = enabled ? "Выключаем…" : "Включаем…";
    try {
      if (enabled) await disableNotifications();
      else await enableNotifications(zach);
    } finally {
      renderSettings();
    }
  });
}
