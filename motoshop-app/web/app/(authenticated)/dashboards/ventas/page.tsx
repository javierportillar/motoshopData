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
import { Table } from "@/components/ui/Table";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  LineChart, Line, BarChart, Bar, ComposedChart,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from "recharts";

const MONTHS = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
type Tab = "mensual" | "diaria" | "historica" | "forecast";

export default function VentasPage(): JSX.Element {
  const [tab, setTab] = useState<Tab>("mensual");
  const sales = useSalesSummaryV2();
  const cm = new Date().toISOString().slice(0, 7);
  const cy = new Date().getFullYear();
  const daily = useSalesDailyMonth(cm);
  const dailyPrev = useSalesDailyMonth(`${cy-1}-${cm.slice(5)}`);
  const hist = useSalesHistorical();
  const fc = useSalesForecastMonthly();
  const trend = useSalesTrend(24);
  const trendPrev = useSalesTrendByYear(cy - 1);

  const d = sales.data;
  const dm = daily.data;
  const dp = dailyPrev.data;
  const dh = hist.data;
  const df = fc.data;

  const trendCurr = new Map((trend.data?.items??[]).filter(i=>i.year===cy).map(i=>[i.month,i.total_ventas]));
  const trendP = new Map((trendPrev.data?.items??[]).map(i=>[i.month,i.total_ventas]));

  if (!d) return <div className="p-4"><Skeleton className="h-60 rounded-xl" /></div>;

  const tabs: Tab[] = ["mensual","diaria","historica","forecast"];
  const labels: Record<Tab,string> = {mensual:"Mensual",diaria:"Diaria",historica:"Histórica",forecast:"Forecast"};

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">← Volver a inicio</Link>
      <div><h1 className="text-xl font-bold text-text-primary">Ventas</h1><p className="text-sm text-text-muted">Datos hasta {d.max_sales_date}</p></div>
      <div className="flex gap-2 flex-wrap">{tabs.map(v=>(<button key={v} onClick={()=>setTab(v)} className={`rounded-lg px-3 py-1.5 text-xs font-medium ${tab===v?"bg-surface-dark text-text-inverse":"bg-surface-alt text-text-secondary"}`}>{labels[v]}</button>))}</div>

      {tab === "mensual" && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Card><Stat label="Ventas acumuladas" value={formatMoney(d.current_month_accumulated)} subtitle={`${d.current_month_days_with_sales} días`} /></Card>
            <Card><Stat label="Facturas" value={d.num_facturas.toLocaleString("es-CO")} subtitle="este mes" /></Card>
            <Card><Stat label="Ticket promedio" value={formatMoney(d.ticket_promedio)} subtitle="por factura" /></Card>
            <Card><Stat label="vs mes anterior" value={`${d.previous_month_same_window.delta_pct>0?"+":""}${d.previous_month_same_window.delta_pct}%`} subtitle="misma ventana" /></Card>
          </div>

          {/* Evolución diaria */}
          {dm && <Card header={<h2 className="font-semibold text-text-primary">Evolución diaria — {cm}</h2>}>
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={dm.days.map(d=>({label:d.date.slice(8),ventas:d.sales,acumulado:d.accumulated}))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="label" tick={{fontSize:10}} stroke="#a3a3a3" />
                <YAxis yAxisId="left" tick={{fontSize:10}} stroke="#a3a3a3" tickFormatter={(v:number)=>`$${(v/1e3).toFixed(0)}K`} />
                <YAxis yAxisId="right" orientation="right" tick={{fontSize:10}} stroke="#2563EB" tickFormatter={(v:number)=>`$${(v/1e6).toFixed(1)}M`} />
                <Tooltip contentStyle={{borderRadius:"8px",fontSize:"12px"}} />
                <Bar yAxisId="left" dataKey="ventas" fill="#7B1818" radius={[2,2,0,0]} />
                <Line yAxisId="right" type="monotone" dataKey="acumulado" stroke="#2563EB" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </Card>}

          {/* Comparativa diaria entre años */}
          {dm && <Card header={<h2 className="font-semibold text-text-primary">Comparativa diaria: {cy} vs {cy-1}</h2>}>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={Array.from({length:31},(_,i)=>({
                day:i+1,
                curr: dm.days.find(d=>parseInt(d.date.slice(8))===i+1)?.sales??null,
                prev: dp?.days.find(d=>parseInt(d.date.slice(8))===i+1)?.sales??null,
                currAcc: dm.days.find(d=>parseInt(d.date.slice(8))===i+1)?.accumulated??null,
              }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="day" tick={{fontSize:10}} stroke="#a3a3a3" />
                <YAxis tick={{fontSize:10}} stroke="#a3a3a3" tickFormatter={(v:number)=>`$${(v/1e3).toFixed(0)}K`} />
                <Tooltip contentStyle={{borderRadius:"8px",fontSize:"12px"}} />
                <Line type="monotone" dataKey="curr" stroke="#7B1818" strokeWidth={2} dot={false} name={`${cy}`} connectNulls={false} />
                <Line type="monotone" dataKey="prev" stroke="#4B5563" strokeWidth={1.5} strokeDasharray="5 5" dot={false} name={`${cy-1}`} connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
            <div className="flex items-center gap-4 mt-1 text-xs text-text-muted">
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{background:"#7B1818"}} /> {cy}</span>
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{background:"#4B5563"}} /> {cy-1}</span>
            </div>
          </Card>}

          {/* Año actual vs anterior */}
          <Card header={<h2 className="font-semibold text-text-primary">Año actual vs anterior</h2>}>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={MONTHS.map((lbl,i)=>{
                const m=i+1;
                const cm2=new Date().getMonth()+1;
                return {
                  label:lbl,
                  prev:trendP.get(m)??null,
                  curr:m<cm2?(trendCurr.get(m)??null):null,
                  proj:m>=cm2?(df?m===cm2?df.current_month.projected_amount:m===cm2+1?df.next_month.projected_amount:null:null):null,
                };
              })}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="label" tick={{fontSize:10}} stroke="#a3a3a3" />
                <YAxis tick={{fontSize:10}} stroke="#a3a3a3" tickFormatter={(v:number)=>`$${(v/1e6).toFixed(1)}M`} />
                <Tooltip contentStyle={{borderRadius:"8px",fontSize:"12px"}} />
                <Line type="monotone" dataKey="prev" stroke="#94A3B8" strokeDasharray="5 5" dot={false} name={`${cy-1}`} />
                <Line type="monotone" dataKey="curr" stroke="#7B1818" strokeWidth={2} dot={{r:2,fill:"#7B1818"}} name={`${cy}`} connectNulls={false} />
                <Line type="monotone" dataKey="proj" stroke="#FCD34D" strokeWidth={2} strokeDasharray="6 3" dot={{r:3,fill:"#FCD34D"}} name="Proyección" connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        </>
      )}

      {tab === "diaria" && dm && (
        <Card header={<h2 className="font-semibold text-text-primary">Detalle diario — {cm}</h2>}>
          <Table columns={[
            {header:"Día",cell:(r:typeof dm.days[number])=>r.date.slice(8)},
            {header:"Ventas",cell:(r:typeof dm.days[number])=>formatMoney(r.sales),align:"right"},
            {header:"Facturas",cell:(r:typeof dm.days[number])=>String(r.invoices),align:"right"},
            {header:"Acumulado",cell:(r:typeof dm.days[number])=>formatMoney(r.accumulated),align:"right"},
            {header:"Ticket",cell:(r:typeof dm.days[number])=>formatMoney(r.avg_ticket),align:"right"},
          ]} data={dm.days} keyFn={(r:typeof dm.days[number])=>r.date} striped />
        </Card>
      )}

      {tab === "historica" && dh && (
        <>
          <Card header={<h2 className="font-semibold text-text-primary">Tendencia histórica</h2>}>
            {dh.meses.length > 0 ? (
              <ResponsiveContainer width="100%" height={320}>
                <ComposedChart data={(() => {
                  const data: { month: string; ventas: number; tendencia: number | null; proy: number | null }[] = dh.meses.map(m => ({
                    month: `${MONTHS[m.month-1]??""} ${String(m.year).slice(2)}`,
                    ventas: m.total_ventas,
                    tendencia: m.total_ventas,
                    proy: null,
                  }));
                  if (df) {
                    const cmIdx = data.findIndex(d => d.month === `${MONTHS[new Date().getMonth()]??""} ${String(cy).slice(2)}`);
                    if (cmIdx >= 0) {
                      const actual = data[cmIdx]!.ventas;
                      data[cmIdx]!.proy = df.current_month.projected_amount - actual;
                    }
                    data.push({
                      month: `${MONTHS[new Date().getMonth()+1]??""} ${String(cy).slice(2)}`,
                      ventas: 0, tendencia: null, proy: df.next_month.projected_amount,
                    });
                  }
                  return data;
                })()}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="month" tick={{ fontSize: 7, angle: -60, textAnchor: "end" }} stroke="#a3a3a3" height={70} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 10 }} stroke="#a3a3a3" tickFormatter={(v: number) => `$${(v/1e6).toFixed(1)}M`} />
                  <Tooltip contentStyle={{ borderRadius: "8px", fontSize: "12px" }} />
                  <Bar dataKey="ventas" fill="#7B1818" stackId="a" radius={[2,2,0,0]} name="Real" />
                  <Bar dataKey="proy" fill="#FCD34D" stackId="a" radius={[2,2,0,0]} name="Proyección" />
                  <Line type="monotone" dataKey="tendencia" stroke="#7B1818" strokeWidth={1.5} dot={false} name="Tendencia" connectNulls />
                </ComposedChart>
              </ResponsiveContainer>
            ) : <p className="py-6 text-sm text-text-muted text-center">Sin datos históricos.</p>}
            <div className="flex items-center gap-4 mt-2 text-xs text-text-muted">
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{background:"#7B1818"}} /> Real</span>
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{background:"#FCD34D"}} /> Proyección</span>
            </div>
          </Card>
          <Card header={<h2 className="font-semibold text-text-primary">Histórico mensual</h2>}>
            <Table columns={[
              {header:"Mes",cell:(r:typeof dh.meses[number])=>`${MONTHS[r.month-1]??""} ${r.year}`},
              {header:"Ventas",cell:(r:typeof dh.meses[number])=>formatMoney(r.total_ventas),align:"right"},
              {header:"Facturas",cell:(r:typeof dh.meses[number])=>String(r.num_facturas),align:"right"},
              {header:"Ticket",cell:(r:typeof dh.meses[number])=>formatMoney(r.ticket_promedio),align:"right"},
            ]} data={dh.meses} keyFn={(r:typeof dh.meses[number])=>`${r.year}-${r.month}`} striped />
          </Card>
        </>
      )}

      {tab === "forecast" && df && (
        <Card header={<h2 className="font-semibold text-text-primary">Proyección</h2>}>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <Card><Stat label={df.current_month.month} value={formatMoney(df.current_month.projected_amount)} subtitle={`${df.current_month.days_observed}/${df.current_month.days_total}d · ${formatMoney(df.current_month.observed_amount??0)} real`} /></Card>
            <Card><Stat label={df.next_month.month} value={formatMoney(df.next_month.projected_amount)} subtitle={`${df.next_month.days_total} días (${df.next_month.confidence})`} /></Card>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={[
              {label:df.current_month.month.slice(5),real:df.current_month.observed_amount??0,proy:df.current_month.projected_amount-(df.current_month.observed_amount??0)},
              {label:df.next_month.month.slice(5),real:0,proy:df.next_month.projected_amount},
            ]}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="label" tick={{fontSize:10}} stroke="#a3a3a3" />
              <YAxis tick={{fontSize:10}} stroke="#a3a3a3" tickFormatter={(v:number)=>`$${(v/1e6).toFixed(1)}M`} />
              <Tooltip contentStyle={{borderRadius:"8px",fontSize:"12px"}} />
              <Bar dataKey="real" fill="#7B1818" stackId="a" radius={[4,4,0,0]} />
              <Bar dataKey="proy" fill="#FCD34D" stackId="a" radius={[4,4,0,0]} />
            </BarChart>
          </ResponsiveContainer>
          <p className="text-xs text-text-muted mt-1">Modelo: {df.model_version}</p>
        </Card>
      )}
    </div>
  );
}
