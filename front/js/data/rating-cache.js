const CACHE_SCHEMA = 1;
const CACHE_PREFIX = "rating:sections:";

export const RATING_REFRESH_COOLDOWN_MS = 60000;

function keyFor(zach) {
  return `${CACHE_PREFIX}${zach}`;
}

export function readRatingCache(zach) {
  try {
    const raw = localStorage.getItem(keyFor(zach));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || parsed.schema !== CACHE_SCHEMA || !parsed.entries) return null;
    return parsed;
  } catch (_) {
    return null;
  }
}

export function writeRatingCache(zach, cache) {
  try {
    localStorage.setItem(
      keyFor(zach),
      JSON.stringify({
        schema: CACHE_SCHEMA,
        savedAt: Date.now(),
        entries: cache.entries || {},
      }),
    );
  } catch (_) {
    /* приватный режим — кеш будет только сетевым через service worker */
  }
}

export function cacheHasVersion(cache, version, types) {
  if (!cache || !version) return false;
  return types.every((type) => cache.entries?.[type.segment]?.snapshotVersion === version);
}

export function typesNeedingRefresh(cache, version, types) {
  if (!version) return types;
  return types.filter((type) => cache?.entries?.[type.segment]?.snapshotVersion !== version);
}

export function mergeRatingCache(cache, updates, version) {
  const entries = { ...(cache?.entries || {}) };
  const savedAt = Date.now();
  updates.forEach(({ type, records }) => {
    entries[type.segment] = {
      records: Array.isArray(records) ? records : [],
      snapshotVersion: version,
      savedAt,
    };
  });
  return { schema: CACHE_SCHEMA, savedAt, entries };
}

export function sectionsFromCache(cache, types) {
  return types
    .map((type) => ({ type, records: cache?.entries?.[type.segment]?.records }))
    .filter((section) => Array.isArray(section.records) && section.records.length > 0);
}
