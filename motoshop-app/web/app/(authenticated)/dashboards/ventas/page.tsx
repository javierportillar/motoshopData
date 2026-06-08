"use client";

import { useState } from "react";
import Link from "next/link";
import {
  useSalesSummaryV2,
  useSalesDailyMonth,
  useSalesForecastMonthly,
  useSalesHistorical,
  useSalesTrend,
  useSalesTrendByYear,
} from "@/lib/api/hooks";
import { formatMoney } from "@/lib/format/currency";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Badge } from "@/components/ui/Badge";
import { Table } from "@/components/ui/Table";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import {
  BarChart, Bar, Line, LineChart, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ComposedChart, PieChart, Pie, Cell,
} from "recharts";

const MONTH_NAMES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

type TabView = "mensual" | "diaria" | "historica" | "forecast";
const TAB_LABEL: Record<TabView, string> = { mensual: "Mensual", diaria: "Diaria", historica: "Histórica", forecast: "Forecast" };

// ── Daily evolution chart (bars + accumulated line) ───────────────────

function DailyEvoChart({ days }: { days: { date: string; sales: number; accumulated: number }[] }) {
  const data = days.map(d => ({ label: d.date.slice(8), ventas: d.sales, acumulado: d.accumulated }));
  if (!data.length) return null;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <ComposedChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="label" tick={{ fontSize: 10 }} stroke="#a3a3a3" />
        <YAxis yAxisId="left" tick={{ fontSize: 10 }} stroke="#a3a3a3" tickFormatter={(v: number) => `$${(v/1e3).toFixed(0)}K`} />
        <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} stroke="#2563EB" tickFormatter={(v: number) => `$${(v/1e6).toFixed(1)}M`} />
        <Tooltip contentStyle={{ borderRadius: "8px", fontSize: "12px" }} />
        <Bar yAxisId="left" dataKey="ventas" fill="#7B1818" radius={[2,2,0,0]} name="Ventas día" />
        <Line yAxisId="right" type="monotone" dataKey="acumulado" stroke="#2563EB" strokeWidth={2} dot={false} name="Acumulado" />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ── Daily comparison across years (line chart) ───────────────────────

function DailyYearCompareChart({ curr, prev, prev2, currYear, prevYear, prevYear2 }: {
  curr: { days: { date: string; sales: number; accumulated: number }[] };
  prev?: { days: { date: string; sales: number; accumulated: number }[] };
  prev2?: { days: { date: string; sales: number; accumulated: number }[] };
  currYear: number; prevYear: number; prevYear2: number;
}) {
  // Build aligned data: day 1-31, with values from each year
  const currentMonth = new Date().getMonth() + 1;
  const daysInMonth = new Date(currYear, currentMonth, 0).getDate();
  const data = Array.from({ length: daysInMonth }, (_, i) => ({
    day: i + 1,
    curr: curr.days.find(d => parseInt(d.date.slice(8)) === i + 1)?.sales ?? null,
    currAcc: curr.days.find(d => parseInt(d.date.slice(8)) === i + 1)?.accumulated ?? null,
    prev: prev?.days.find(d => parseInt(d.date.slice(8)) === i + 1)?.sales ?? null,
    prev2: prev2?.days.find(d => parseInt(d.date.slice(8)) === i + 1)?.sales ?? null,
  }));
  const hasPrev = data.some(d => d.prev != null);
  const hasPrev2 = data.some(d => d.prev2 != null);
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="day" tick={{ fontSize: 10 }} stroke="#a3a3a3" label={{ value: "Día del mes", position: "insideBottom", offset: -2, fontSize: 10 }} />
        <YAxis tick={{ fontSize: 10 }} stroke="#a3a3a3" tickFormatter={(v: number) => `$${(v/1e3).toFixed(0)}K`} />
        <Tooltip contentStyle={{ borderRadius: "8px", fontSize: "12px" }} />
        <Line type="monotone" dataKey="curr" stroke="#7B1818" strokeWidth={2} dot={false} name={`${currYear}`} connectNulls={false} />
        {hasPrev && <Line type="monotone" dataKey="prev" stroke="#4B5563" strokeWidth={1.5} dot={false} name={`${prevYear}`} connectNulls={false} strokeDasharray="5 5" />}
        {hasPrev2 && <Line type="monotone" dataKey="prev2" stroke="#94A3B8" strokeWidth={1} dot={false} name={`${prevYear2}`} connectNulls={false} strokeDasharray="3 3" />}
        <Line type="monotone" dataKey="currAcc" stroke="#2563EB" strokeWidth={1.5} dot={false} name="Acumulado" yAxisId="right" connectNulls={false} />
        <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} stroke="#2563EB" tickFormatter={(v: number) => `$${(v/1e6).toFixed(1)}M`} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── Year comparison chart (no future zeros, current year with projection) ─

