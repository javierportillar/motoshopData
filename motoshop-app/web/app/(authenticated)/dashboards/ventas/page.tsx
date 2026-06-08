"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import {
  useSalesSummaryV2,
  useSalesDailyMonth,
  useSalesForecastMonthly,
  useSalesHistorical,
} from "@/lib/api/hooks";
import { formatMoney } from "@/lib/format/currency";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Badge } from "@/components/ui/Badge";
import { Table } from "@/components/ui/Table";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import {
  BarChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ComposedChart,
} from "recharts";

const MONTH_NAMES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

type TabView = "resumen" | "diaria" | "historica" | "forecast";

const TAB_LABEL: Record<TabView, string> = {
  resumen: "Resumen",
  diaria: "Diaria",
  historica: "Histórica",
  forecast: "Forecast",
};

// ── Daily chart: bars + accumulated line ──────────────────────────────

function DailyChart({ days }: { days: { date: string; ventas: number; facturas: number; is_future: boolean }[] }) {
  const data = days.filter(d => !d.is_future).map((d, i) => {
    const acc = days.slice(0, i + 1).reduce((s, day) => s + day.ventas, 0);
    return { label: d.date.slice(8), ventas: d.ventas, acumulado: acc };
  });
  if (data.length === 0) return null;
  return (
    <Card header={<h2 className="font-semibold text-text-primary">Ventas diarias del mes</h2>}>
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="label" tick={{ fontSize: 10 }} stroke="#a3a3a3" />
          <YAxis yAxisId="left" tick={{ fontSize: 10 }} stroke="#a3a3a3" tickFormatter={(v: number) => `$${(v/1e6).toFixed(1)}M`} />
          <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} stroke="#2563EB" tickFormatter={(v: number) => `$${(v/1e6).toFixed(1)}M`} />
          <Tooltip contentStyle={{ borderRadius: "8px", fontSize: "12px" }} />
          <Bar yAxisId="left" dataKey="ventas" fill="#7B1818" radius={[2,2,0,0]} name="Ventas del día" />
          <Line yAxisId="right" type="monotone" dataKey="acumulado" stroke="#2563EB" strokeWidth={2} dot={false} name="Acumulado" />
        </ComposedChart>
      </ResponsiveContainer>
    </Card>
  );
}

// ── Forecast chart ─────────────────────────────────────────────────────

function ForecastChart({ monthly }: { monthly: { month: string; forecast_ventas: number; is_history: boolean; confidence_lower: number | null; confidence_upper: number | null }[] }) {
  if (monthly.length === 0) return (
    <Card><p className="py-6 text-center text-sm text-text-muted">Forecast no disponible aún.</p></Card>
  );
  const data = monthly.map(m => ({
    label: m.month.slice(5),
    history: m.is_history ? m.forecast_ventas : 0,
    predicted: m.is_history ? 0 : m.forecast_ventas,
  }));
  return (
    <Card header={<h2 className="font-semibold text-text-primary">Proyección de ventas</h2>}>
      <div className="flex items-center gap-4 mb-2 text-xs text-text-muted">
        <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{background:"#7B1818"}} /> Real</span>
        <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{background:"#FCD34D"}} /> Proyectado</span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="label" tick={{ fontSize: 10 }} stroke="#a3a3a3" />
          <YAxis tick={{ fontSize: 10 }} stroke="#a3a3a3" tickFormatter={(v: number) => `$${(v/1e6).toFixed(1)}M`} />
          <Tooltip contentStyle={{ borderRadius: "8px", fontSize: "12px" }} />
          <Bar dataKey="history" fill="#7B1818" stackId="a" radius={[4,4,0,0]} name="Real" />
          <Bar dataKey="predicted" fill="#FCD34D" stackId="a" radius={[4,4,0,0]} name="Proyectado" />
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}

// ── Main ──────────────────────────────────────────────────────────────

