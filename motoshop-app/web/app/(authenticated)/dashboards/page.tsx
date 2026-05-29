"use client";

import { KpiGrid } from "@/components/KpiGrid";
import { KpiCard } from "@/components/KpiCard";
import { useSalesSummary, useInventorySummary, useAbcSegmentation, useDormidos } from "@/lib/api/hooks";

function formatMoney(v: number): string {
  return `$${(v / 1_000_000).toFixed(1)}M`;
}

function formatNumber(v: number): string {
  return v.toLocaleString("es-CO");
}

function SkeletonCard(): JSX.Element {
  return (
    <div className="animate-pulse space-y-3 rounded-xl border border-gray-200 p-4">
      <div className="h-3 w-20 rounded bg-gray-200" />
      <div className="h-7 w-32 rounded bg-gray-200" />
      <div className="h-3 w-24 rounded bg-gray-200" />
    </div>
  );
}

export default function DashboardsPage(): JSX.Element {
  const sales = useSalesSummary();
  const inventory = useInventorySummary();
  const abc = useAbcSegmentation();
  const dormidos = useDormidos();

  const loading = sales.isLoading || inventory.isLoading || abc.isLoading;
  const errors = [sales.error, inventory.error, abc.error, dormidos.error].filter(Boolean);
  if (errors.length > 0) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-bold text-secondary-dark">Dashboards</h1>
          <p className="text-sm text-gray-500">Indicadores del negocio</p>
        </div>
        <div className="rounded-xl border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-medium text-red-800">
            Error al cargar indicadores. Intentá de nuevo más tarde.
          </p>
          <p className="mt-1 text-xs text-red-600">
            {errors[0]?.message ?? "Error desconocido"}
          </p>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-bold text-secondary-dark">Dashboards</h1>
          <p className="text-sm text-gray-500">Indicadores del negocio</p>
        </div>
        <KpiGrid>
          {[...Array(6)].map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </KpiGrid>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-secondary-dark">Dashboards</h1>
        <p className="text-sm text-gray-500">
          {sales.data?.business_month
            ? `Indicadores - ${sales.data.business_month}`
            : "Indicadores del negocio"}
        </p>
      </div>

      <KpiGrid>
        <KpiCard
          title="Ventas del Mes"
          value={sales.data ? formatMoney(sales.data.ventas_mes_actual) : "—"}
          delta={sales.data?.delta_porcentual ?? null}
          deltaLabel="vs mes anterior"
          href="/dashboards/ventas"
          icon={
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="22,12 18,12 15,21 9,3 6,12 2,12" />
            </svg>
          }
        />

        <KpiCard
          title="Stock Total"
          value={inventory.data ? formatNumber(inventory.data.stock_total) : "—"}
          subtitle={`${inventory.data?.num_productos ?? "—"} productos`}
          href="/dashboards/inventario"
          icon={
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 002 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" />
            </svg>
          }
        />

        <KpiCard
          title="Ticket Promedio"
          value={sales.data ? formatMoney(sales.data.ticket_promedio) : "—"}
          subtitle={`${sales.data?.num_facturas ?? "—"} facturas`}
          icon={
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
              <polyline points="14,2 14,8 20,8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
            </svg>
          }
        />

        <KpiCard
          title="Clasificación ABC"
          value={abc.data ? `${abc.data.bucket_a.porcentaje_ingreso}% A` : "—"}
          subtitle={`${abc.data?.total_skus ?? "—"} SKUs`}
          href="/dashboards/abc"
          icon={
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="7" height="7" />
              <rect x="14" y="3" width="7" height="7" />
              <rect x="14" y="14" width="7" height="7" />
              <rect x="3" y="14" width="7" height="7" />
            </svg>
          }
        />

        <KpiCard
          title="Productos Dormidos"
          value={dormidos.data ? `${dormidos.data.total}` : "—"}
          subtitle={dormidos.data && dormidos.data.total > 0 ? "> 90 días sin venta" : "Sin datos"}
          href="/dashboards/dormidos"
          icon={
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12,6 12,12 16,14" />
            </svg>
          }
        />

        <KpiCard
          title="Valor Inventario"
          value={inventory.data ? formatMoney(inventory.data.valor_total) : "—"}
          subtitle="Costo total estimado"
          href="/dashboards/inventario"
          icon={
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="12" y1="1" x2="12" y2="23" />
              <path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" />
            </svg>
          }
        />
      </KpiGrid>
    </div>
  );
}
