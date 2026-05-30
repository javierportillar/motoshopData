"use client";

import Link from "next/link";
import { useCohortes } from "@/lib/api/hooks";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Table } from "@/components/ui/Table";
import { Badge } from "@/components/ui/Badge";
import { formatMoney } from "@/lib/format/currency";

export default function CohortesPage(): JSX.Element {
  const { data, error, isLoading } = useCohortes();

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
            Error al cargar datos de cohortes
          </p>
        </Card>
      </div>
    );
  }

  // ── Agregados ────────────────────────────────────────────────

  const totalClientes = new Set(data.cohortes.map((c) => c.cohorte_mes)).size;
  const cohortesConRecurrencia = data.cohortes.filter((c) => c.tasa_recurrencia != null);
  const avgLtv =
    cohortesConRecurrencia.length > 0
      ? cohortesConRecurrencia.reduce((sum, c) => sum + c.ticket_promedio, 0) /
        cohortesConRecurrencia.length
      : 0;

  // ── Render ───────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">
        ← Volver a inicio
      </Link>

      <div>
        <h1 className="text-xl font-bold text-text-primary">Cohortes de clientes</h1>
        <p className="text-sm text-text-muted">
          Retención y valor por mes de primera compra
        </p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-3 gap-3">
        <Card>
          <Stat
            label="Cohortes"
            value={String(totalClientes)}
            subtitle="meses con primera compra"
          />
        </Card>
        <Card>
          <Stat
            label="Ticket prom. LTV"
            value={formatMoney(avgLtv)}
            subtitle="promedio cohortes con recurrencia"
          />
        </Card>
        <Card>
          <Stat
            label="Total clientes"
            value={String(data.cohortes.length)}
            subtitle="observaciones"
          />
        </Card>
      </div>

      {/* Tabla de cohortes */}
      <Card header={<h2 className="font-semibold text-text-primary">Desglose por cohorte</h2>}>
        <div className="overflow-x-auto">
          <Table
            columns={[
              {
                header: "Cohorte",
                cell: (c) => (
                  <span className="font-medium">{c.cohorte_mes}</span>
                ),
              },
              {
                header: "Mes obs.",
                cell: (c) => c.mes_observacion,
              },
              {
                header: "Clientes",
                cell: (c) => c.num_clientes,
                align: "right",
              },
              {
                header: "Ticket prom.",
                cell: (c) => formatMoney(c.ticket_promedio),
                align: "right",
              },
              {
                header: "Recurrencia",
                cell: (c) =>
                  c.tasa_recurrencia != null ? (
                    <Badge
                      variant={c.tasa_recurrencia > 0.5 ? "success" : "warning"}
                      size="sm"
                    >
                      {(c.tasa_recurrencia * 100).toFixed(0)}%
                    </Badge>
                  ) : (
                    <span className="text-text-muted">—</span>
                  ),
                align: "center",
              },
            ]}
            data={data.cohortes}
            keyFn={(c, i) => `${c.cohorte_mes}-${c.mes_observacion}-${i}`}
            striped
          />
        </div>
      </Card>
    </div>
  );
}