export default function VentasPage(): JSX.Element {
  const [tab, setTab] = useState<TabView>("resumen");
  const sales = useSalesSummaryV2();
  const currentMonth = new Date().toISOString().slice(0, 7);
  const salesDaily = useSalesDailyMonth(currentMonth);
  const salesHistorical = useSalesHistorical();
  const forecast = useSalesForecastMonthly();

  const activeIsLoading =
    tab === "resumen" ? sales.isLoading
    : tab === "diaria" ? salesDaily.isLoading
    : tab === "forecast" ? forecast.isLoading
    : salesHistorical.isLoading;

  const activeError =
    tab === "resumen" ? sales.error
    : tab === "diaria" ? salesDaily.error
    : tab === "forecast" ? forecast.error
    : salesHistorical.error;

  const activeHasData =
    tab === "resumen" ? !!sales.data
    : tab === "diaria" ? !!salesDaily.data
    : tab === "forecast" ? !!forecast.data
    : !!salesHistorical.data;

  if (activeIsLoading) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-accent hover:underline">← Volver a inicio</Link>
        <Skeleton className="h-5 w-24" />
        <div className="grid grid-cols-2 gap-3">
          {[1,2,3,4].map(i => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
        <Skeleton className="h-60 rounded-xl" />
      </div>
    );
  }

  if (activeError || !activeHasData) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-accent hover:underline">← Volver a inicio</Link>
        <ErrorState title="Error al cargar" message="No se pudieron obtener los datos de ventas." severity="warning" />
      </div>
    );
  }

  const d = sales.data!;
  const dm = salesDaily.data;
  const dh = salesHistorical.data;
  const df = forecast.data;

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">← Volver a inicio</Link>

      <div>
        <h1 className="text-xl font-bold text-text-primary">Ventas</h1>
        <p className="text-sm text-text-muted">
          {d.max_sales_date ? `Datos hasta ${d.max_sales_date}` : ""}
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 flex-wrap">
        {(["resumen", "diaria", "historica", "forecast"] as TabView[]).map(v => (
          <button key={v} onClick={() => setTab(v)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
              tab === v ? "bg-surface-dark text-text-inverse" : "bg-surface-alt text-text-secondary hover:bg-surface-dark/10"
            }`}
          >{TAB_LABEL[v]}</button>
        ))}
      </div>

      {/* ── Resumen (V2) ─────────────────────────────────── */}
      {tab === "resumen" && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Card><Stat label="Ventas acumuladas" value={formatMoney(d.current_month_accumulated)} subtitle={`${d.current_month_days_with_sales} días`} /></Card>
            <Card><Stat label="Facturas" value={d.num_facturas.toLocaleString("es-CO")} subtitle="este mes" /></Card>
            <Card><Stat label="Ticket promedio" value={formatMoney(d.ticket_promedio)} subtitle="por factura" /></Card>
            <Card>
              <Stat
                label="vs mes anterior"
                value={d.previous_month_same_window.delta_pct > 0 ? `+${d.previous_month_same_window.delta_pct}%` : `${d.previous_month_same_window.delta_pct}%`}
                subtitle={`${d.previous_month_same_window.from}–${d.previous_month_same_window.to}`}
              />
            </Card>
          </div>

          <Card header={<h2 className="font-semibold text-text-primary">Comparativa con años anteriores</h2>}>
            <Table
              columns={[
                { header: "Año", cell: (r: typeof d.same_month_previous_years[number]) => String(r.year) },
                { header: "Misma ventana", cell: (r: typeof d.same_month_previous_years[number]) => formatMoney(r.same_day_window_amount), align: "right" },
                { header: "Mes completo", cell: (r: typeof d.same_month_previous_years[number]) => formatMoney(r.full_month_amount), align: "right" },
                { header: "Delta ventana", cell: (r: typeof d.same_month_previous_years[number]) => r.delta_same_window_pct != null ? `${r.delta_same_window_pct > 0 ? "+" : ""}${r.delta_same_window_pct}%` : "—", align: "right" },
              ]}
              data={d.same_month_previous_years}
              keyFn={(r: typeof d.same_month_previous_years[number]) => String(r.year)}
              striped
            />
          </Card>
        </>
      )}

      {/* ── Diaria ───────────────────────────────────────── */}
      {tab === "diaria" && dm && (
        <>
          <div className="grid grid-cols-3 gap-3">
            <Card><Stat label="Total mes" value={formatMoney(dm.total_month)} subtitle={dm.days.length + " días"} /></Card>
            <Card><Stat label="Promedio diario" value={formatMoney(dm.total_month / Math.max(1, dm.days.filter(x => !x.is_future).length))} subtitle="por día con ventas" /></Card>
            <Card><Stat label="Mejor día" value={formatMoney(Math.max(...dm.days.filter(x => !x.is_future).map(x => x.ventas), 0))} /></Card>
          </div>
          <DailyChart days={dm.days} />
          <Card header={<h2 className="font-semibold text-text-primary">Detalle diario</h2>}>
            <Table
              columns={[
                { header: "Día", cell: (r: typeof dm.days[number]) => <span className={r.is_future ? "text-text-muted" : ""}>{r.date.slice(8)}</span> },
                { header: "Ventas", cell: (r: typeof dm.days[number]) => <span className={r.is_future ? "text-text-muted" : ""}>{r.is_future ? "—" : formatMoney(r.ventas)}</span>, align: "right" },
                { header: "Facturas", cell: (r: typeof dm.days[number]) => <span className={r.is_future ? "text-text-muted" : ""}>{r.is_future ? "—" : r.facturas}</span>, align: "right" },
              ]}
              data={dm.days}
              keyFn={(r: typeof dm.days[number]) => r.date}
              striped
            />
          </Card>
        </>
      )}

      {/* ── Histórica ───────────────────────────────────── */}
      {tab === "historica" && dh && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <Card><Stat label="Total histórico" value={formatMoney(dh.total_ventas)} /></Card>
            <Card><Stat label="Facturas totales" value={dh.total_facturas.toLocaleString("es-CO")} /></Card>
          </div>
          <Card header={<h2 className="font-semibold text-text-primary">Ventas mensuales</h2>}>
            <Table
              columns={[
                { header: "Mes", cell: (r: typeof dh.meses[number]) => `${MONTH_NAMES[r.month-1] ?? ""} ${r.year}` },
                { header: "Ventas", cell: (r: typeof dh.meses[number]) => formatMoney(r.total_ventas), align: "right" },
                { header: "Facturas", cell: (r: typeof dh.meses[number]) => String(r.num_facturas), align: "right" },
                { header: "Ticket prom.", cell: (r: typeof dh.meses[number]) => formatMoney(r.ticket_promedio), align: "right" },
              ]}
              data={dh.meses}
              keyFn={(r: typeof dh.meses[number], i: number) => `${r.year}-${r.month}-${i}`}
              striped
            />
          </Card>
        </>
      )}

      {/* ── Forecast ────────────────────────────────────── */}
      {tab === "forecast" && (
        <ForecastChart monthly={df?.monthly ?? []} />
      )}
    </div>
  );
}
