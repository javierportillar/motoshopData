"use client";

import { useState } from "react";
import Link from "next/link";
import { useVendedoresSummary, useVendedorDetail } from "@/lib/api/hooks";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Table } from "@/components/ui/Table";
import { DeltaBadge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatMoney } from "@/lib/format/currency";

type TabView = "month" | "historical" | "6months";

const TAB_LABEL: Record<TabView, string> = {
  month: "Este mes",
  historical: "Histórico",
  "6months": "Últimos 6 meses",
};

// ── Vendor Detail Modal ───────────────────────────────────────────────────

function VendorDetailModal({
  nit,
  period,
  onClose,
}: {
  nit: string;
  period: string;
  onClose: () => void;
}): JSX.Element {
  const { data, error, isLoading } = useVendedorDetail(nit, period);

  if (isLoading) {
    return (
      <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center">
        <div className="w-full max-w-lg rounded-t-2xl bg-surface p-5 shadow-xl sm:rounded-2xl">
          <Skeleton className="h-5 w-40" />
          <div className="mt-4 grid grid-cols-2 gap-2">
            <Skeleton className="h-20 rounded-xl" />
            <Skeleton className="h-20 rounded-xl" />
          </div>
          <Skeleton className="mt-4 h-6 w-full rounded-lg" />
          <Skeleton className="mt-4 h-40 w-full rounded-xl" />
          <Skeleton className="mt-4 h-10 w-full rounded-lg" />
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center">
        <div className="w-full max-w-lg rounded-t-2xl bg-surface p-5 shadow-xl sm:rounded-2xl">
          <ErrorState title="Error" message="No se pudieron cargar los datos del vendedor." severity="warning" />
          <button onClick={onClose} className="mt-4 w-full rounded-lg bg-surface-dark px-4 py-2.5 text-sm font-medium text-text-inverse hover:opacity-90">
            Cerrar
          </button>
        </div>
      </div>
    );
  }

  const d = data;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center">
      <div className="w-full max-w-lg rounded-t-2xl bg-surface p-5 shadow-xl sm:rounded-2xl">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-text-primary">{d.nombre}</h2>
            <p className="text-xs text-text-muted">NIT: {d.vendedor_id}</p>
          </div>
          <button onClick={onClose} className="text-sm text-text-muted hover:text-text-primary">
            ✕
          </button>
        </div>

        {/* KPIs detalle */}
        <div className="grid grid-cols-2 gap-2">
          <Card>
            <Stat label="Ventas" value={formatMoney(d.ventas_total)} subtitle={TAB_LABEL[period as TabView]?.toLowerCase() ?? period} />
          </Card>
          <Card>
            <Stat
              label="Ticket prom."
              value={formatMoney(d.ticket_promedio)}
              subtitle={`${d.productos_vendidos} productos`}
            />
          </Card>
        </div>

        <div className="mt-2 flex items-center gap-2 rounded-lg bg-surface-alt p-3">
          <span className="text-xs text-text-muted">Vs período anterior:</span>
          <DeltaBadge value={d.comparacion_mes_anterior.delta ?? 0} />
        </div>

        {/* Categorías top */}
        {d.ventas_por_categoria.length > 0 && (
          <div className="mt-4">
            <h3 className="mb-2 text-sm font-semibold text-text-primary">Top categorías</h3>
            <div className="space-y-1.5">
              {d.ventas_por_categoria.slice(0, 5).map((cat) => (
                <div key={cat.categoria} className="flex items-center justify-between rounded-lg bg-surface-alt px-3 py-2">
                  <span className="text-sm text-text-secondary">{cat.categoria}</span>
                  <span className="text-sm font-medium text-text-primary">{formatMoney(cat.total)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <button
          onClick={onClose}
          className="mt-4 w-full rounded-lg bg-surface-dark px-4 py-2.5 text-sm font-medium text-text-inverse hover:opacity-90"
        >
          Cerrar
        </button>
      </div>
    </div>
  );
}

// ── Página principal ──────────────────────────────────────────────────────

export default function VendedoresPage(): JSX.Element {
  const [tab, setTab] = useState<TabView>("month");
  const [detailNit, setDetailNit] = useState<string | null>(null);

  // Pre-fetch todos los períodos para que el cambio de tab sea instantáneo
  const monthSummary = useVendedoresSummary("month");
  const historicalSummary = useVendedoresSummary("historical");
  const sixMonthsSummary = useVendedoresSummary("6months");

  const activeSummary =
    tab === "month" ? monthSummary
    : tab === "historical" ? historicalSummary
    : sixMonthsSummary;

  const { data, error, isLoading } = activeSummary;

  // ── Loading ──────────────────────────────────────────────────

  if (isLoading) {
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
        <ErrorState
          title="Error al cargar"
          message="No se pudieron obtener los datos de vendedores."
          severity="warning"
        />
      </div>
    );
  }

  const items = data.items;

  const totalVendido = items.reduce((s, v) => s + v.total_ventas, 0);
  const totalFacturas = items.reduce((s, v) => s + v.facturas, 0);
  const totalVendedores = items.length;

  // ── Tabs ─────────────────────────────────────────────────────

  function renderTabButtons(): JSX.Element {
    const views: TabView[] = ["month", "historical", "6months"];
    return (
      <div className="flex gap-2">
        {views.map((v) => (
          <button
            key={v}
            onClick={() => setTab(v)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
              tab === v
                ? "bg-surface-dark text-text-inverse"
                : "bg-surface-alt text-text-secondary hover:bg-surface-dark/10"
            }`}
          >
            {TAB_LABEL[v]}
          </button>
        ))}
      </div>
    );
  }

  // ── Render tabla según tab ───────────────────────────────────

  function renderTable() {
    const columns = [
      { header: "#", cell: (_: unknown, i: number) => i + 1, align: "center" as const, className: "w-8" },
      {
        header: "Vendedor",
        cell: (v: { nombre_vendedor: string; nit_vendedor: string }) => (
          <div>
            <p className="text-sm font-medium">{v.nombre_vendedor}</p>
            <p className="font-mono text-xs text-text-muted">{v.nit_vendedor}</p>
          </div>
        ),
      },
      {
        header: "Facturas",
        cell: (v: { facturas: number }) => v.facturas,
        align: "right" as const,
      },
      {
        header: "Total",
        cell: (v: { total_ventas: number }) => formatMoney(v.total_ventas),
        align: "right" as const,
      },
      {
        header: "Ticket",
        cell: (v: { ticket_promedio: number }) => formatMoney(v.ticket_promedio),
        align: "right" as const,
      },
      {
        header: "",
        cell: (v: { nit_vendedor: string }) => (
          <button
            onClick={() => setDetailNit(v.nit_vendedor)}
            className="text-xs font-medium text-primary hover:underline"
          >
            Ver detalle
          </button>
        ),
        align: "center" as const,
      },
    ];

    return (
      <Card header={<h2 className="font-semibold text-text-primary">Ranking {TAB_LABEL[tab].toLowerCase()}</h2>}>
        <Table columns={columns} data={items} keyFn={(v) => v.nit_vendedor} striped />
      </Card>
    );
  }

  // ── Render ───────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">
        ← Volver a inicio
      </Link>

      <div>
        <h1 className="text-xl font-bold text-text-primary">Vendedores</h1>
        <p className="text-sm text-text-muted">Rendimiento — {TAB_LABEL[tab]}</p>
      </div>

      {renderTabButtons()}

      {/* KPIs */}
      <div className="grid grid-cols-3 gap-3">
        <Card>
          <Stat label="Total vendido" value={formatMoney(totalVendido)} subtitle={TAB_LABEL[tab].toLowerCase()} />
        </Card>
        <Card>
          <Stat label="Facturas" value={totalFacturas.toLocaleString("es-CO")} subtitle={TAB_LABEL[tab].toLowerCase()} />
        </Card>
        <Card>
          <Stat label="Vendedores" value={String(totalVendedores)} subtitle="activos" />
        </Card>
      </div>

      {renderTable()}

      {/* Modal detalle vendedor */}
      {detailNit && <VendorDetailModal nit={detailNit} period={tab} onClose={() => setDetailNit(null)} />}
    </div>
  );
}
