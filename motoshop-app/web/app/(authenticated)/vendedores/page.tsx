"use client";

import { useState } from "react";
import Link from "next/link";
import { useVendedoresSummary } from "@/lib/api/hooks";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Table } from "@/components/ui/Table";
import { DeltaBadge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatMoney } from "@/lib/format/currency";

type TabView = "month" | "historical" | "6months";

const TAB_LABEL: Record<TabView, string> = {
  month: "Este mes",
  historical: "Histórico",
  "6months": "Últimos 6 meses",
};

// ── Mock data helpers ─────────────────────────────────────────────────────
// TODO: reemplazar con /api/metrics/vendedores-summary?period=... cuando Backend 1 lo implemente

interface VendedorDetalle {
  nit_vendedor: string;
  nombre_vendedor: string;
  total_ventas: number;
  facturas: number;
  ticket_promedio: number;
  ventas_mes_anterior: number;
  delta_vs_mes_anterior: number;
  productos_vendidos: number;
  categorias: { nombre: string; valor: number }[];
}

function mockVendedorDetalle(nit: string): VendedorDetalle {
  const catalog: Record<string, VendedorDetalle> = {
    "9001": {
      nit_vendedor: "9001",
      nombre_vendedor: "Ana López",
      total_ventas: 12_450_000,
      facturas: 98,
      ticket_promedio: 127_041,
      ventas_mes_anterior: 11_200_000,
      delta_vs_mes_anterior: 11.2,
      productos_vendidos: 184,
      categorias: [
        { nombre: "Aceites y lubricantes", valor: 3_800_000 },
        { nombre: "Frenos", valor: 2_900_000 },
        { nombre: "Filtros", valor: 2_100_000 },
        { nombre: "Transmisión", valor: 1_800_000 },
        { nombre: "Eléctrico", valor: 1_850_000 },
      ],
    },
    "9002": {
      nit_vendedor: "9002",
      nombre_vendedor: "Carlos Mejía",
      total_ventas: 11_800_000,
      facturas: 85,
      ticket_promedio: 138_824,
      ventas_mes_anterior: 10_500_000,
      delta_vs_mes_anterior: 12.4,
      productos_vendidos: 156,
      categorias: [
        { nombre: "Transmisión", valor: 3_200_000 },
        { nombre: "Motor", valor: 2_800_000 },
        { nombre: "Frenos", valor: 2_400_000 },
        { nombre: "Suspensión", valor: 1_900_000 },
        { nombre: "Aceites", valor: 1_500_000 },
      ],
    },
    "9003": {
      nit_vendedor: "9003",
      nombre_vendedor: "Pedro Ramírez",
      total_ventas: 8_920_000,
      facturas: 72,
      ticket_promedio: 123_889,
      ventas_mes_anterior: 9_100_000,
      delta_vs_mes_anterior: -2.0,
      productos_vendidos: 132,
      categorias: [
        { nombre: "Eléctrico", valor: 2_500_000 },
        { nombre: "Filtros", valor: 2_200_000 },
        { nombre: "Aceites", valor: 1_800_000 },
        { nombre: "Frenos", valor: 1_400_000 },
        { nombre: "Accesorios", valor: 1_020_000 },
      ],
    },
  };
  return catalog[nit] ?? {
    nit_vendedor: nit,
    nombre_vendedor: "Vendedor",
    total_ventas: 0,
    facturas: 0,
    ticket_promedio: 0,
    ventas_mes_anterior: 0,
    delta_vs_mes_anterior: 0,
    productos_vendidos: 0,
    categorias: [],
  };
}

function mockHistoricalRanking() {
  return [
    { nit_vendedor: "9001", nombre_vendedor: "Ana López", total_ventas: 98_500_000, facturas: 780, ticket_promedio: 126_282 },
    { nit_vendedor: "9002", nombre_vendedor: "Carlos Mejía", total_ventas: 92_300_000, facturas: 710, ticket_promedio: 130_000 },
    { nit_vendedor: "9003", nombre_vendedor: "Pedro Ramírez", total_ventas: 85_100_000, facturas: 695, ticket_promedio: 122_446 },
  ];
}