function YearTrendChart({ currentYear, trendCurrData, trendPrevData, forecast }: {
  currentYear: number;
  trendCurrData: Map<number, number>;
  trendPrevData: Map<number, number>;
  forecast?: { current_month: { month: string; projected_amount: number }; next_month: { month: string; projected_amount: number } };
}) {
  const currentMonth = new Date().getMonth() + 1;
  const labels = MONTH_NAMES;
  const prevData = labels.map((lbl, i) => ({
    label: lbl,
    prev: trendPrevData.get(i + 1) ?? null,
  }));
  const hasPrev = prevData.some(d => d.prev != null && d.prev > 0);

  // Projection: start from last real month, show current and next
  const projectedMap = new Map<number, number>();
  if (forecast) {
    // Anclar la proyección en el último mes con dato real
    const lastRealMonth = currentMonth - 1;
    const lastRealValue = trendCurrData.get(lastRealMonth);
    if (lastRealValue != null) {
      projectedMap.set(lastRealMonth, lastRealValue);
    }
    projectedMap.set(currentMonth, forecast.current_month.projected_amount);
    projectedMap.set(currentMonth + 1, forecast.next_month.projected_amount);
  }

  const data = labels.map((lbl, i) => ({
    label: lbl,
    prev: prevData[i]?.prev ?? null,
    curr: i < currentMonth ? (trendCurrData.get(i + 1) ?? null) : null,
    projected: projectedMap.get(i + 1) ?? null,
  }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="label" tick={{ fontSize: 10 }} stroke="#a3a3a3" />
        <YAxis tick={{ fontSize: 10 }} stroke="#a3a3a3" tickFormatter={(v: number) => `$${(v/1e6).toFixed(1)}M`} />
        <Tooltip contentStyle={{ borderRadius: "8px", fontSize: "12px" }} />
        {hasPrev && <Line type="monotone" dataKey="prev" stroke="#94A3B8" strokeDasharray="5 5" dot={false} name={`${currentYear-1}`} />}
        <Line type="monotone" dataKey="curr" stroke="#7B1818" strokeWidth={2} dot={{ r: 2, fill: "#7B1818" }} name={`${currentYear}`} connectNulls={false} />
        <Line type="monotone" dataKey="projected" stroke="#FCD34D" strokeWidth={2} strokeDasharray="6 3" dot={{ r: 3, fill: "#FCD34D" }} name="Proyección" connectNulls />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── Forecast donut ────────────────────────────────────────────────────

function ForecastDonut({ current, next }: { current: { month: string; projected_amount: number; observed_amount?: number; days_observed?: number; days_total: number; confidence: string }; next: { month: string; projected_amount: number; days_total: number; confidence: string } }) {
  const observed = current.observed_amount ?? 0;
  const projected = current.projected_amount;
  const remaining = projected - observed;
  const donutData = [
    { name: `Real (${current.days_observed}/${current.days_total}d)`, value: observed },
    { name: `Pendiente (${current.days_total - (current.days_observed ?? 0)}d)`, value: Math.max(0, remaining) },
  ];
  const COLORS = ["#7B1818", "#FCD34D"];
  return (
    <div className="grid grid-cols-2 gap-3">
      <Card>
        <Stat
          label={`${current.month} (${current.confidence})`}
          value={formatMoney(projected)}
          subtitle={`${current.days_observed ?? "?"}/${current.days_total} días · ${formatMoney(observed)} real`}
        />
      </Card>
      <Card>
        <Stat
          label={`${next.month} (${next.confidence})`}
          value={formatMoney(next.projected_amount)}
          subtitle={`${next.days_total} días proyectados`}
        />
      </Card>
      <Card header={<h3 className="text-xs font-semibold text-text-primary">Progreso {current.month}</h3>}>
        <ResponsiveContainer width="100%" height={160}>
          <PieChart>
            <Pie data={donutData} cx="50%" cy="50%" innerRadius={40} outerRadius={60} dataKey="value" stroke="none">
              {donutData.map((_, idx) => <Cell key={idx} fill={COLORS[idx]} />)}
            </Pie>
            <Tooltip contentStyle={{ borderRadius: "8px", fontSize: "12px" }} />
          </PieChart>
        </ResponsiveContainer>
        <p className="text-center text-xs text-text-muted -mt-2">
          {((observed / projected) * 100).toFixed(0)}% completado
        </p>
      </Card>
    </div>
  );
}// ── Main ──────────────────────────────────────────────────────────────

export default function VentasPage(): JSX.Element {
  try {
    return <VentasPageInner />;
  } catch (_e) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-accent hover:underline">← Volver a inicio</Link>
        <Card><p className="py-8 text-center text-sm text-text-muted">Error al cargar la página de ventas. Por favor intentá de nuevo.</p></Card>
      </div>
    );
  }
}

function VentasPageInner(): JSX.Element {
  const [tab, setTab] = useState<TabView>("mensual");
  const sales = useSalesSummaryV2();
  const currentMonth = new Date().toISOString().slice(0, 7);
  const currentYear = new Date().getFullYear();
  const salesDaily = useSalesDailyMonth(currentMonth);
  const salesDailyPrev = useSalesDailyMonth(`${currentYear-1}-${new Date().toISOString().slice(5,7)}`);
  const salesDailyPrev2 = useSalesDailyMonth(`${currentYear-2}-${new Date().toISOString().slice(5,7)}`);
  const salesHistorical = useSalesHistorical();
  const forecast = useSalesForecastMonthly();
  const trend = useSalesTrend(12);
  const trendPrev = useSalesTrendByYear(currentYear - 1);

  const isLoading =
    tab === "mensual" ? (sales.isLoading || trend.isLoading || trendPrev.isLoading)
    : tab === "diaria" ? salesDaily.isLoading
    : tab === "forecast" ? forecast.isLoading
    : salesHistorical.isLoading;

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-accent hover:underline">← Volver a inicio</Link>
        <Skeleton className="h-5 w-24" />
        <div className="grid grid-cols-2 gap-3">{[1,2,3,4].map(i => <Skeleton key={i} className="h-24 rounded-xl" />)}</div>
        <Skeleton className="h-60 rounded-xl" />
      </div>
    );
  }

  const d = sales.data!;
  const dm = salesDaily.data;
  const dh = salesHistorical.data;
  const df = forecast.data;

  // Trend maps
  const trendCurrMap = new Map((trend.data?.items ?? []).filter(it => it.year === currentYear).map(it => [it.month, it.total_ventas]));
  const trendPrevMap = new Map((trendPrev.data?.items ?? []).map(it => [it.month, it.total_ventas]));

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">← Volver a inicio</Link>
      <div>
        <h1 className="text-xl font-bold text-text-primary">Ventas</h1>
        <p className="text-sm text-text-muted">{d.max_sales_date ? `Datos hasta ${d.max_sales_date}` : ""}</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 flex-wrap">
        {(["mensual", "diaria", "historica", "forecast"] as TabView[]).map(v => (
          <button key={v} onClick={() => setTab(v)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
              tab === v ? "bg-surface-dark text-text-inverse" : "bg-surface-alt text-text-secondary"
            }`}>{TAB_LABEL[v]}</button>
        ))}
      </div>

      {/* ── MENSUAL (principal) ─────────────────────────── */}
      {tab === "mensual" && (
        <>
          {/* KPIs principales */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Card><Stat label="Ventas acumuladas" value={formatMoney(d.current_month_accumulated)} subtitle={`${d.current_month_days_with_sales} días`} /></Card>
            <Card><Stat label="Facturas" value={d.num_facturas.toLocaleString("es-CO")} subtitle="este mes" /></Card>
            <Card><Stat label="Ticket promedio" value={formatMoney(d.ticket_promedio)} subtitle="por factura" /></Card>
            <Card><Stat
              label="vs mes anterior"
              value={`${d.previous_month_same_window.delta_pct > 0 ? "+" : ""}${d.previous_month_same_window.delta_pct}%`}
              subtitle={`Misma ventana ${d.previous_month_same_window.from.slice(5)}–${d.previous_month_same_window.to.slice(5)}`}
            /></Card>
          </div>

          {/* Evolución diaria del mes */}
          {dm && dm.days.length > 0 && (
            <Card header={<h2 className="font-semibold text-text-primary">Evolución diaria — {currentMonth}</h2>}>
              <DailyEvoChart days={dm.days} />
            </Card>
          )}

          {/* Comparativa diaria entre años */}
          <Card header={<h2 className="font-semibold text-text-primary">Comparativa diaria: {currentYear} vs años anteriores</h2>}>
            <div className="flex items-center gap-4 mb-2 text-xs text-text-muted">
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{background:"#7B1818"}} /> {currentYear}</span>
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{background:"#4B5563"}} /> {currentYear-1}</span>
              {salesDailyPrev2.data?.total_days_with_sales ? <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{background:"#94A3B8"}} /> {currentYear-2}</span> : null}
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{background:"#2563EB"}} /> Acum. {currentYear}</span>
            </div>
            {dm?.days ? (
              <DailyYearCompareChart
                curr={{ days: dm.days }}
                prev={salesDailyPrev.data?.days ? { days: salesDailyPrev.data.days } : undefined}
                prev2={salesDailyPrev2.data?.days ? { days: salesDailyPrev2.data.days } : undefined}
                currYear={currentYear} prevYear={currentYear-1} prevYear2={currentYear-2}
              />
            ) : <Skeleton className="h-60 rounded-xl" />}
          </Card>

          {/* Tendencia año actual vs anterior */}
          <Card header={<h2 className="font-semibold text-text-primary">Año actual vs anterior</h2>}>
            <div className="flex items-center gap-4 mb-2 text-xs text-text-muted">
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{background:"#7B1818"}} /> {currentYear}</span>
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{background:"#4B5563"}} /> {currentYear-1}</span>
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{background:"#FCD34D"}} /> Proyección</span>
            </div>
            <YearTrendChart currentYear={currentYear} trendCurrData={trendCurrMap} trendPrevData={trendPrevMap}
              forecast={df ? { current_month: df.current_month, next_month: df.next_month } : undefined} />
          </Card>

          {/* Tabla detalle mensual */}

        </>
      )}

      {/* ── DIARIA ──────────────────────────────────────── */}
      {tab === "diaria" && dm && (
        <>
          <div className="grid grid-cols-3 gap-3">
            <Card><Stat label="Total mes" value={formatMoney(dm.days[dm.days.length-1]?.accumulated ?? 0)} subtitle={dm.total_days_with_sales + " días"} /></Card>
            <Card><Stat label="Promedio" value={formatMoney(dm.days.length > 0 ? ((dm.days[dm.days.length-1]?.accumulated ?? 0) / dm.total_days_with_sales) : 0)} subtitle="por día con ventas" /></Card>
            <Card><Stat label="Mejor día" value={formatMoney(Math.max(...dm.days.map(x => x.sales), 0))} /></Card>
          </div>
          <Card header={<h2 className="font-semibold text-text-primary">Ventas diarias</h2>}>
            <DailyEvoChart days={dm.days} />
          </Card>
          <Card header={<h2 className="font-semibold text-text-primary">Detalle diario</h2>}>
            <Table
              columns={[
                { header: "Día", cell: (r: typeof dm.days[number]) => r.date.slice(8) },
                { header: "Ventas", cell: (r: typeof dm.days[number]) => formatMoney(r.sales), align: "right" },
                { header: "Facturas", cell: (r: typeof dm.days[number]) => String(r.invoices), align: "right" },
                { header: "Acumulado", cell: (r: typeof dm.days[number]) => formatMoney(r.accumulated), align: "right" },
                { header: "Ticket", cell: (r: typeof dm.days[number]) => formatMoney(r.avg_ticket), align: "right" },
              ]}
              data={dm.days} keyFn={(r: typeof dm.days[number]) => r.date} striped
            />
          </Card>
        </>
      )}

      {/* ── HISTÓRICA ──────────────────────────────────── */}
      {tab === "historica" && dh && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <Card><Stat label="Total histórico" value={formatMoney(dh.total_ventas)} /></Card>
            <Card><Stat label="Facturas" value={dh.total_facturas.toLocaleString("es-CO")} /></Card>
          </div>
          <Card header={<h2 className="font-semibold text-text-primary">Tendencia mensual</h2>}>
            {dh.meses.length > 0 ? (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={dh.meses.map(m => ({ month: `${MONTH_NAMES[m.month-1] ?? ""} ${m.year}`, ventas: m.total_ventas }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="month" tick={{ fontSize: 8, angle: -45, textAnchor: "end" }} stroke="#a3a3a3" height={50} />
                  <YAxis tick={{ fontSize: 10 }} stroke="#a3a3a3" tickFormatter={(v: number) => `$${(v/1e6).toFixed(1)}M`} />
                  <Tooltip contentStyle={{ borderRadius: "8px", fontSize: "12px" }} />
                  <Bar dataKey="ventas" fill="#7B1818" radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <p className="py-6 text-sm text-text-muted text-center">Sin datos históricos.</p>}
          </Card>
          {dh && (
            <Card header={<h2 className="font-semibold text-text-primary">Histórico mensual</h2>}>
              <Table
                columns={[
                  { header: "Mes", cell: (r: typeof dh.meses[number]) => `${MONTH_NAMES[r.month-1] ?? ""} ${r.year}` },
                  { header: "Ventas", cell: (r: typeof dh.meses[number]) => formatMoney(r.total_ventas), align: "right" },
                  { header: "Facturas", cell: (r: typeof dh.meses[number]) => String(r.num_facturas), align: "right" },
                  { header: "Ticket", cell: (r: typeof dh.meses[number]) => formatMoney(r.ticket_promedio), align: "right" },
                ]}
                data={dh.meses.slice(-24)} keyFn={(r: typeof dh.meses[number]) => `${r.year}-${r.month}`} striped
              />
            </Card>
          )}
        </>
      )}

      {/* ── FORECAST ───────────────────────────────────── */}
      {tab === "forecast" && df && (
        <>
          <ForecastDonut current={df.current_month} next={df.next_month} />
          <Card header={<h2 className="font-semibold text-text-primary">Proyección</h2>}>
            {(() => {
              const data = [
                { label: df.current_month.month.slice(5), real: df.current_month.observed_amount ?? 0, proyectado: df.current_month.projected_amount - (df.current_month.observed_amount ?? 0) },
                { label: df.next_month.month.slice(5), real: 0, proyectado: df.next_month.projected_amount },
              ];
              return (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={data}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="label" tick={{ fontSize: 10 }} stroke="#a3a3a3" />
                    <YAxis tick={{ fontSize: 10 }} stroke="#a3a3a3" tickFormatter={(v: number) => `$${(v/1e6).toFixed(1)}M`} />
                    <Tooltip contentStyle={{ borderRadius: "8px", fontSize: "12px" }} />
                    <Bar dataKey="real" fill="#7B1818" stackId="a" radius={[4,4,0,0]} name="Real" />
                    <Bar dataKey="proyectado" fill="#FCD34D" stackId="a" radius={[4,4,0,0]} name="Proyectado" />
                  </BarChart>
                </ResponsiveContainer>
              );
            })()}
            <p className="text-xs text-text-muted mt-1">Modelo: {df.model_version} · Drivers: {(df.drivers ?? []).join(", ")}</p>
          </Card>
        </>
      )}
    </div>
  );
}
