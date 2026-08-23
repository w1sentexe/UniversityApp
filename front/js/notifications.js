import { apiGet, apiPost } from "./api.js";
import { STORAGE_KEYS } from "./config.js";

const LAST_ENDPOINT_KEY = "rating:pushEndpoint";

function supported() {
  return (
    window.isSecureContext &&
    "Notification" in window &&
    "serviceWorker" in navigator &&
    "PushManager" in window
  );
}

function urlBase64ToUint8Array(value) {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) output[i] = raw.charCodeAt(i);
  return output;
}

function storeEndpoint(endpoint) {
  try {
    localStorage.setItem(LAST_ENDPOINT_KEY, endpoint);
  } catch (_) {}
}

function forgetEndpoint() {
  try {
    localStorage.removeItem(LAST_ENDPOINT_KEY);
  } catch (_) {}
}

function savedEndpoint() {
  try {
    return localStorage.getItem(LAST_ENDPOINT_KEY);
  } catch (_) {
    return null;
  }
}

export async function notificationState() {
  if (!supported()) return { supported: false, enabled: false, label: "Недоступно" };
  const backend = await apiGet("/notifications/status");
  if (!backend.supported) return { supported: false, enabled: false, label: "Недоступно" };
  const permission = Notification.permission;
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  return {
    supported: true,
    enabled: Boolean(subscription),
    permission,
    label: subscription ? "Включены" : permission === "denied" ? "Запрещены" : "Выключены",
  };
}

export async function enableNotifications(zach) {
  if (!supported()) throw new Error("Push is not supported");

  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Notification permission denied");

  const { public_key: publicKey } = await apiGet("/notifications/vapid-public-key");
  const registration = await navigator.serviceWorker.ready;
  const existing = await registration.pushManager.getSubscription();
  const subscription =
    existing ||
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    }));

  await apiPost("/notifications/subscribe", {
    zach_number: zach,
    subscription: subscription.toJSON(),
  });
  storeEndpoint(subscription.endpoint);
}

export async function syncExistingNotificationSubscription(zach) {
  if (!supported() || Notification.permission !== "granted") return false;

  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (!subscription) return false;

  await apiPost("/notifications/subscribe", {
    zach_number: zach,
    subscription: subscription.toJSON(),
  });
  storeEndpoint(subscription.endpoint);
  return true;
}

export async function disableNotifications() {
  if (!supported()) return;

  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  const endpoint = subscription ? subscription.endpoint : savedEndpoint();

  if (endpoint) await apiPost("/notifications/unsubscribe", { endpoint });
  if (subscription) await subscription.unsubscribe();
  forgetEndpoint();
}

export async function disableNotificationsForStoredSession() {
  try {
    if (localStorage.getItem(STORAGE_KEYS.zach)) await disableNotifications();
  } catch (_) {}
}
