"use client";

import { useState } from "react";
import Link from "next/link";
import { useSalesSummary, useSalesTrend } from "@/lib/api/hooks";
import { formatMoney } from "@/lib/format/currency";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Badge } from "@/components/ui/Badge";
import { Table } from "@/components/ui/Table";
import { SalesTrendChart } from "@/components/SalesTrendChart";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";

const MONTH_NAMES = [
  "Ene", "Feb", "Mar", "Abr", "May", "Jun",
  "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
];

type TabView = "diaria" | "mensual" | "historica";

const TAB_LABEL: Record<TabView, string> = {
  diaria: "Diaria",
  mensual: "Mensual",
  historica: "Histórica",
};

// ── Mock data helpers (TODO: reemplazar con endpoints reales cuando Backend 1 los implemente) ──

interface VentaDiariaItem {
  sku: string;
  nombre: string;
  cantidad: number;
  valor: number;
  vendedor: string;
}

interface VentaDiariaResponse {
  ventas_hoy: number;
  productos_vendidos: number;
  ticket_promedio: number;
  detalles: VentaDiariaItem[];
}

interface VentaHistoricaItem {
  mes: string;
  ventas: number;
  facturas: number;
}

interface VentaHistoricaResponse {
  total_periodos: number;
  total_ventas: number;
  primer_mes: string;
  items: VentaHistoricaItem[];
}

function mockDiaria(): VentaDiariaResponse {
  return {
    ventas_hoy: 2_450_000,
    productos_vendidos: 47,
    ticket_promedio: 52_128,
    detalles: [
      { sku: "MOTS-001", nombre: "Filtro de aceite YAMAHA", cantidad: 5, valor: 125_000, vendedor: "Carlos" },
      { sku: "MOTS-045", nombre: "Pastillas de freno DELANTERAS", cantidad: 3, valor: 340_000, vendedor: "Ana" },
      { sku: "MOTS-102", nombre: "Cadena de transmisión DID", cantidad: 2, valor: 280_000, vendedor: "Carlos" },
      { sku: "MOTS-078", nombre: "Bujía NGK IRIDIUM", cantidad: 8, valor: 160_000, vendedor: "Pedro" },
      { sku: "MOTS-034", nombre: "Aceite de motor 20W50", cantidad: 12, valor: 240_000, vendedor: "Ana" },
      { sku: "MOTS-210", nombre: "Filtro de aire K&N", cantidad: 2, valor: 180_000, vendedor: "Pedro" },
      { sku: "MOTS-156", nombre: "Kit de arrastre SUNSTAR", cantidad: 1, valor: 195_000, vendedor: "Carlos" },
      { sku: "MOTS-089", nombre: "Líquido de frenos DOT4", cantidad: 10, valor: 150_000, vendedor: "Ana" },
      { sku: "MOTS-067", nombre: "Amortiguador trasero", cantidad: 1, valor: 420_000, vendedor: "Pedro" },
      { sku: "MOTS-123", nombre: "Manija de embrague", cantidad: 3, valor: 360_000, vendedor: "Carlos" },
    ],
  };
}

function mockHistorica(): VentaHistoricaResponse {
  return {
    total_periodos: 24,
    total_ventas: 218_500_000,
    primer_mes: "Jun 2024",
    items: [
      { mes: "Jun 24", ventas: 7_200_000, facturas: 142 },
      { mes: "Jul 24", ventas: 7_800_000, facturas: 158 },
      { mes: "Ago 24", ventas: 8_100_000, facturas: 165 },
      { mes: "Sep 24", ventas: 8_400_000, facturas: 170 },
      { mes: "Oct 24", ventas: 8_900_000, facturas: 180 },
      { mes: "Nov 24", ventas: 9_200_000, facturas: 185 },
      { mes: "Dic 24", ventas: 11_500_000, facturas: 220 },
      { mes: "Ene 25", ventas: 8_000_000, facturas: 155 },
      { mes: "Feb 25", ventas: 7_500_000, facturas: 148 },
      { mes: "Mar 25", ventas: 8_800_000, facturas: 172 },
      { mes: "Abr 25", ventas: 9_000_000, facturas: 178 },
      { mes: "May 25", ventas: 9_500_000, facturas: 190 },
      { mes: "Jun 25", ventas: 10_200_000, facturas: 200 },
      { mes: "Jul 25", ventas: 10_800_000, facturas: 210 },
      { mes: "Ago 25", ventas: 11_000_000, facturas: 215 },
      { mes: "Sep 25", ventas: 11_200_000, facturas: 218 },
      { mes: "Oct 25", ventas: 11_500_000, facturas: 225 },
      { mes: "Nov 25", ventas: 11_800_000, facturas: 230 },
      { mes: "Dic 25", ventas: 14_200_000, facturas: 265 },
      { mes: "Ene 26", ventas: 10_500_000, facturas: 202 },
      { mes: "Feb 26", ventas: 9_800_000, facturas: 195 },
      { mes: "Mar 26", ventas: 10_200_000, facturas: 198 },
      { mes: "Abr 26", ventas: 10_800_000, facturas: 210 },
      { mes: "May 26", ventas: 11_300_000, facturas: 218 },
    ],
  };
}

