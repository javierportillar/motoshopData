"use client";

import Link from "next/link";
import { useDriftSummary } from "@/lib/api/hooks";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Table } from "@/components/ui/Table";
import { Badge } from "@/components/ui/Badge";

export default function DriftPage(): JSX.Element {
  const { data, error, isLoading } = useDriftSummary();

  // ── Loading ──────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-accent hover:underline">
          ← Volver a inicio
        </Link>
        <div className="h-5 w-24 animate-pulse rounded bg-surface-alt" />
        <div className="grid grid-cols-3 gap-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-surface-alt" />
          ))}
        </div>
        <div className="h-80 animate-pulse rounded-xl bg-surface-alt" />
      </div>
    );
  }

  // ── Error ────────────────────────────────────────────────────

  if (error || !data) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-accent hover:underline">
          ← Volver a inicio
        </Link>
        <Card>
          <p className="py-8 text-center text-sm text-text-muted">
            Error al cargar datos de drift
          </p>
        </Card>
      </div>
    );
  }

  // ── Render ───────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">
        ← Volver a inicio
      </Link>

      <div>
        <h1 className="text-xl font-bold text-text-primary">Alertas de drift</h1>
        <p className="text-sm text-text-muted">
          Monitoreo de desviaciones en métricas clave
        </p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-3 gap-3">
        <Card>
          <Stat
            label="Activas"
            value={String(data.active_count)}
            subtitle="requieren acción"
          />
        </Card>
        <Card>
          <Stat
            label="Warnings"
            value={String(data.warning_count)}
            subtitle="en observación"
          />
        </Card>
        <Card>
          <Stat
            label="Threshold"
            value={`${data.current_threshold}%`}
            subtitle="umbral de drift"
          />
        </Card>
      </div>

      {/* Tabla de drift */}
      {data.items.length > 0 ? (
        <Card header={<h2 className="font-semibold text-text-primary">Historial de drift</h2>}>
          <Table
            columns={[
              {
                header: "Métrica",
                cell: (d) => <span className="font-medium">{d.metric_name}</span>,
              },
              {
                header: "Detectado",
                cell: (d) => d.detected_at,
              },
              {
                header: "Drift",
                cell: (d) => (
                  <Badge
                    variant={d.drift_magnitude > d.threshold ? "error" : "warning"}
                    size="md"
                  >
                    {d.drift_magnitude}%
                  </Badge>
                ),
                align: "center",
              },
              {
                header: "Estado",
                cell: (d) => (
                  <Badge
                    variant={
                      d.status === "active"
                        ? "error"
                        : d.status === "warning"
                          ? "warning"
                          : "success"
                    }
                    size="sm"
                  >
                    {d.status === "active"
                      ? "Activo"
                      : d.status === "warning"
                        ? "Alerta"
                        : "Resuelto"}
                  </Badge>
                ),
                align: "center",
              },
              {
                header: "Acción recomendada",
                cell: (d) => (
                  <p className="max-w-xs text-xs text-text-secondary">
                    {d.recommended_action}
                  </p>
                ),
              },
            ]}
            data={data.items}
            keyFn={(d, i) => `${d.metric_name}-${d.detected_at}-${i}`}
            striped
          />
        </Card>
      ) : (
        <Card>
          <p className="py-8 text-center text-sm text-text-muted">
            No se detectaron desviaciones
          </p>
        </Card>
      )}
    </div>
  );
}
