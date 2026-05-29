"use client";

import { Card } from "@/lib/ui/Card";
import { KpiCard } from "@/components/KpiCard";
import { SalesTrendChart } from "@/components/SalesTrendChart";
import { TopList } from "@/components/TopList";
import { useSalesSummary } from "@/lib/api/hooks";
import Link from "next/link";

function formatMoney(v: number): string {
  return `$${(v / 1_000_000).toFixed(1)}M`;
}

export default function VentasPage(): JSX.Element {
  const { data, error, isLoading } = useSalesSummary();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-5 w-24 animate-pulse rounded bg-gray-200" />
        <div className="h-40 animate-pulse rounded-xl bg-gray-100" />
        <div className="h-60 animate-pulse rounded-xl bg-gray-100" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-4">
        <Link href="/dashboards" className="text-sm text-primary hover:underline">
          ← Volver a Dashboards
        </Link>
        <Card>
          <p className="text-center text-gray-500">Error al cargar datos de ventas</p>
        </Card>
      </div>
    );
  }

  // Top 5 SKUs como datos de tendencia real desde la API
  const trendData = data.top_skus.slice(0, 5).map((sku, i) => ({
    label: sku.nom_producto.substring(0, 12),
    valor: sku.valor_total,
  }));

  return (
    <div className="space-y-4">
      <Link href="/dashboards" className="text-sm text-primary hover:underline">
        ← Volver a Dashboards
      </Link>

      <h1 className="text-xl font-bold text-secondary-dark">Ventas</h1>
      <p className="text-sm text-gray-500">Período: {data.business_month}</p>

      <div className="grid grid-cols-2 gap-3">
        <KpiCard
          title="Ventas del Mes"
          value={formatMoney(data.ventas_mes_actual)}
          delta={data.delta_porcentual}
          deltaLabel="vs anterior"
        />
        <KpiCard
          title="Ticket Promedio"
          value={formatMoney(data.ticket_promedio)}
          subtitle={`${data.num_facturas} facturas`}
        />
      </div>

      <Card header={<h2 className="font-semibold text-secondary-dark">Tendencia Mensual</h2>}>
        <SalesTrendChart data={trendData} />
      </Card>

      <Card header={<h2 className="font-semibold text-secondary-dark">Top 10 SKUs</h2>}>
        <TopList
          items={data.top_skus.map((sku, i) => ({
            rank: i + 1,
            label: sku.nom_producto,
            value: sku.valor_total,
            secondary: `${sku.cantidad_total} unidades`,
          }))}
        />
      </Card>
    </div>
  );
}
