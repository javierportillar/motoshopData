import { get, set, del, clear } from "idb-keyval";

const PREFIX = "motoshop:";
const DEFAULT_TTL_MS = 60 * 60 * 1000; // 1 hour

interface CacheEntry<T> {
  data: T;
  timestamp: number;
  ttl: number;
}

export async function getCached<T>(key: string): Promise<T | null> {
  try {
    const entry = await get<CacheEntry<T>>(PREFIX + key);
    if (!entry) return null;
    if (Date.now() - entry.timestamp > entry.ttl) {
      await del(PREFIX + key);
      return null;
    }
    return entry.data;
  } catch {
    return null;
  }
}

export async function setCache<T>(
  key: string,
  data: T,
  ttlMs: number = DEFAULT_TTL_MS,
): Promise<void> {
  try {
    await set(PREFIX + key, { data, timestamp: Date.now(), ttl: ttlMs });
  } catch {
    // IndexedDB full or unavailable — silent fail
  }
}

export async function removeCache(key: string): Promise<void> {
  try {
    await del(PREFIX + key);
  } catch {
    // ignore
  }
}

export async function clearAllCache(): Promise<void> {
  try {
    const keys = await get<string[] | undefined>(PREFIX + "_keys");
    if (keys) {
      await Promise.all(keys.map((k) => del(PREFIX + k)));
    }
    await clear();
  } catch {
    // ignore
  }
}


