"use client";

import { apiFetchJson } from "./client";

type ActionType = "ordered" | "dismissed" | "postponed";

export interface SubmitActionBody {
  action_type: ActionType;
  quantity?: number;
  supplier?: string;
  reason?: string;
  postponed_to?: string;
  notes?: string;
}

interface ActionResponse {
  id: number;
  alert_id: string;
  sku: string;
  action_type: ActionType;
  user_id: string;
  created_at: string;
}

export interface MyActionItem {
  id: number;
  alert_id: string;
  sku: string;
  action_type: ActionType;
  quantity: number | null;
  supplier: string | null;
  reason: string | null;
  postponed_to: string | null;
  notes: string | null;
  created_at: string;
}

interface MyActionsResponse {
  actions: MyActionItem[];
  total: number;
}

/** POST /api/alerts/{sku}/action — fallback mock si Dev A no terminó. */
export async function submitAlertAction(
  sku: string,
  body: SubmitActionBody,
  idempotencyKey: string,
): Promise<ActionResponse> {
  try {
    return await apiFetchJson<ActionResponse>(`/api/alerts/${encodeURIComponent(sku)}/action`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify(body),
    });
  } catch (err: unknown) {
    if (err instanceof Error && err.message.includes("404")) {
      // Mock temporal mientras Dev A desarrolla el endpoint
      return mockSubmit(sku, body, idempotencyKey);
    }
    throw err;
  }
}

/** GET /api/alerts/actions/me — fallback mock si Dev A no terminó. */
export async function fetchMyActions(
  date?: string,
  offset = 0,
  limit = 20,
): Promise<MyActionsResponse> {
  const params = new URLSearchParams();
  if (date) params.set("date", date);
  params.set("offset", String(offset));
  params.set("limit", String(limit));

  try {
    return await apiFetchJson<MyActionsResponse>(
      `/api/alerts/actions/me?${params.toString()}`,
    );
  } catch (err: unknown) {
    if (err instanceof Error && err.message.includes("404")) {
      return mockFetchMyActions(date, offset, limit);
    }
    throw err;
  }
}

// ── Mock helpers (temporal, se borran cuando Dev A termine) ────────────────

let mockIdCounter = 0;
const mockStore: MyActionItem[] = [];

function mockSubmit(
  sku: string,
  body: SubmitActionBody,
  _idempotencyKey: string,
): ActionResponse {
  // Simular idempotency
  const existing = mockStore.find((a) => a.sku === sku && a.action_type === body.action_type);
  if (existing) {
    return {
      id: existing.id,
      alert_id: existing.alert_id,
      sku: existing.sku,
      action_type: existing.action_type,
      user_id: existing.sku,
      created_at: existing.created_at,
    };
  }

  mockIdCounter++;
  const created = new Date().toISOString();
  const entry: MyActionItem = {
    id: mockIdCounter,
    alert_id: sku,
    sku,
    action_type: body.action_type,
    quantity: body.quantity ?? null,
    supplier: body.supplier ?? null,
    reason: body.reason ?? null,
    postponed_to: body.postponed_to ?? null,
    notes: body.notes ?? null,
    created_at: created,
  };
  mockStore.push(entry);

  return {
    id: entry.id,
    alert_id: sku,
    sku,
    action_type: body.action_type,
    user_id: sku,
    created_at: created,
  };
}

function mockFetchMyActions(
  _date?: string,
  _offset = 0,
  _limit = 20,
): MyActionsResponse {
  return { actions: mockStore.slice(), total: mockStore.length };
}
