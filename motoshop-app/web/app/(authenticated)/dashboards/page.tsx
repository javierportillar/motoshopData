"use client";

import Link from "next/link";
import { useSalesSummary, useInventorySummary, useAbcSegmentation, useDormidos } from "@/lib/api/hooks";
import { formatMoney } from "@/lib/format/currency";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";

export default function DashboardsPage(): JSX.Element {
  const sales = useSalesSummary();
  const inventory = useInventorySummary();
  const abc = useAbcSegmentation();
  const dormidos = useDormidos();

  const loading =
    sales.isLoading || inventory.isLoading || abc.isLoading || dormidos.isLoading;
  const errors = [sales.error, inventory.error, abc.error, dormidos.error].filter(Boolean);

  // ── Error ────────────────────────────────────────────────────

  if (!loading && errors.length > 0) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Dashboards</h1>
          <p className="text-sm text-text-muted">Indicadores del negocio</p>
        </div>
        <Card>
          <p className="py-8 text-center text-sm text-error">
            Error al cargar indicadores. Intentá de nuevo más tarde.
          </p>
        </Card>
      </div>
    );
  }

  // ── Loading ──────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Dashboards</h1>
          <p className="text-sm text-text-muted">Indicadores del negocio</p>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[...Array(6)].map((_, i) => (
            <div
              key={i}
              className="animate-pulse space-y-3 rounded-xl border border-border bg-surface p-4"
            >
              <div className="h-3 w-20 rounded bg-surface-alt" />
              <div className="h-7 w-32 rounded bg-surface-alt" />
              <div className="h-3 w-24 rounded bg-surface-alt" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── Render ───────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-text-primary">Dashboards</h1>
        <p className="text-sm text-text-muted">
          {sales.data?.business_month
            ? `Indicadores — ${sales.data.business_month}`
            : "Indicadores del negocio"}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Link href="/dashboards/ventas" className="block">
          <Card hover className="cursor-pointer">
            <Stat
              label="Ventas del mes"
              value={sales.data ? formatMoney(sales.data.ventas_mes_actual) : "—"}
              delta={sales.data?.delta_porcentual ?? null}
              deltaLabel="vs mes anterior"
              icon={
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="22,12 18,12 15,21 9,3 6,12 2,12" />
                </svg>
              }
            />
          </Card>
        </Link>

        <Link href="/dashboards/inventario" className="block">
          <Card hover className="cursor-pointer">
            <Stat
              label="Stock total"
              value={inventory.data ? inventory.data.stock_total.toLocaleString("es-CO") : "—"}
              subtitle={`${inventory.data?.num_productos ?? "—"} productos`}
              icon={
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 002 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" />
                </svg>
              }
            />
          </Card>
        </Link>

        <Link href="/dashboards/ventas" className="block">
          <Card hover className="cursor-pointer">
            <Stat
              label="Ticket promedio"
              value={sales.data ? formatMoney(sales.data.ticket_promedio) : "—"}
              subtitle={`${sales.data?.num_facturas ?? "—"} facturas`}
              icon={
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                  <polyline points="14,2 14,8 20,8" />
                </svg>
              }
            />
          </Card>
        </Link>

        <Link href="/dashboards/abc" className="block">
          <Card hover className="cursor-pointer">
            <Stat
              label="Clasificación ABC"
              value={abc.data ? `${abc.data.bucket_a.porcentaje_ingreso}% A` : "—"}
              subtitle={`${abc.data?.total_skus ?? "—"} SKUs`}
              icon={
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="7" height="7" />
                  <rect x="14" y="3" width="7" height="7" />
                  <rect x="14" y="14" width="7" height="7" />
                  <rect x="3" y="14" width="7" height="7" />
                </svg>
              }
            />
          </Card>
        </Link>

        <Link href="/dashboards/dormidos" className="block">
          <Card hover className="cursor-pointer">
            <Stat
              label="Productos dormidos"
              value={dormidos.data ? String(dormidos.data.total) : "—"}
              subtitle={dormidos.data && dormidos.data.total > 0 ? "&gt; 90 días sin venta" : "Sin datos"}
              icon={
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="12,6 12,12 16,14" />
                </svg>
              }
            />
          </Card>
        </Link>

        <Link href="/dashboards/inventario" className="block">
          <Card hover className="cursor-pointer">
            <Stat
              label="Valor inventario"
              value={inventory.data ? formatMoney(inventory.data.valor_total) : "—"}
              subtitle="Costo total estimado"
              icon={
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="12" y1="1" x2="12" y2="23" />
                  <path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" />
                </svg>
              }
            />
          </Card>
        </Link>
      </div>
    </div>
  );
}
