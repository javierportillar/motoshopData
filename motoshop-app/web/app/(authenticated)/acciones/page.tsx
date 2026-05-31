"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { fetchMyActions, type MyActionItem } from "@/lib/api/alertActions";
import { useAlerts } from "@/lib/api/hooks";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";

type Period = "today" | "week" | "month";

const PERIOD_LABELS: Record<Period, string> = {
  today: "Hoy",
  week: "Esta semana",
  month: "Este mes",
};

const ACTION_BADGE: Record<string, { variant: "success" | "default" | "info"; label: string }> = {
  ordered: { variant: "success", label: "Pedido" },
  dismissed: { variant: "default", label: "Descartado" },
  postponed: { variant: "info", label: "Pospuesto" },
};

const URGENCY_BADGE: Record<string, { variant: "error" | "warning" | "info"; label: string }> = {
  alta: { variant: "error", label: "Alta" },
  media: { variant: "warning", label: "Media" },
  baja: { variant: "info", label: "Baja" },
};

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("es-CO", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function MyActionsPage(): JSX.Element {
  const [period, setPeriod] = useState<Period>("today");
  const [actions, setActions] = useState<MyActionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const { data: alertsData, error: alertsError, isLoading: alertsLoading } = useAlerts();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const today = new Date().toISOString().slice(0, 10);
      let dateFrom: string | undefined;
      let dateTo: string | undefined;

      if (period === "today") {
        dateFrom = today;
        dateTo = today;
      } else if (period === "week") {
        const monday = new Date();
        const day = monday.getDay();
        const diff = day === 0 ? 6 : day - 1;
        monday.setDate(monday.getDate() - diff);
        dateFrom = monday.toISOString().slice(0, 10);
        dateTo = today;
      } else if (period === "month") {
        const first = new Date();
        first.setDate(1);
        dateFrom = first.toISOString().slice(0, 10);
        dateTo = today;
      }

      const resp = await fetchMyActions(dateFrom, dateTo);
      setActions(resp.items);
      setTotal(resp.total);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    load();
  }, [load]);

  const counts = {
    ordered: actions.filter((a) => a.action_type === "ordered").length,
    dismissed: actions.filter((a) => a.action_type === "dismissed").length,
    postponed: actions.filter((a) => a.action_type === "postponed").length,
  };

  const hasRecomendaciones = alertsData && alertsData.alerts.length > 0;
  const hasHistorial = actions.length > 0;

  return (
    <div className="space-y-6">
      <Link href="/" className="text-sm text-accent hover:underline">
        ← Volver a inicio
      </Link>

      <div>
        <h1 className="text-xl font-bold text-text-primary">Acciones</h1>
        <p className="text-sm text-text-muted">
          {hasRecomendaciones
            ? `${alertsData!.alerts.length} producto${alertsData!.alerts.length !== 1 ? "s" : ""} necesita${alertsData!.alerts.length !== 1 ? "n" : ""} atención`
            : "Sin recomendaciones pendientes"}
          {hasHistorial && ` · ${total} acción${total !== 1 ? "es" : ""} registrada${total !== 1 ? "s" : ""}`}
        </p>
      </div>

      {/* ── Recomendaciones activas ──────────────────────────────── */}

      {alertsLoading && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-text-primary">Recomendaciones</h2>
          {[1, 2].map((i) => (
            <Skeleton key={i} className="h-20 rounded-xl" />
          ))}
        </div>
      )}

      {alertsError && (
        <ErrorState
          title="Error al cargar recomendaciones"
          message="No se pudieron obtener las alertas de stock."
          severity="info"
        />
      )}

      {hasRecomendaciones && (
        <section>
          <h2 className="mb-3 text-sm font-semibold text-text-primary">Recomendaciones activas</h2>
          <div className="space-y-2">
            {alertsData!.alerts.map((a) => {
              const urgency = URGENCY_BADGE[a.urgencia] ?? { variant: "default" as const, label: a.urgencia };
              return (
                <div
                  key={a.sku}
                  className="rounded-xl border-l-4 border-l-primary bg-surface p-4 shadow-sm"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-text-muted">{a.sku}</span>
                        <Badge variant={urgency.variant} size="sm">{urgency.label}</Badge>
                      </div>
                      <p className="mt-0.5 text-sm font-medium text-text-primary">{a.nom_producto}</p>
                      <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
                        <span>Stock: <strong className="text-text-primary">{a.stock_actual}</strong></span>
                        <span>Demanda: <strong className="text-text-primary">{a.demanda_predicha}</strong></span>
                        <span>Quiebre en: <strong className="text-text-primary">{a.dias_hasta_quiebre} días</strong></span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ── Historial ────────────────────────────────────────────── */}

      {hasHistorial && (
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-text-primary">Historial</h2>
            <div className="flex gap-2">
              {(["today", "week", "month"] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => setPeriod(p)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                    period === p
                      ? "bg-surface-dark text-text-inverse"
                      : "bg-surface-alt text-text-secondary hover:bg-surface-dark/10"
                  }`}
                >
                  {PERIOD_LABELS[p]}
                </button>
              ))}
            </div>
          </div>

          {/* KPIs rápidos */}
          {!loading && actions.length > 0 && (
            <div className="mb-3 grid grid-cols-3 gap-2">
              <Card>
                <div className="text-center">
                  <Badge variant="success" size="sm">{counts.ordered}</Badge>
                  <p className="mt-1 text-xs text-text-muted">Pedidos</p>
                </div>
              </Card>
              <Card>
                <div className="text-center">
                  <Badge variant="default" size="sm">{counts.dismissed}</Badge>
                  <p className="mt-1 text-xs text-text-muted">Descartados</p>
                </div>
              </Card>
              <Card>
                <div className="text-center">
                  <Badge variant="info" size="sm">{counts.postponed}</Badge>
                  <p className="mt-1 text-xs text-text-muted">Pospuestos</p>
                </div>
              </Card>
            </div>
          )}

          {loading && (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-20 rounded-xl" />
              ))}
            </div>
          )}

          {!loading && actions.length === 0 && (
            <Card>
              <p className="py-8 text-center text-sm text-text-muted">
                No hay acciones en este período
              </p>
            </Card>
          )}

          {!loading && actions.map((a) => {
            const badge = ACTION_BADGE[a.action_type] ?? {
              variant: "default" as const,
              label: a.action_type,
            };
            return (
              <div
                key={a.id}
                className="rounded-xl border-l-4 border-l-primary bg-surface p-4 shadow-sm"
              >
                <div className="flex items-start justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-text-muted">{a.sku}</span>
                      <Badge variant={badge.variant} size="sm">
                        {badge.label}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-text-muted">{formatDate(a.created_at)}</p>
                    {a.action_type === "ordered" && a.quantity != null && (
                      <p className="mt-1 text-sm text-text-secondary">
                        Cantidad: {a.quantity}
                        {a.supplier ? ` — ${a.supplier}` : ""}
                      </p>
                    )}
                    {a.action_type === "dismissed" && a.reason && (
                      <p className="mt-1 text-sm text-text-secondary">{a.reason}</p>
                    )}
                    {a.action_type === "postponed" && a.postponed_to && (
                      <p className="mt-1 text-sm text-text-secondary">
                        Revisar el{" "}
                        {new Date(a.postponed_to).toLocaleDateString("es-CO")}
                      </p>
                    )}
                    {a.notes && (
                      <p className="mt-1 text-xs text-text-muted italic">{a.notes}</p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </section>
      )}

      {/* Empty state — ni recomendaciones ni historial */}
      {!alertsLoading && !hasRecomendaciones && !loading && !hasHistorial && (
        <Card>
          <p className="py-8 text-center text-sm text-text-muted">
            Sin recomendaciones ni acciones registradas
          </p>
        </Card>
      )}
    </div>
  );
}
