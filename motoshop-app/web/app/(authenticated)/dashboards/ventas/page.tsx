"use client";

import { useState } from "react";
import Link from "next/link";
import {
  useSalesSummary,
  useSalesTrend,
  useSalesDaily,
  useSalesHistorical,
} from "@/lib/api/hooks";
import { formatMoney } from "@/lib/format/currency";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
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

export default function VentasPage(): JSX.Element {
  const [tab, setTab] = useState<TabView>("mensual");
  const sales = useSalesSummary();
  const trend = useSalesTrend(9);
  const salesDaily = useSalesDaily();
  const salesHistorical = useSalesHistorical();

  // ── Loading (solo para el tab activo) ────────────────────────

  const activeIsLoading =
    tab === "mensual"
      ? sales.isLoading
      : tab === "diaria"
        ? salesDaily.isLoading
        : salesHistorical.isLoading;

  if (activeIsLoading) {
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

  // ── Error (solo para el tab activo) ──────────────────────────

  const activeError =
    tab === "mensual"
      ? sales.error
      : tab === "diaria"
        ? salesDaily.error
        : salesHistorical.error;

  const activeHasData =
    tab === "mensual"
      ? !!sales.data
      : tab === "diaria"
        ? !!salesDaily.data
        : !!salesHistorical.data;

  if (activeError || !activeHasData) {
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

  const d = sales.data!;
  const dd = salesDaily.data!;
  const dh = salesHistorical.data!;

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
    const totalUnidades = dd.productos_vendidos.reduce((s, p) => s + p.cantidad, 0);
    const ticketProm = dd.total_facturas > 0 ? dd.total_ventas / dd.total_facturas : 0;
    return (
      <>
        {/* KPIs diarios */}
        <div className="grid grid-cols-3 gap-3">
          <Card>
            <Stat label="Ventas hoy" value={formatMoney(dd.total_ventas)} subtitle="del día" />
          </Card>
          <Card>
            <Stat label="Productos" value={String(totalUnidades)} subtitle="unidades vendidas" />
          </Card>
          <Card>
            <Stat label="Ticket prom." value={formatMoney(ticketProm)} subtitle="por factura" />
          </Card>
        </div>

        {/* Detalle de productos vendidos hoy */}
        <Card header={<h2 className="font-semibold text-text-primary">Productos vendidos — hoy</h2>}>
          <Table
            columns={[
              { header: "SKU", cell: (r: (typeof dd.productos_vendidos)[number]) => r.sku },
              {
                header: "Producto",
                cell: (r: (typeof dd.productos_vendidos)[number]) => r.nombre,
              },
              { header: "Cant.", cell: (r: (typeof dd.productos_vendidos)[number]) => r.cantidad, align: "right" },
              { header: "Valor", cell: (r: (typeof dd.productos_vendidos)[number]) => formatMoney(r.valor), align: "right" },
            ]}
            data={dd.productos_vendidos}
            keyFn={(r: (typeof dd.productos_vendidos)[number]) => r.sku}
            striped
          />
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
    const histItems = dh.meses.map((m) => ({
      label: `${MONTH_NAMES[m.month - 1]} ${m.year}`,
      ventas: m.total_ventas,
      facturas: m.num_facturas,
    }));
    const numMeses = dh.meses.length;
    const promMensual = numMeses > 0 ? dh.total_ventas / numMeses : 0;
    const primer = numMeses > 0 ? dh.meses[0] : null;
    const primerMes = primer
      ? `${MONTH_NAMES[primer.month - 1]} ${primer.year}`
      : dh.fecha_primera_venta ?? "—";
    return (
      <>
        <div className="grid grid-cols-3 gap-3">
          <Card>
            <Stat label="Total acumulado" value={formatMoney(dh.total_ventas)} subtitle={`${dh.meses.length} meses`} />
          </Card>
          <Card>
            <Stat label="Promedio mensual" value={formatMoney(promMensual)} subtitle="histórico" />
          </Card>
          <Card>
            <Stat label="Desde" value={primerMes} subtitle="primer registro" />
          </Card>
        </div>

        <Card header={<h2 className="font-semibold text-text-primary">Tendencia histórica</h2>}>
          <SalesTrendChart
            data={histItems.map((h) => ({ label: h.label, valor: h.ventas }))}
          />
        </Card>

        <Card header={<h2 className="font-semibold text-text-primary">Detalle por período</h2>}>
          <Table
            columns={[
              { header: "Mes", cell: (h: (typeof histItems)[number]) => h.label },
              { header: "Ventas", cell: (h: (typeof histItems)[number]) => formatMoney(h.ventas), align: "right" },
              { header: "Facturas", cell: (h: (typeof histItems)[number]) => h.facturas, align: "right" },
            ]}
            data={histItems}
            keyFn={(h) => h.label}
            striped
          />
        </Card>
      </>
    );
  }

  // ── Render principal ────────────────────────────────────────

  const totalMesesHist = dh.meses.length;

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">
        ← Volver a inicio
      </Link>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Ventas</h1>
          <p className="text-sm text-text-muted">
            {tab === "diaria" && `Ventas del día — ${dd.date}`}
            {tab === "mensual" && `Período: ${d.business_month}`}
            {tab === "historica" && `Histórico — ${totalMesesHist} meses`}
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
