import { apiGet } from "../api.js";

const STATUS_CACHE_KEY = "rating:snapshotStatus";
const STATUS_MEMORY_TTL_MS = 15000;

let memoryStatus = null;
let memoryStatusAt = 0;
let inFlight = null;

export function readCachedSnapshotStatus() {
  try {
    const raw = localStorage.getItem(STATUS_CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    return null;
  }
}

export async function loadSnapshotStatus({ force = false } = {}) {
  const now = Date.now();
  if (!force && memoryStatus && now - memoryStatusAt < STATUS_MEMORY_TTL_MS) {
    return memoryStatus;
  }
  if (inFlight) return inFlight;

  inFlight = apiGet("/rating/snapshot/status")
    .then((status) => {
      memoryStatus = status;
      memoryStatusAt = Date.now();
      try {
        localStorage.setItem(STATUS_CACHE_KEY, JSON.stringify(status));
      } catch (_) {
        /* приватный режим — работаем только с памятью */
      }
      return status;
    })
    .finally(() => {
      inFlight = null;
    });

  return inFlight;
}

export function snapshotVersion(status) {
  return status && typeof status.version === "string" && status.version ? status.version : null;
}