export default function VentasPage(): JSX.Element {
  const [tab, setTab] = useState<TabView>("mensual");
  const sales = useSalesSummary();
  const trend = useSalesTrend(9);

  const diariaData = mockDiaria(); // TODO: reemplazar con fetch a /api/metrics/sales-daily?date=... cuando Backend 1 lo implemente
  const historicaData = mockHistorica(); // TODO: reemplazar con fetch a /api/metrics/sales-historical cuando Backend 1 lo implemente

  const isLoading = sales.isLoading || trend.isLoading;

  // ── Loading ──────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-accent hover:underline">
          ← Volver a inicio
        </Link>
        <Skeleton className="h-5 w-24" />
        <div className="grid grid-cols-2 gap-3">
          {[...Array(2)].map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-60 rounded-xl" />
        <Skeleton className="h-60 rounded-xl" />
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
        <ErrorState
          title="Error al cargar"
          message="No se pudieron obtener los datos de ventas."
          severity="warning"
        />
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

  function renderTabButtons(): JSX.Element {
    const views: TabView[] = ["diaria", "mensual", "historica"];
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

  // ── Vista diaria ────────────────────────────────────────────

  function renderDiaria(): JSX.Element {
    return (
      <>
        {/* KPIs diarios */}
        <div className="grid grid-cols-3 gap-3">
          <Card>
            <Stat label="Ventas hoy" value={formatMoney(diariaData.ventas_hoy)} subtitle="del día" />
          </Card>
          <Card>
            <Stat label="Productos" value={String(diariaData.productos_vendidos)} subtitle="vendidos hoy" />
          </Card>
          <Card>
            <Stat label="Ticket prom." value={formatMoney(diariaData.ticket_promedio)} subtitle="por factura" />
          </Card>
        </div>

        {/* Detalle por vendedor */}
        <Card header={<h2 className="font-semibold text-text-primary">Detalle por vendedor — hoy</h2>}>
          <Table
            columns={[
              { header: "Vendedor", cell: (r: VentaDiariaItem) => r.vendedor },
              {
                header: "Productos",
                cell: (r: VentaDiariaItem) => r.nombre,
              },
              { header: "Cant.", cell: (r: VentaDiariaItem) => r.cantidad, align: "right" },
              { header: "Valor", cell: (r: VentaDiariaItem) => formatMoney(r.valor), align: "right" },
            ]}
            data={diariaData.detalles}
            keyFn={(r: VentaDiariaItem) => r.sku}
            striped
          />
          {/* TODO: reemplazar mockDiaria() con fetch a /api/metrics/sales-daily?date=... cuando Backend 1 lo implemente */}
        </Card>
      </>
    );
  }

  // ── Vista mensual (existente) ───────────────────────────────

  function renderMensual(): JSX.Element {
    return (
      <>
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
          <Skeleton className="h-60 rounded-xl" />
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
                      <p className="font-mono text-xs text-text-muted">{sku.cod_producto}</p>
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
      </>
    );
  }

  // ── Vista histórica ─────────────────────────────────────────

  function renderHistorica(): JSX.Element {
    const histItems = historicaData.items;
    return (
      <>
        <div className="grid grid-cols-3 gap-3">
          <Card>
            <Stat label="Total acumulado" value={formatMoney(historicaData.total_ventas)} subtitle={`${historicaData.total_periodos} meses`} />
          </Card>
          <Card>
            <Stat label="Promedio mensual" value={formatMoney(historicaData.total_ventas / historicaData.total_periodos)} subtitle="últimos 2 años" />
          </Card>
          <Card>
            <Stat label="Desde" value={historicaData.primer_mes} subtitle="primer registro" />
          </Card>
        </div>

        <Card header={<h2 className="font-semibold text-text-primary">Tendencia histórica</h2>}>
          <SalesTrendChart
            data={histItems.map((h) => ({ label: h.mes, valor: h.ventas }))}
          />
          {/* TODO: reemplazar mockHistorica() con fetch a /api/metrics/sales-historical cuando Backend 1 lo implemente */}
        </Card>

        <Card header={<h2 className="font-semibold text-text-primary">Detalle por período</h2>}>
          <Table
            columns={[
              { header: "Mes", cell: (h: VentaHistoricaItem) => h.mes },
              { header: "Ventas", cell: (h: VentaHistoricaItem) => formatMoney(h.ventas), align: "right" },
              { header: "Facturas", cell: (h: VentaHistoricaItem) => h.facturas, align: "right" },
            ]}
            data={histItems}
            keyFn={(h: VentaHistoricaItem) => h.mes}
            striped
          />
        </Card>
      </>
    );
  }

  // ── Render principal ────────────────────────────────────────

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">
        ← Volver a inicio
      </Link>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Ventas</h1>
          <p className="text-sm text-text-muted">
            {tab === "diaria" && "Ventas del día"}
            {tab === "mensual" && `Período: ${d.business_month}`}
            {tab === "historica" && `Histórico — ${historicaData.total_periodos} meses`}
          </p>
        </div>
      </div>

      {renderTabButtons()}
      {tab === "diaria" && renderDiaria()}
      {tab === "mensual" && renderMensual()}
      {tab === "historica" && renderHistorica()}
    </div>
  );
}
