"use client";

import { Card } from "@/lib/ui/Card";
import { KpiCard } from "@/components/KpiCard";
import { useDormidos } from "@/lib/api/hooks";
import Link from "next/link";

function dormancyColor(dias: number): string {
  if (dias > 180) return "text-red-600 bg-red-50";
  if (dias >= 90) return "text-orange-600 bg-orange-50";
  return "text-gray-600 bg-gray-100";
}

function formatNumber(v: number): string {
  return v.toLocaleString("es-CO");
}

export default function DormidosPage(): JSX.Element {
  const { data, error, isLoading } = useDormidos();

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
          <p className="text-center text-gray-500">Error al cargar datos de productos dormidos</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Link href="/dashboards" className="text-sm text-primary hover:underline">
        ← Volver a Dashboards
      </Link>

      <h1 className="text-xl font-bold text-secondary-dark">Productos Dormidos</h1>
      <p className="text-sm text-gray-500">
        {data.total > 0
          ? `${data.total} producto${data.total !== 1 ? "s" : ""} sin venta en los últimos 90 días o más`
          : "Sin productos dormidos"}
      </p>

      <div className="grid grid-cols-2 gap-3">
        <KpiCard
          title="Total Dormidos"
          value={String(data.total)}
          subtitle="> 90 días sin venta"
        />
        <KpiCard
          title="Críticos"
          value={String(data.productos.filter((p) => p.dias_sin_venta > 180).length)}
          subtitle="> 180 días sin venta"
        />
      </div>

      <Card header={<h2 className="font-semibold text-secondary-dark">Lista de Dormidos</h2>}>
        <div className="space-y-2">
          {data.productos.length === 0 && (
            <p className="py-4 text-center text-sm text-gray-400">
              No hay productos dormidos en este período
            </p>
          )}
          {data.productos.map((p) => (
            <div
              key={p.cod_producto}
              className="flex items-center justify-between rounded-lg bg-gray-50 p-3"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-secondary-dark">
                  {p.nom_producto}
                </p>
                <p className="text-xs text-gray-400">{p.cod_producto}</p>
              </div>
              <div className="ml-2 shrink-0 text-right">
                <span
                  className={`inline-block rounded-full px-2.5 py-1 text-xs font-medium ${dormancyColor(p.dias_sin_venta)}`}
                >
                  {p.dias_sin_venta}d
                </span>
                {p.stock_actual != null && (
                  <p className="mt-1 text-xs text-gray-400">
                    Stock: {formatNumber(p.stock_actual)}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
