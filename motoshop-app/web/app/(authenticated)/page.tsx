"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuthStore } from "@/lib/auth/store";
import { useSalesSummaryV2, useInventorySummary, useAlerts, useDormidos, useSalesTrendByYear } from "@/lib/api/hooks";
import { formatMoney } from "@/lib/format/currency";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Badge } from "@/components/ui/Badge";
import { Logo } from "@/components/Logo";
import { SalesTrendChart } from "@/components/SalesTrendChart";
import { SearchBar } from "@/components/SearchBar";
import { StaleDataBanner } from "@/components/StaleDataBanner";
import { Skeleton, SkeletonCard } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";

// ── Gerente: home completo ────────────────────────────────────────────────

function GerenteHome(): JSX.Element {
  const sales = useSalesSummaryV2();
  const inventory = useInventorySummary();
  const alerts = useAlerts();
  const dormidos = useDormidos();
  const currentYear = new Date().getFullYear();
  const trend = useSalesTrendByYear(currentYear, 24);
  const trendPrev = useSalesTrendByYear(currentYear - 1, 24);

  // F7-FIX1 bug 5.1: bloquear el render completo solo en la primera carga del KPI
  // principal (sales). El resto de hooks muestra "—" o skeleton inline mientras
  // resuelve. Evita el flicker "vacío → data → vacío → data" cuando un hook
  // tarda más o falla mientras el resto ya tiene datos.
  const loading = sales.isLoading && !sales.data;

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Logo size="md" />
          <div>
            <h1 className="text-xl font-bold text-text-primary">MotoShop</h1>
            <p className="text-sm text-text-muted">Panel de gerencia</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
        <SkeletonCard />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          {[...Array(5)].map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (sales.error || !sales.data) {
    return (
      <ErrorState
        title="Error al cargar"
        message="No se pudieron obtener los indicadores de gerencia. Verificá la conexión e intentá de nuevo."
        severity="warning"
      />
    );
  }

  const hasData = sales.data && inventory.data;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Logo size="md" />
        <div>
          <h1 className="text-xl font-bold text-text-primary">MotoShop</h1>
          <p className="text-sm text-text-muted">
            {sales.data?.max_sales_date
              ? `Panel de gerencia — Acumulado hasta ${sales.data.max_sales_date}`
              : "Panel de gerencia"}
          </p>
        </div>
      </div>

      <StaleDataBanner />

      {/* KPIs principales */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Link href="/dashboards/ventas" className="block">
          <Card hover className="cursor-pointer">
            <Stat
              label="Ventas del mes"
              value={sales.data ? formatMoney(sales.data.current_month_accumulated) : "—"}
              subtitle={sales.data ? `Acumulado ${sales.data.current_month_days_with_sales} días` : ""}
              icon={
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="22,12 18,12 15,21 9,3 6,12 2,12" />
                </svg>
              }
            />
          </Card>
        </Link>

        <Link href="/dashboards/ventas" className="block">
          <Card hover className="cursor-pointer">
            <Stat
              label="Facturas"
              value={sales.data ? sales.data.num_facturas.toLocaleString("es-CO") : "—"}
              subtitle="este mes"
              icon={
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                  <polyline points="14,2 14,8 20,8" />
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
              subtitle="por factura"
              icon={
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="12" y1="1" x2="12" y2="23" />
                  <path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" />
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
              subtitle={`${inventory.data?.num_productos ?? "—"} productos`}
              icon={
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 002 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" />
                </svg>
              }
            />
          </Card>
        </Link>
      </div>

      {/* Tendencia mensual: año actual vs año anterior (F7-FIX1 bug 5.4) */}
      {trend.data && trend.data.items.length > 0 && (() => {
        const MONTH_LABELS = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
        const currMap = new Map(trend.data.items.filter(i => i.year === currentYear).map(i => [i.month, i.total_ventas]));
        const prevMap = new Map((trendPrev.data?.items ?? []).map(i => [i.month, i.total_ventas]));
        // Solo meses con datos reales (no pintar meses futuros en cero)
        const currentMonth = new Date().getMonth() + 1;
        const monthsWithData = Math.max(
          ...[...currMap.keys(), ...prevMap.keys(), currentMonth]
        );
        const currData = Array.from({ length: monthsWithData }, (_, i) => ({ label: MONTH_LABELS[i] ?? "", valor: currMap.get(i + 1) ?? 0 }));
        const prevData = Array.from({ length: monthsWithData }, (_, i) => ({ label: MONTH_LABELS[i] ?? "", valor: prevMap.get(i + 1) ?? 0 }));
        const hasPrev = prevData.some(p => p.valor > 0);
        return (
          <Card header={
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-text-primary">Tendencia mensual</h2>
              <div className="flex items-center gap-3 text-xs">
                <span className="flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full" style={{background:"#7B1818"}}></span>
                  <span className="text-text-muted">{currentYear}</span>
                </span>
                {hasPrev && (
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-gray-400"></span>
                    <span className="text-text-muted">{currentYear - 1}</span>
                  </span>
                )}
              </div>
            </div>
          }>
            <SalesTrendChart
              data={currData}
              previousYearData={hasPrev ? prevData : undefined}
              currentYearLabel={`${currentYear}`}
              previousYearLabel={`${currentYear - 1}`}
            />
          </Card>
        );
      })()}

      {/* Decisiones de compra */}
      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-text-muted">
          Decisiones de compra
        </h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          <Link href="/dashboards/ventas" className="block">
            <Card hover className="cursor-pointer">
              <Stat
                label="Ventas"
                value={sales.data ? formatMoney(sales.data.current_month_accumulated) : "—"}
                subtitle="Ver detalle →"
              />
            </Card>
          </Link>

          <Link href="/alerts" className="block">
            <Card hover className="cursor-pointer">
              <div className="flex flex-col gap-1">
                <p className="text-xs font-medium uppercase tracking-wider text-text-muted">Alertas</p>
                <div className="flex items-center gap-2">
                  <p className="text-2xl font-bold text-text-primary">
                    {alerts.data?.total ?? "—"}
                  </p>
                  {alerts.data && alerts.data.total > 0 && (
                    <Badge variant="error" size="sm">activas</Badge>
                  )}
                </div>
                <p className="text-xs text-text-muted">Gestionar →</p>
              </div>
            </Card>
          </Link>

          <Link href="/dashboards/abc" className="block">
            <Card hover className="cursor-pointer">
              <Stat
                label="ABC"
                value={hasData ? `${inventory.data!.num_productos}` : "—"}
                subtitle={`${inventory.data?.num_productos ?? "—"} SKUs →`}
              />
            </Card>
          </Link>

          <Link href="/forecast" className="block">
            <Card hover className="cursor-pointer">
              <div className="flex flex-col gap-1">
                <p className="text-xs font-medium uppercase tracking-wider text-text-muted">Forecast</p>
                <p className="text-2xl font-bold text-text-primary">Pred.</p>
                <p className="text-xs text-text-muted">Consultar →</p>
              </div>
            </Card>
          </Link>

          <Link href="/dashboards/dormidos" className="block">
            <Card hover className="cursor-pointer">
              <div className="flex flex-col gap-1">
                <p className="text-xs font-medium uppercase tracking-wider text-text-muted">Dormidos</p>
                <div className="flex items-center gap-2">
                  <p className="text-2xl font-bold text-text-primary">
                    {dormidos.data?.total ?? "—"}
                  </p>
                  {dormidos.data && dormidos.data.total > 0 && (
                    <Badge variant="warning" size="sm">inmovilizado</Badge>
                  )}
                </div>
                <p className="text-xs text-text-muted">Revisar →</p>
              </div>
            </Card>
          </Link>
        </div>
      </div>
    </div>
  );
}

// ── Vendedor: home completo ───────────────────────────────────────────────

function VendedorHome(): JSX.Element {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const alerts = useAlerts();
  const dormidos = useDormidos();

  const loading = alerts.isLoading || dormidos.isLoading;

  function handleSearch(): void {
    const q = query.trim();
    if (q) {
      router.push(`/products?q=${encodeURIComponent(q)}`);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <Logo size="sm" />
          <div>
            <h1 className="text-lg font-bold text-text-primary">MotoShop</h1>
            <p className="text-xs text-text-muted">Búsqueda rápida</p>
          </div>
        </div>
        <Skeleton className="h-12 rounded-xl" />
        <div className="grid grid-cols-2 gap-3">
          {[...Array(3)].map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header compacto */}
      <div className="flex items-center gap-3">
        <Logo size="sm" />
        <div>
          <h1 className="text-lg font-bold text-text-primary">MotoShop</h1>
          <p className="text-xs text-text-muted">Búsqueda rápida</p>
        </div>
      </div>

      <StaleDataBanner />

      {/* Búsqueda con autofocus */}
      <div className="flex gap-2">
        <div className="flex-1">
          <SearchBar
            value={query}
            onChange={setQuery}
            placeholder="Buscar repuesto por nombre o código..."
          />
        </div>
        <button
          onClick={handleSearch}
          className="rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-fg hover:bg-primary-light"
        >
          Buscar
        </button>
      </div>

      {/* Cards de acción rápida */}
      <div className="grid grid-cols-2 gap-3">
        <Link href="/alerts" className="block">
          <Card variant="dark" hover className="cursor-pointer">
            <div className="flex flex-col gap-1">
              <p className="text-xs font-medium uppercase tracking-wider text-text-inverse/60">
                🚨 Alertas activas
              </p>
              <p className="text-3xl font-bold text-text-inverse">
                {alerts.data?.total ?? "—"}
              </p>
              <p className="text-xs text-text-inverse/50">
                {alerts.data && alerts.data.total > 0
                  ? "Gestionar ahora →"
                  : "Sin alertas"}
              </p>
            </div>
          </Card>
        </Link>

        <Link href="/dashboards/dormidos" className="block">
          <Card variant="dark" hover className="cursor-pointer">
            <div className="flex flex-col gap-1">
              <p className="text-xs font-medium uppercase tracking-wider text-text-inverse/60">
                💤 Liquidar
              </p>
              <p className="text-3xl font-bold text-text-inverse">
                {dormidos.data?.total ?? "—"}
              </p>
              <p className="text-xs text-text-inverse/50">
                {dormidos.data && dormidos.data.total > 0
                  ? "Ver dormidos →"
                  : "Sin productos"}
              </p>
            </div>
          </Card>
        </Link>

        <Link href="/acciones" className="block">
          <Card hover className="cursor-pointer">
            <div className="flex flex-col gap-1">
              <p className="text-xs font-medium uppercase tracking-wider text-text-muted">
                📋 Mis acciones
              </p>
              <p className="text-2xl font-bold text-text-primary">Hoy</p>
              <p className="text-xs text-text-muted">Ver registro →</p>
            </div>
          </Card>
        </Link>

        {/* Top 3 rotación A — placeholder hasta tener endpoint */}
        <Link href="/dashboards/abc" className="block">
          <Card hover className="cursor-pointer">
            <div className="flex flex-col gap-1">
              <p className="text-xs font-medium uppercase tracking-wider text-text-muted">
                ⭐ Rotación A
              </p>
              <p className="text-2xl font-bold text-text-primary">Top</p>
              <p className="text-xs text-text-muted">Ver ABC →</p>
            </div>
          </Card>
        </Link>
      </div>
    </div>
  );
}

// ── Página principal: redirige según rol ──────────────────────────────────

export default function HomePage(): JSX.Element {
  const role = useAuthStore((s) => s.role);
  const hasHydrated = useAuthStore((s) => s.hasHydrated);

  // F7-FIX1 bug 5.1: evitar flicker rol-undefined → GerenteHome → rol-correcto
  // esperando a que Zustand persist rehidrate antes del primer render con contenido.
  if (!hasHydrated) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Logo size="md" />
          <div>
            <h1 className="text-xl font-bold text-text-primary">MotoShop</h1>
            <p className="text-sm text-text-muted">Cargando…</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (role === "vendedor") {
    return <VendedorHome />;
  }

  // admin, gerente, o cualquier otro → vista gerente
  return <GerenteHome />;
}
