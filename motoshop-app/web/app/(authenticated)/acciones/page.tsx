"use client";

import { useState, useEffect, useCallback } from "react";
import { fetchMyActions, type MyActionItem } from "@/lib/api/alertActions";
import Link from "next/link";

type Period = "today" | "week" | "month";

const PERIOD_LABELS: Record<Period, string> = {
  today: "Hoy",
  week: "Esta semana",
  month: "Este mes",
};

const ACTION_STYLES: Record<string, { bg: string; label: string }> = {
  ordered: { bg: "border-l-green-500 bg-green-50", label: "Pedido" },
  dismissed: { bg: "border-l-gray-400 bg-gray-50", label: "Descartado" },
  postponed: { bg: "border-l-blue-500 bg-blue-50", label: "Pospuesto" },
};

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("es-CO", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export default function MyActionsPage(): JSX.Element {
  const [period, setPeriod] = useState<Period>("today");
  const [actions, setActions] = useState<MyActionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const dateParam = period === "today" ? new Date().toISOString().slice(0, 10) : undefined;
      const resp = await fetchMyActions(dateParam);
      setActions(resp.actions);
      setTotal(resp.total);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <Link href="/dashboards" className="text-sm text-primary hover:underline">
        ← Volver a Dashboards
      </Link>

      <h1 className="text-xl font-bold text-secondary-dark">Mis acciones del día</h1>
      <p className="text-sm text-gray-500">
        {total > 0 ? `${total} acción${total !== 1 ? "es" : ""} registrada${total !== 1 ? "s" : ""}` : "Ninguna acción aún"}
      </p>

      {/* Filtros de período */}
      <div className="flex gap-2">
        {(["today", "week", "month"] as const).map((p) => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              period === p
                ? "bg-gray-800 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {PERIOD_LABELS[p]}
          </button>
        ))}
      </div>

      {/* Loading */}
      {loading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-xl bg-gray-100" />
          ))}
        </div>
      )}

      {/* Lista de acciones */}
      {!loading && actions.length === 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-center">
          <p className="text-sm text-gray-400">No hay acciones en este período</p>
        </div>
      )}

      {!loading && actions.map((a) => {
        const style = ACTION_STYLES[a.action_type] ?? { bg: "border-l-gray-300 bg-gray-50", label: a.action_type };
        return (
          <div
            key={a.id}
            className={`rounded-xl border-l-4 p-4 ${style.bg}`}
          >
            <div className="flex items-start justify-between">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-gray-400">{a.sku}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium text-white ${
                    a.action_type === "ordered" ? "bg-green-600" :
                    a.action_type === "dismissed" ? "bg-gray-500" : "bg-blue-600"
                  }`}>
                    {style.label}
                  </span>
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  {formatDate(a.created_at)}
                </p>
                {a.action_type === "ordered" && a.quantity != null && (
                  <p className="mt-1 text-sm text-gray-600">
                    Cantidad: {a.quantity}{a.supplier ? ` — ${a.supplier}` : ""}
                  </p>
                )}
                {a.action_type === "dismissed" && a.reason && (
                  <p className="mt-1 text-sm text-gray-600">{a.reason}</p>
                )}
                {a.action_type === "postponed" && a.postponed_to && (
                  <p className="mt-1 text-sm text-gray-600">
                    Revisar el {new Date(a.postponed_to).toLocaleDateString("es-CO")}
                  </p>
                )}
                {a.notes && (
                  <p className="mt-1 text-xs text-gray-400 italic">{a.notes}</p>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