function mock6MonthsRanking() {
  return [
    { nit_vendedor: "9001", nombre_vendedor: "Ana López", total_ventas: 68_200_000, facturas: 520, ticket_promedio: 131_154, tendencia: "up" as const },
    { nit_vendedor: "9002", nombre_vendedor: "Carlos Mejía", total_ventas: 62_500_000, facturas: 485, ticket_promedio: 128_866, tendencia: "up" as const },
    { nit_vendedor: "9003", nombre_vendedor: "Pedro Ramírez", total_ventas: 55_800_000, facturas: 430, ticket_promedio: 129_767, tendencia: "down" as const },
  ];
}

// ── Vendor Detail Modal ───────────────────────────────────────────────────

function VendorDetailModal({
  nit,
  onClose,
}: {
  nit: string;
  onClose: () => void;
}): JSX.Element {
  const detalle = mockVendedorDetalle(nit);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center">
      <div className="w-full max-w-lg rounded-t-2xl bg-surface p-5 shadow-xl sm:rounded-2xl">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-text-primary">{detalle.nombre_vendedor}</h2>
            <p className="text-xs text-text-muted">NIT: {detalle.nit_vendedor}</p>
          </div>
          <button onClick={onClose} className="text-sm text-text-muted hover:text-text-primary">
            ✕
          </button>
        </div>

        {/* KPIs detalle */}
        <div className="grid grid-cols-2 gap-2">
          <Card>
            <Stat label="Ventas mes" value={formatMoney(detalle.total_ventas)} subtitle={`${detalle.facturas} facturas`} />
          </Card>
          <Card>
            <Stat
              label="Ticket prom."
              value={formatMoney(detalle.ticket_promedio)}
              subtitle={`${detalle.productos_vendidos} productos`}
            />
          </Card>
        </div>

        <div className="mt-2 flex items-center gap-2 rounded-lg bg-surface-alt p-3">
          <span className="text-xs text-text-muted">Vs mes anterior:</span>
          <DeltaBadge value={detalle.delta_vs_mes_anterior} />
        </div>

        {/* Categorías top */}
        {detalle.categorias.length > 0 && (
          <div className="mt-4">
            <h3 className="mb-2 text-sm font-semibold text-text-primary">Top categorías</h3>
            <div className="space-y-1.5">
              {detalle.categorias.slice(0, 5).map((cat) => (
                <div key={cat.nombre} className="flex items-center justify-between rounded-lg bg-surface-alt px-3 py-2">
                  <span className="text-sm text-text-secondary">{cat.nombre}</span>
                  <span className="text-sm font-medium text-text-primary">{formatMoney(cat.valor)}</span>
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

  const { data, error, isLoading } = useVendedoresSummary();

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
        <Card>
          <p className="py-8 text-center text-sm text-text-muted">
            Error al cargar datos de vendedores
          </p>
        </Card>
      </div>
    );
  }

  const items = data.items;

  // ── Mock data según tab ──────────────────────────────────────

  const historicalData = mockHistoricalRanking();
  const sixMonthsData = mock6MonthsRanking();

  const totalVendido =
    tab === "month"
      ? items.reduce((s, v) => s + v.total_ventas, 0)
      : tab === "historical"
        ? historicalData.reduce((s, v) => s + v.total_ventas, 0)
        : sixMonthsData.reduce((s, v) => s + v.total_ventas, 0);

  const totalFacturas =
    tab === "month"
      ? items.reduce((s, v) => s + v.facturas, 0)
      : tab === "historical"
        ? historicalData.reduce((s, v) => s + v.facturas, 0)
        : sixMonthsData.reduce((s, v) => s + v.facturas, 0);

  const totalVendedores =
    tab === "month" ? items.length : tab === "historical" ? historicalData.length : sixMonthsData.length;

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
    const rows: {
      nit_vendedor: string;
      nombre_vendedor: string;
      facturas: number;
      total_ventas: number;
      ticket_promedio: number;
    }[] = tab === "month"
      ? items
      : tab === "historical"
        ? historicalData
        : sixMonthsData;

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
        <Table columns={columns} data={rows} keyFn={(v) => (v as { nit_vendedor: string }).nit_vendedor} striped />
        {/* TODO: reemplazar mock data con /api/metrics/vendedores-summary?period=... cuando Backend 1 lo implemente */}
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
      {detailNit && <VendorDetailModal nit={detailNit} onClose={() => setDetailNit(null)} />}
    </div>
  );
}
