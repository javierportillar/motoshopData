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

/** POST /api/alerts/{sku}/action */
export async function submitAlertAction(
  sku: string,
  body: SubmitActionBody,
  idempotencyKey: string,
): Promise<ActionResponse> {
  return apiFetchJson<ActionResponse>(`/api/alerts/${encodeURIComponent(sku)}/action`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(body),
  });
}

/** GET /api/alerts/actions/me */
export async function fetchMyActions(
  date?: string,
  offset = 0,
  limit = 20,
): Promise<MyActionsResponse> {
  const params = new URLSearchParams();
  if (date) params.set("date", date);
  params.set("offset", String(offset));
  params.set("limit", String(limit));

  return apiFetchJson<MyActionsResponse>(
    `/api/alerts/actions/me?${params.toString()}`,
  );
}
