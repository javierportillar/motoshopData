"use client";

import { Card } from "@/lib/ui/Card";
import { KpiCard } from "@/components/KpiCard";
import { InventoryByBodega } from "@/components/InventoryByBodega";
import { useInventorySummary } from "@/lib/api/hooks";
import Link from "next/link";
import { formatMoney } from "@/lib/format/currency";

function formatNumber(v: number): string {
  return v.toLocaleString("es-CO");
}

export default function InventarioPage(): JSX.Element {
  const { data, error, isLoading } = useInventorySummary();

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
          <p className="text-center text-gray-500">Error al cargar datos de inventario</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Link href="/dashboards" className="text-sm text-primary hover:underline">
        ← Volver a Dashboards
      </Link>

      <h1 className="text-xl font-bold text-secondary-dark">Inventario</h1>
      <p className="text-sm text-gray-500">{data.num_productos} productos en total</p>

      <div className="grid grid-cols-2 gap-3">
        <KpiCard
          title="Stock Total"
          value={formatNumber(data.stock_total)}
          subtitle="unidades"
        />
        <KpiCard
          title="Valor Estimado"
          value={formatMoney(data.valor_total)}
          subtitle="costo total"
        />
      </div>

      <Card header={<h2 className="font-semibold text-secondary-dark">Stock por Bodega</h2>}>
        <InventoryByBodega data={data.por_bodega} />
      </Card>

      <Card header={<h2 className="font-semibold text-secondary-dark">Detalle por Bodega</h2>}>
        <div className="space-y-2">
          {data.por_bodega.map((b) => (
            <div
              key={b.cod_bodega}
              className="flex items-center justify-between rounded-lg bg-gray-50 p-3"
            >
              <div>
                <p className="text-sm font-medium text-secondary-dark">
                  {b.nom_bodega}
                </p>
                <p className="text-xs text-gray-400">{b.cod_bodega}</p>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold text-secondary">
                  {formatNumber(b.cantidad)}
                </p>
                <p className="text-xs text-gray-400">{b.porcentaje}%</p>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
