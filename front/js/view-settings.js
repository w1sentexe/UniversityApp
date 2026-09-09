/**
 * Экран настроек: карточка профиля, выбор темы и стартового раздела.
 *
 * Перерисовывается целиком при каждом открытии вкладки и после смены настройки —
 * состояния тут нет, всё берётся из store и theme.
 */

import { START_TABS } from "./config.js";
import { $, escapeHtml } from "./utils.js";
import { getGroup, getStartTab, getZach, setStartTab } from "./store.js";
import {
  disableNotifications,
  enableNotifications,
  notificationState,
  syncExistingNotificationSubscription,
} from "./notifications.js";
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
  const startTab = getStartTab();

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
        <p class="set-card__label">Запуск</p>
        <div class="set-row set-row--control">
          <span class="set-row__k">Открывать при входе</span>
          <div class="seg" role="group" aria-label="Раздел при входе">
            ${START_TABS.map(
              (tab) =>
                `<button class="seg__btn ${tab.id === startTab ? "is-active" : ""}" type="button" data-set-start="${tab.id}">${tab.title}</button>`,
            ).join("")}
          </div>
        </div>
      </div>
      <div class="set-card">
        <p class="set-card__label">Уведомления</p>
        <div class="set-row set-row--control">
          <span class="set-row__k">Новый рейтинг</span>
          <label class="switch">
            <input class="switch__input" type="checkbox" role="switch" data-push-toggle disabled />
            <span class="switch__track" aria-hidden="true">
              <span class="switch__thumb"></span>
            </span>
            <span class="switch__text" data-push-status>Проверяем…</span>
          </label>
        </div>
      </div>
    </div>`;

  el.querySelectorAll("[data-set-theme]").forEach((b) =>
    b.addEventListener("click", () => {
      applyTheme(b.dataset.setTheme);
      renderSettings();
    }),
  );

  el.querySelectorAll("[data-set-start]").forEach((b) =>
    b.addEventListener("click", () => {
      setStartTab(b.dataset.setStart);
      renderSettings();
    }),
  );
  syncNotificationControl();
}

async function syncNotificationControl() {
  const toggle = document.querySelector("[data-push-toggle]");
  const status = document.querySelector("[data-push-status]");
  if (!toggle || !status) return;

  try {
    const state = await notificationState();
    const zach = getZach();
    if (state.enabled && zach) await syncExistingNotificationSubscription(zach);

    toggle.disabled = !state.supported || state.permission === "denied" || !zach;
    toggle.checked = state.enabled;
    status.textContent = state.permission === "denied" ? "Запрещены" : state.enabled ? "Включены" : "Выключены";
  } catch (err) {
    toggle.disabled = true;
    status.textContent = err instanceof Error ? err.message : "Недоступно";
  }

  toggle.addEventListener("change", async () => {
    const zach = getZach();
    if (!zach) return;
    const enabled = toggle.checked;
    toggle.disabled = true;
    status.textContent = enabled ? "Включаем…" : "Выключаем…";
    try {
      if (enabled) await enableNotifications(zach);
      else await disableNotifications();
      renderSettings();
    } catch (err) {
      toggle.checked = !enabled;
      toggle.disabled = false;
      status.textContent = err instanceof Error ? err.message : "Ошибка";
    }
  });
}
