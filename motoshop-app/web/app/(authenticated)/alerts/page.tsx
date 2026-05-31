"use client";

import { useState } from "react";
import Link from "next/link";
import { useAlerts } from "@/lib/api/hooks";
import { useAuthStore } from "@/lib/auth/store";
import { Card } from "@/components/ui/Card";
import { Badge, AlertBadge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { StaleDataBanner } from "@/components/StaleDataBanner";
import { AlertActionModal } from "@/components/AlertActionModal";
import { registerPushSubscription } from "@/lib/push/setup";

const URGENCY_BG: Record<string, string> = {
  alta: "border-l-error bg-error/5",
  media: "border-l-warning bg-warning/5",
  baja: "border-l-warning bg-warning/5",
};

const URGENCY_LABEL: Record<string, string> = {
  alta: "Alta",
  media: "Media",
  baja: "Baja",
};

export default function AlertsPage(): JSX.Element {
  const [filter, setFilter] = useState<string | undefined>(undefined);
  const [pushStatus, setPushStatus] = useState<"idle" | "loading" | "active" | "error">("idle");
  const [manageSku, setManageSku] = useState<string | null>(null);

  const role = useAuthStore((s) => s.role);
  const canManage = role === "admin" || role === "gerente";

  const { data, error, isLoading, mutate } = useAlerts(filter);

  async function handleEnablePush() {
    setPushStatus("loading");
    const ok = await registerPushSubscription();
    setPushStatus(ok ? "active" : "error");
    if (ok) setTimeout(() => setPushStatus("idle"), 5000);
  }

  const counts = data
    ? {
        alta: data.alerts.filter((a) => a.urgencia === "alta").length,
        media: data.alerts.filter((a) => a.urgencia === "media").length,
        baja: data.alerts.filter((a) => a.urgencia === "baja").length,
      }
    : { alta: 0, media: 0, baja: 0 };

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">
        ← Volver a inicio
      </Link>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Alertas</h1>
          <p className="text-sm text-text-muted">
            {data ? `${data.total} SKU${data.total !== 1 ? "s" : ""} en riesgo` : "Cargando..."}
          </p>
        </div>

        <button
          onClick={handleEnablePush}
          disabled={pushStatus === "loading"}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
            pushStatus === "active"
              ? "bg-success/10 text-success"
              : "bg-primary text-primary-fg hover:bg-primary-light"
          }`}
        >
          {pushStatus === "loading"
            ? "Configurando..."
            : pushStatus === "active"
              ? "Push activo ✓"
              : "Activar push"}
        </button>
      </div>

      <StaleDataBanner />

      {/* Filtros */}
      <div className="flex gap-2">
        <button
          onClick={() => setFilter(undefined)}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
            filter === undefined
              ? "bg-surface-dark text-text-inverse"
              : "bg-surface-alt text-text-secondary hover:bg-surface-dark/10"
          }`}
        >
          Todas {data ? `(${data.total})` : ""}
        </button>
        {(["alta", "media", "baja"] as const).map((u) => (
          <button
            key={u}
            onClick={() => setFilter(u)}
            className={`flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium ${
              filter === u
                ? "bg-surface-dark text-text-inverse"
                : "bg-surface-alt text-text-secondary hover:bg-surface-dark/10"
            }`}
          >
            {URGENCY_LABEL[u]}
            {counts[u] > 0 && (
              <span className="ml-1 rounded-full bg-error px-1.5 py-0.5 text-[10px] text-error-fg">
                {counts[u]}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <Card>
          <p className="py-8 text-center text-sm text-error">
            Error al cargar alertas
          </p>
        </Card>
      )}

      {/* Lista de alertas */}
      {data?.alerts.map((alert) => (
        <div
          key={alert.sku}
          className={`rounded-xl border-l-4 bg-surface p-4 shadow-sm ${URGENCY_BG[alert.urgencia]}`}
        >
          <div className="flex items-start justify-between">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-text-muted">{alert.sku}</span>
                <AlertBadge
                  severity={
                    alert.urgencia === "alta"
                      ? "critical"
                      : alert.urgencia === "media"
                        ? "warning"
                        : "info"
                  }
                />
              </div>
              <p className="mt-1 text-sm font-medium text-text-primary truncate">
                {alert.nom_producto}
              </p>
            </div>
            <div className="ml-2 flex shrink-0 items-center gap-2">
              {canManage && (
                <button
                  onClick={() => setManageSku(alert.sku)}
                  className="text-xs font-medium text-primary hover:underline"
                >
                  Gestionar
                </button>
              )}
              <Link
                href={`/products/${alert.sku}`}
                className="text-xs text-accent hover:underline"
              >
                Ver SKU
              </Link>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-3 gap-2">
            <div className="rounded-lg bg-surface-alt px-2 py-1.5 text-center">
              <p className="text-xs text-text-muted">Stock</p>
              <p className="text-sm font-semibold text-text-primary">
                {alert.stock_actual.toFixed(0)}
              </p>
            </div>
            <div className="rounded-lg bg-surface-alt px-2 py-1.5 text-center">
              <p className="text-xs text-text-muted">Demanda</p>
              <p className="text-sm font-semibold text-text-primary">
                {alert.demanda_predicha.toFixed(0)}
              </p>
            </div>
            <div className="rounded-lg bg-surface-alt px-2 py-1.5 text-center">
              <p className="text-xs text-text-muted">Días rest.</p>
              <p
                className={`text-sm font-semibold ${
                  alert.dias_hasta_quiebre <= 5 ? "text-error" : "text-text-primary"
                }`}
              >
                {alert.dias_hasta_quiebre}
              </p>
            </div>
          </div>
        </div>
      ))}

      {/* Empty state */}
      {data && data.alerts.length === 0 && (
        <Card>
          <p className="py-8 text-center text-sm text-text-muted">
            No hay alertas de quiebre
          </p>
        </Card>
      )}

      {pushStatus === "error" && (
        <p className="text-center text-xs text-error">
          No se pudieron activar las notificaciones. Probá desde otro navegador.
        </p>
      )}

      {manageSku && (
        <AlertActionModal
          sku={manageSku}
          nomProducto={data?.alerts.find((a) => a.sku === manageSku)?.nom_producto ?? ""}
          onClose={() => setManageSku(null)}
          onSuccess={() => {
            setManageSku(null);
            mutate();
          }}
        />
      )}
    </div>
  );
}
