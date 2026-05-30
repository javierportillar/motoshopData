"use client";

import { useState } from "react";
import { Card } from "@/lib/ui/Card";
import { useAlerts } from "@/lib/api/hooks";
import { StaleDataBanner } from "@/components/StaleDataBanner";
import { AlertActionModal } from "@/components/AlertActionModal";
import { registerPushSubscription } from "@/lib/push/setup";
import { useAuthStore } from "@/lib/auth/store";
import Link from "next/link";

const URGENCY_COLORS: Record<string, string> = {
  alta: "border-red-500 bg-red-50",
  media: "border-orange-400 bg-orange-50",
  baja: "border-yellow-400 bg-yellow-50",
};

const URGENCY_BADGE: Record<string, string> = {
  alta: "bg-red-500 text-white",
  media: "bg-orange-400 text-white",
  baja: "bg-yellow-400 text-yellow-900",
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
      <Link href="/dashboards" className="text-sm text-primary hover:underline">
        ← Volver a Dashboards
      </Link>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-secondary-dark">Alertas</h1>
          <p className="text-sm text-gray-500">
            {data ? `${data.total} SKU${data.total !== 1 ? "s" : ""} en riesgo` : "Cargando..."}
          </p>
        </div>

        {/* Push toggle */}
        <button
          onClick={handleEnablePush}
          disabled={pushStatus === "loading"}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
            pushStatus === "active"
              ? "bg-green-100 text-green-700"
              : "bg-primary text-white hover:bg-primary-dark"
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

      {/* Filtros de urgencia */}
      <div className="flex gap-2">
        <button
          onClick={() => setFilter(undefined)}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
            filter === undefined
              ? "bg-gray-800 text-white"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200"
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
                ? "bg-gray-800 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {URGENCY_LABEL[u]}
            {counts[u] > 0 && (
              <span className={`ml-1 rounded-full px-1.5 py-0.5 text-[10px] ${URGENCY_BADGE[u]}`}>
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
            <div key={i} className="h-24 animate-pulse rounded-xl bg-gray-100" />
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <Card>
          <p className="text-center text-sm text-red-500">
            Error al cargar alertas
          </p>
        </Card>
      )}

      {/* Lista de alertas */}
      {data && data.alerts.map((alert) => (
        <div
          key={alert.sku}
          className={`rounded-xl border-l-4 p-4 ${URGENCY_COLORS[alert.urgencia]}`}
        >
          <div className="flex items-start justify-between">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-gray-400">{alert.sku}</span>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${URGENCY_BADGE[alert.urgencia]}`}>
                  {URGENCY_LABEL[alert.urgencia]}
                </span>
              </div>
              <p className="mt-1 text-sm font-medium text-secondary-dark truncate">
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
                className="text-xs text-primary hover:underline"
              >
                Ver SKU
              </Link>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-3 gap-2">
            <div className="rounded-lg bg-white/60 px-2 py-1.5 text-center">
              <p className="text-xs text-gray-400">Stock</p>
              <p className="text-sm font-semibold text-secondary-dark">
                {alert.stock_actual.toFixed(0)}
              </p>
            </div>
            <div className="rounded-lg bg-white/60 px-2 py-1.5 text-center">
              <p className="text-xs text-gray-400">Demanda</p>
              <p className="text-sm font-semibold text-secondary-dark">
                {alert.demanda_predicha.toFixed(0)}
              </p>
            </div>
            <div className="rounded-lg bg-white/60 px-2 py-1.5 text-center">
              <p className="text-xs text-gray-400">Días rest.</p>
              <p className={`text-sm font-semibold ${alert.dias_hasta_quiebre <= 5 ? "text-red-600" : "text-secondary-dark"}`}>
                {alert.dias_hasta_quiebre}
              </p>
            </div>
          </div>
        </div>
      ))}

      {/* Empty state */}
      {data && data.alerts.length === 0 && (
        <Card>
          <p className="py-8 text-center text-sm text-gray-400">
            No hay alertas de quiebre
          </p>
        </Card>
      )}

      {/* Push error feedback */}
      {pushStatus === "error" && (
        <p className="text-center text-xs text-red-500">
          No se pudieron activar las notificaciones. Probá desde otro navegador.
        </p>
      )}

      {/* Modal de gestión */}
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
