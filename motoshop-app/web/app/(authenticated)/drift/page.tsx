"use client";

import Link from "next/link";
import { useDriftSummary } from "@/lib/api/hooks";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Table } from "@/components/ui/Table";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";

const METRIC_DESCRIPTIONS: Record<string, string> = {
  "WAPE baseline": "Error de predicción del modelo — mide qué tan precisas son las predicciones vs. la demanda real",
  "Ventas diarias": "Volumen de ventas promedio por día — permite detectar cambios en la demanda",
  "Cobertura forecast": "% de SKUs con predicción válida — indica qué tan completo es el modelo de forecast",
  "Tasa recurrencia": "% de clientes que recompran — mide la fidelidad y retención de clientes",
};

export default function DriftPage(): JSX.Element {
  const { data, error, isLoading } = useDriftSummary();

  // ── Loading ──────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-accent hover:underline">
          ← Volver a inicio
        </Link>
        <Skeleton className="h-5 w-24" />
        <div className="grid grid-cols-3 gap-3">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-80 rounded-xl" />
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

      {/* Explicación de drift */}
      <Card>
        <h3 className="mb-2 text-sm font-semibold text-text-primary">¿Qué es el monitoreo de drift?</h3>
        <p className="mb-3 text-xs leading-relaxed text-text-secondary">
          Drift es la <strong>desviación de métricas clave</strong> respecto a su valor histórico.
          El monitoreo continuo permite detectar cambios inesperados en los patrones de ventas,
          calidad de predicciones y comportamiento de clientes.
        </p>
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="rounded-lg bg-surface-alt p-2.5">
            <span className="font-medium text-text-primary">Estados</span>
            <ul className="mt-1 space-y-1.5 text-text-secondary">
              <li className="flex items-center gap-1.5">
                <Badge variant="error" size="sm">Activo</Badge>
                Métrica fuera de rango, requiere atención
              </li>
              <li className="flex items-center gap-1.5">
                <Badge variant="warning" size="sm">Alerta</Badge>
                Métrica en observación, cerca del umbral
              </li>
              <li className="flex items-center gap-1.5">
                <Badge variant="success" size="sm">Resuelto</Badge>
                Métrica volvió a rango normal
              </li>
            </ul>
          </div>
          <div className="rounded-lg bg-surface-alt p-2.5">
            <span className="font-medium text-text-primary">Métricas monitoreadas</span>
            <ul className="mt-1 space-y-1 text-text-secondary">
              <li><strong>WAPE baseline</strong> — Error de predicción del modelo</li>
              <li><strong>Ventas diarias</strong> — Volumen de ventas promedio</li>
              <li><strong>Cobertura forecast</strong> — % de SKUs con predicción válida</li>
              <li><strong>Tasa recurrencia</strong> — % de clientes que recompran</li>
            </ul>
          </div>
        </div>
      </Card>

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
                cell: (d) => (
                  <span
                    className="cursor-help font-medium underline decoration-dotted decoration-text-muted/40 underline-offset-2"
                    title={METRIC_DESCRIPTIONS[d.metric_name] ?? d.metric_name}
                  >
                    {d.metric_name}
                  </span>
                ),
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
