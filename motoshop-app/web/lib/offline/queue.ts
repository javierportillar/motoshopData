"use client";

import { get, set } from "idb-keyval";
import { submitAlertAction } from "@/lib/api/alertActions";
import type { SubmitActionBody } from "@/lib/api/alertActions";

const STORE_KEY = "pending-actions";
const MAX_RETRIES = 6;
const MAX_ITEMS = 100;

interface PendingAction {
  idempotency_key: string;
  sku: string;
  body: SubmitActionBody;
  attempt: number;
  created_at: string;
  last_error?: string;
}

export type { PendingAction };

/** Guarda una acción en la cola offline. */
export async function enqueueAction(
  sku: string,
  body: SubmitActionBody,
  idempotencyKey: string,
): Promise<void> {
  const queue = await getQueue();
  if (queue.length >= MAX_ITEMS) {
    throw new Error("Demasiadas acciones pendientes. Sincronizá manualmente.");
  }
  queue.push({
    idempotency_key: idempotencyKey,
    sku,
    body,
    attempt: 0,
    created_at: new Date().toISOString(),
  });
  await set(STORE_KEY, queue);
}

/** Obtiene la cola completa. */
export async function getQueue(): Promise<PendingAction[]> {
  try {
    return (await get<PendingAction[]>(STORE_KEY)) ?? [];
  } catch {
    return [];
  }
}

/** Obtiene la cantidad de acciones pendientes. */
export async function getQueueCount(): Promise<number> {
  const queue = await getQueue();
  return queue.length;
}

/** Intenta reenviar todas las acciones pendientes. Retorna cuántas sincronizó. */
export async function flushQueue(): Promise<number> {
  const queue = await getQueue();
  if (queue.length === 0) return 0;

  const remaining: PendingAction[] = [];
  let synced = 0;

  for (const item of queue) {
    try {
      await submitAlertAction(item.sku, item.body, item.idempotency_key);

      // 201/200 → éxito (idempotent replay incluido)
      synced++;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);

      if (msg.includes("401") || msg.includes("403") || msg.includes("422")) {
        // Errores fatales: no reintentar
        continue;
      }

      if (item.attempt < MAX_RETRIES - 1) {
        remaining.push({
          ...item,
          attempt: item.attempt + 1,
          last_error: msg,
        });
      }
      // Si llegó a MAX_RETRIES, se descarta silenciosamente
    }
  }

  await set(STORE_KEY, remaining);

  // Disparar evento para que el badge se actualice
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("queue-flushed", { detail: { synced, remaining: remaining.length } }));
  }

  return synced;
}

/** Scheduler de reintentos: corre flushQueue cada 30s + cuando hay conexión. */
let intervalId: ReturnType<typeof setInterval> | null = null;

export function startQueueScheduler(): void {
  if (intervalId) return;

  // Flush inmediato si hay conexión
  if (navigator.onLine) {
    flushQueue();
  }

  // Reintentar cada 30s
  intervalId = setInterval(() => {
    if (navigator.onLine) {
      flushQueue();
    }
  }, 30_000);

  // Flush al reconectar
  window.addEventListener("online", handleOnline);
}

function handleOnline(): void {
  flushQueue();
}

export function stopQueueScheduler(): void {
  if (intervalId) {
    clearInterval(intervalId);
    intervalId = null;
  }
  window.removeEventListener("online", handleOnline);
}
