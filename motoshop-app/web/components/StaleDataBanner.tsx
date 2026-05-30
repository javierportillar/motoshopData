"use client";

import useSWR from "swr";
import { apiFetchJson } from "@/lib/api/client";

interface FreshnessResponse {
  status: "OK" | "WARN" | "STALE" | "CRITICAL" | "ERROR";
  lag_hours: number;
  last_manifest: string | null;
}

function formatLag(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  const days = Math.floor(hours / 24);
  const rest = hours % 24;
  return rest > 0 ? `${days}d ${rest.toFixed(0)}h` : `${days}d`;
}

export function StaleDataBanner(): JSX.Element | null {
  const { data, error } = useSWR<FreshnessResponse>(
    "/api/health/data-freshness",
    apiFetchJson<FreshnessResponse>,
    { refreshInterval: 5 * 60 * 1000 },
  );

  if (error) {
    return (
      <div
        data-testid="stale-banner"
        className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700"
      >
        <span className="h-2 w-2 rounded-full bg-red-500" />
        No se pudo verificar frescura de datos
      </div>
    );
  }

  if (!data) return null;

  const stale = data.lag_hours > 24 || data.status === "STALE" || data.status === "CRITICAL";

  if (!stale) return null;

  const formattedTime = formatLag(data.lag_hours);

  return (
    <div
      data-testid="stale-banner"
      className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-700"
    >
      <span className="h-2 w-2 rounded-full bg-amber-400" />
      Predicciones basadas en datos de hace {formattedTime}. Revisar pipeline de actualización.
    </div>
  );
}
