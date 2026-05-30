"use client";

import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Table } from "@/components/ui/Table";
import { Badge } from "@/components/ui/Badge";

// ── Mock data (reemplazar cuando Dev A2 cree /metrics/drift-summary) ──

interface DriftItem {
  metric_name: string;
  detected_at: string;
  drift_magnitude: number;
  threshold: number;
  status: "active" | "resolved" | "warning";
  recommended_action: string;
}

const MOCK_DRIFT: DriftItem[] = [
  {
    metric_name: "WAPE baseline",
    detected_at: "2026-05-28",
    drift_magnitude: 3.2,
    threshold: 5.0,
    status: "warning",
    recommended_action: "Monitorear. Si supera 5%, re-entrenar baseline la próxima semana.",
  },
  {
    metric_name: "Ventas diarias promedio",
    detected_at: "2026-05-25",
    drift_magnitude: 8.7,
    threshold: 5.0,
    status: "active",
    recommended_action: "Revisar datos de ingesta. Verificar si es real (fin de mes) o error de pipeline.",
  },
  {
    metric_name: "Mix de categorías",
    detected_at: "2026-05-15",
    drift_magnitude: 2.1,
    threshold: 5.0,
    status: "resolved",
    recommended_action: "Normalizado. El drift fue temporal (promoción fin de semana).",
  },
];

// ── Page ───────────────────────────────────────────────────────

export default function DriftPage(): JSX.Element {
  // TODO: reemplazar por useDrift() cuando Dev A2 cree el endpoint
  const data = MOCK_DRIFT;

  const activeCount = data.filter((d) => d.status === "active").length;
  const warningCount = data.filter((d) => d.status === "warning").length;

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">
        ← Volver a inicio
      </Link>

      <div>
        <h1 className="text-xl font-bold text-text-primary">Alertas de drift</h1>
        <p className="text-sm text-text-muted">
          Monitoreo de desviaciones en métricas clave — datos de muestra
        </p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-3 gap-3">
        <Card>
          <Stat
            label="Alertas activas"
            value={String(activeCount)}
            subtitle="requieren acción"
          />
        </Card>
        <Card>
          <Stat
            label="Warnings"
            value={String(warningCount)}
            subtitle="en observación"
          />
        </Card>
        <Card>
          <Stat
            label="Threshold"
            value="5.0%"
            subtitle="umbral de drift"
          />
        </Card>
      </div>

      {/* Tabla de drift */}
      <Card header={<h2 className="font-semibold text-text-primary">Historial de drift</h2>}>
        <div className="overflow-x-auto">
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
            data={data}
            keyFn={(d, i) => `${d.metric_name}-${d.detected_at}-${i}`}
            striped
          />
        </div>
      </Card>

      <p className="text-center text-xs text-text-muted">
        Datos de muestra — endpoint real en desarrollo por Dev A2
      </p>
    </div>
  );
}
