"use client";

import { Card } from "@/lib/ui/Card";
import { KpiCard } from "@/components/KpiCard";
import { AbcChart } from "@/components/AbcChart";
import { TopList } from "@/components/TopList";
import { useAbcSegmentation, useDormidos } from "@/lib/api/hooks";
import Link from "next/link";
import { formatMoney } from "@/lib/format/currency";

export default function AbcPage(): JSX.Element {
  const abc = useAbcSegmentation();
  const dormidos = useDormidos();
  const isLoading = abc.isLoading || dormidos.isLoading;

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-5 w-24 animate-pulse rounded bg-gray-200" />
        <div className="h-40 animate-pulse rounded-xl bg-gray-100" />
        <div className="h-60 animate-pulse rounded-xl bg-gray-100" />
      </div>
    );
  }

  if (abc.error) {
    return (
      <div className="space-y-4">
        <Link href="/dashboards" className="text-sm text-primary hover:underline">
          ← Volver a Dashboards
        </Link>
        <Card>
          <p className="text-center text-gray-500">Error al cargar datos ABC</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Link href="/dashboards" className="text-sm text-primary hover:underline">
        ← Volver a Dashboards
      </Link>

      <h1 className="text-xl font-bold text-secondary-dark">
        Segmentación ABC
      </h1>
      <p className="text-sm text-gray-500">
        {abc.data?.business_month ?? ""} — {abc.data?.total_skus ?? "—"} SKUs
      </p>

      <div className="grid grid-cols-3 gap-2">
        <KpiCard
          title="A"
          value={`${abc.data?.bucket_a.num_skus ?? "—"}`}
          subtitle={`${abc.data?.bucket_a.porcentaje_ingreso ?? 0}% ingresos`}
        />
        <KpiCard
          title="B"
          value={`${abc.data?.bucket_b.num_skus ?? "—"}`}
          subtitle={`${abc.data?.bucket_b.porcentaje_ingreso ?? 0}% ingresos`}
        />
        <KpiCard
          title="C"
          value={`${abc.data?.bucket_c.num_skus ?? "—"}`}
          subtitle={`${abc.data?.bucket_c.porcentaje_ingreso ?? 0}% ingresos`}
        />
      </div>

      {abc.data && (
        <Card header={<h2 className="font-semibold text-secondary-dark">Distribución ABC</h2>}>
          <AbcChart
            bucketA={abc.data.bucket_a}
            bucketB={abc.data.bucket_b}
            bucketC={abc.data.bucket_c}
          />
        </Card>
      )}

      {dormidos.data && dormidos.data.productos.length > 0 && (
        <Card header={<h2 className="font-semibold text-secondary-dark">Productos Dormidos (&gt; 90 días)</h2>}>
          <TopList
            items={dormidos.data.productos.map((p, i) => ({
              rank: i + 1,
              label: p.nom_producto,
              value: p.dias_sin_venta,
              secondary: p.stock_actual ? `Stock: ${p.stock_actual}` : undefined,
            }))}
            formatValue={(v) => `${v} días`}
          />
        </Card>
      )}

      {abc.data && (
        <Card header={<h2 className="font-semibold text-secondary-dark">Resumen por Categoría</h2>}>
          <div className="space-y-2">
            {[abc.data.bucket_a, abc.data.bucket_b, abc.data.bucket_c].map((b) => (
              <div
                key={b.categoria}
                className="flex items-center justify-between rounded-lg bg-gray-50 p-3"
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`flex h-8 w-8 items-center justify-center rounded-lg text-sm font-bold text-white ${
                      b.categoria === "A"
                        ? "bg-primary"
                        : b.categoria === "B"
                          ? "bg-amber-600"
                          : "bg-gray-400"
                    }`}
                  >
                    {b.categoria}
                  </span>
                  <div>
                    <p className="text-sm font-medium text-secondary-dark">
                      {b.num_skus} SKUs
                    </p>
                    <p className="text-xs text-gray-400">
                      {b.porcentaje_ingreso}% de ingresos
                    </p>
                  </div>
                </div>
                <span className="text-sm font-semibold text-secondary">
                  {formatMoney(b.valor_total)}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
