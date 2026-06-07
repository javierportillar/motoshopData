"use client";

import Link from "next/link";
import { useCohortes, useCohortesDetail } from "@/lib/api/hooks";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Table } from "@/components/ui/Table";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatMoney } from "@/lib/format/currency";

export default function CohortesPage(): JSX.Element {
  const { data, error, isLoading } = useCohortes();
  const detail = useCohortesDetail();

  const isLoadingBoth = isLoading || detail.isLoading;

  // ── Loading ──────────────────────────────────────────────────

  if (isLoadingBoth) {
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

      {/* F7-FIX1 bug 6.4 + 4.6: explicación pedagógica del componente */}
      <Card>
        <details className="text-sm">
          <summary className="cursor-pointer font-medium text-text-primary">
            ¿Qué es una cohorte y cómo leer este reporte?
          </summary>
          <div className="mt-3 space-y-2 text-text-secondary">
            <p>
              <strong>Cohorte</strong> = grupo de clientes que hicieron su primera compra en el mismo mes.
              Cada fila muestra una cohorte y cómo se comportó en los meses siguientes.
            </p>
            <p>
              <strong>Mes obs.</strong> = el mes en el que observamos a esa cohorte.
              Si la cohorte 2024-01 tiene fila con mes obs. 2024-05, significa que estamos viendo si esos
              clientes de enero volvieron en mayo.
            </p>
            <p>
              <strong>Recurrencia</strong> = porcentaje de clientes de la cohorte que volvieron a comprar
              ese mes. 100% = todos volvieron. 0% = ninguno volvió ese mes.
            </p>
            <p className="text-xs text-text-muted">
              Nota honesta: cohortes con menos de 5 clientes tienen significancia estadística baja.
              Esto refleja el tamaño actual del dataset, no es un error.
            </p>
          </div>
        </details>
      </Card>

      {/* KPIs */}
      <div className="grid grid-cols-3 gap-3 md:grid-cols-5">
        <Card>
          <Stat
            label="Cohortes"
            value={detail.data ? String(detail.data.total_cohortes) : String(totalClientes)}
            subtitle="meses con primera compra"
          />
        </Card>
        <Card>
          <Stat
            label="Nuevos"
            value={detail.data ? String(detail.data.nuevos_este_mes) : "—"}
            subtitle="clientes este mes"
          />
        </Card>
        <Card>
          <Stat
            label="Recurrentes"
            value={detail.data ? String(detail.data.recurrentes_este_mes) : "—"}
            subtitle="compraron otra vez"
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
            label="Top recurrentes"
            value={detail.data ? String(detail.data.top_recurrentes) : "—"}
            subtitle="máximos compradores"
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
                cell: (c) => (
                  <span className="inline-flex items-center gap-1">
                    {c.num_clientes}
                    {c.muestra_pequena && (
                      <span title="Muestra pequeña (<5 clientes). Significancia baja." className="text-xs text-text-muted">
                        ⚠
                      </span>
                    )}
                  </span>
                ),
                align: "right",
              },
              {
                header: "Ticket prom.",
                cell: (c) => c.num_clientes === 0
                  ? <span className="text-text-muted">—</span>
                  : formatMoney(c.ticket_promedio),
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
