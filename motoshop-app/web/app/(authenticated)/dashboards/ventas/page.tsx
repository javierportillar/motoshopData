"use client";

import Link from "next/link";
import { useSalesSummary, useSalesTrend } from "@/lib/api/hooks";
import { formatMoney } from "@/lib/format/currency";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Badge } from "@/components/ui/Badge";
import { Table } from "@/components/ui/Table";
import { SalesTrendChart } from "@/components/SalesTrendChart";

const MONTH_NAMES = [
  "Ene", "Feb", "Mar", "Abr", "May", "Jun",
  "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
];

export default function VentasPage(): JSX.Element {
  const sales = useSalesSummary();
  const trend = useSalesTrend(9);

  const isLoading = sales.isLoading || trend.isLoading;

  // ── Loading ──────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-accent hover:underline">
          ← Volver a inicio
        </Link>
        <div className="h-5 w-24 animate-pulse rounded bg-surface-alt" />
        <div className="grid grid-cols-2 gap-3">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-surface-alt" />
          ))}
        </div>
        <div className="h-60 animate-pulse rounded-xl bg-surface-alt" />
        <div className="h-60 animate-pulse rounded-xl bg-surface-alt" />
      </div>
    );
  }

  // ── Error ────────────────────────────────────────────────────

  if (sales.error || !sales.data) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-accent hover:underline">
          ← Volver a inicio
        </Link>
        <Card>
          <p className="py-8 text-center text-text-muted">
            Error al cargar datos de ventas
          </p>
        </Card>
      </div>
    );
  }

  const d = sales.data;

  // ── Datos de tendencia real ──────────────────────────────────

  const trendData = trend.data?.items.map((item) => ({
    label: `${MONTH_NAMES[item.month - 1]} ${item.year.toString().slice(2)}`,
    valor: item.total_ventas,
  })) ?? [];

  // ── Render ───────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">
        ← Volver a inicio
      </Link>

      <div>
        <h1 className="text-xl font-bold text-text-primary">Ventas</h1>
        <p className="text-sm text-text-muted">
          Período: {d.business_month}
        </p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 gap-3">
        <Card>
          <Stat
            label="Ventas del mes"
            value={formatMoney(d.ventas_mes_actual)}
            delta={d.delta_porcentual}
            deltaLabel="vs mes anterior"
          />
        </Card>
        <Card>
          <Stat
            label="Ticket promedio"
            value={formatMoney(d.ticket_promedio)}
            subtitle={`${d.num_facturas} facturas`}
          />
        </Card>
      </div>

      {/* Tendencia mensual REAL */}
      {trendData.length > 0 ? (
        <Card header={<h2 className="font-semibold text-text-primary">Tendencia mensual</h2>}>
          <SalesTrendChart data={trendData} />
          {trend.data && (
            <p className="mt-2 text-center text-xs text-text-muted">
              Últimos {trend.data.periods} meses
            </p>
          )}
        </Card>
      ) : (
        <Card>
          <p className="py-8 text-center text-sm text-text-muted">
            Sin datos de tendencia aún
          </p>
        </Card>
      )}

      {/* Top 10 SKUs */}
      {d.top_skus.length > 0 && (
        <Card header={<h2 className="font-semibold text-text-primary">Top 10 SKUs del mes</h2>}>
          <Table
            columns={[
              { header: "#", cell: (_, i) => i + 1, align: "center", className: "w-10" },
              {
                header: "Producto",
                cell: (sku) => (
                  <div>
                    <p className="text-sm font-medium">{sku.nom_producto}</p>
                    <p className="font-mono text-xs text-text-muted">
                      {sku.cod_producto}
                    </p>
                  </div>
                ),
              },
              {
                header: "Cantidad",
                cell: (sku) => sku.cantidad_total.toLocaleString("es-CO"),
                align: "right",
              },
              {
                header: "Valor",
                cell: (sku) => formatMoney(sku.valor_total),
                align: "right",
              },
            ]}
            data={d.top_skus}
            keyFn={(sku) => sku.cod_producto}
            striped
          />
        </Card>
      )}
    </div>
  );
}
