"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useInventorySummary, useInventoryDetail, useInventoryDiscrepancies } from "@/lib/api/hooks";
import { formatMoney } from "@/lib/format/currency";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Badge } from "@/components/ui/Badge";
import { Table } from "@/components/ui/Table";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";

// ── Helpers ──────────────────────────────────────────────────────────

function fmt(n: number): string { return n >= 1_000_000 ? `${(n/1e6).toFixed(1)}M` : n >= 1_000 ? `${(n/1e3).toFixed(0)}K` : String(n); }
const PIE_COLORS = ["#7B1818","#4B5563","#F59E0B","#2563EB","#16A34A"];

// ── Filter types ──────────────────────────────────────────────────────

type StockFilter = "all" | "with" | "without";
type DormFilter = "all" | "dormant" | "active";
type SortField = "valor" | "stock" | "dias";

// ── Main Page ─────────────────────────────────────────────────────────

export default function InventarioPage(): JSX.Element {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [stockFilter, setStockFilter] = useState<StockFilter>("all");
  const [dormFilter, setDormFilter] = useState<DormFilter>("all");
  const [abcFilter, setAbcFilter] = useState<string>("");
  const [sortBy, setSortBy] = useState<SortField>("valor");

  const { data: summary } = useInventorySummary();
  const { data: detail, isLoading: detailLoading } = useInventoryDetail(page, 30, search || undefined, undefined, sortBy);
  const { data: discrep } = useInventoryDiscrepancies();

  const items = detail?.items ?? [];
  const total = detail?.total ?? 0;

  // Apply client-side filters (simpler than server params for stock/dorm/abc)
  const filtered = useMemo(() => {
    let result = items;
    if (stockFilter === "with") result = result.filter(i => i.stock_actual > 0);
    if (stockFilter === "without") result = result.filter(i => i.stock_actual === 0);
    if (dormFilter === "dormant") result = result.filter(i => i.es_dormido);
    if (dormFilter === "active") result = result.filter(i => !i.es_dormido);
    if (abcFilter) result = result.filter(i => i.abc === abcFilter);
    return result;
  }, [items, stockFilter, dormFilter, abcFilter]);

  // Chart data
  const topPorValor = useMemo(() => [...(detail?.items ?? [])].sort((a,b)=>b.valor_inventario-a.valor_inventario).slice(0,10), [detail]);
  const topPorUnidades = useMemo(() => [...(detail?.items ?? [])].sort((a,b)=>b.stock_actual-a.stock_actual).slice(0,10), [detail]);
  const bodegaData = (summary?.por_bodega ?? []).map(b => ({ name: b.nom_bodega?.slice(0,15) ?? b.cod_bodega, value: b.cantidad }));
  const dormidosCount = items.filter(i => i.es_dormido).length;

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">← Volver a inicio</Link>
      <div>
        <h1 className="text-xl font-bold text-text-primary">Inventario</h1>
        <p className="text-sm text-text-muted">{summary ? `${summary.num_productos} SKUs · ${detail?.total ?? "?"} productos` : "Cargando..."}</p>
      </div>

      {/* KPIs */}
      {!summary ? <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{[1,2,3,4].map(i=><Skeleton key={i} className="h-24 rounded-xl"/>)}</div> : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Card><Stat label="SKUs totales" value={String(summary.num_productos)} subtitle="en catálogo" /></Card>
          <Card><Stat label="Unidades físicas" value={fmt(summary.stock_total)} subtitle="stock real" /></Card>
          <Card><Stat label="Valor inventario" value={formatMoney(summary.valor_total)} subtitle="a costo" /></Card>
          <Card><Stat label="Dormidos con stock" value={detailLoading ? "..." : fmt(dormidosCount)} subtitle="+90 días sin venta" /></Card>
        </div>
      )}

      {/* Discrepancy warning */}
      {discrep?.summary && !discrep.summary.invariant_ok && (
        <Card className="border-warning">
          <div className="flex items-start gap-2">
            <span className="text-lg">⚠️</span>
            <div className="text-xs">
              <p className="font-semibold text-warning">Datos de dormidos pendientes de rebuild del pipeline</p>
              <p className="text-text-muted">Stock físico = unidades reales disponibles. Dormidos = SKUs sin venta reciente. No son la misma métrica.</p>
              <p className="text-text-muted mt-1">{discrep.summary.invariant_msg}</p>
            </div>
          </div>
        </Card>
      )}

      {/* Reconciliation card */}
      <Card>
        <div className="flex items-start gap-2">
          <span className="text-lg">ℹ️</span>
          <div className="text-xs">
            <p className="font-semibold text-text-primary">Reconciliación</p>
            <p className="text-text-muted">Stock físico ({fmt(summary?.stock_total ?? 0)} u) = unidades reales disponibles. Dormidos = SKUs sin venta reciente. No son la misma métrica. Un SKU dormido puede tener o no tener stock.</p>
          </div>
        </div>
      </Card>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <input type="text" placeholder="Buscar SKU o producto..." value={search} onChange={e=>{setSearch(e.target.value);setPage(1)}}
          className="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs text-text-primary w-full sm:w-auto sm:flex-1" />
        <select value={stockFilter} onChange={e=>setStockFilter(e.target.value as StockFilter)}
          className="rounded-lg border border-border bg-surface px-2 py-1.5 text-xs text-text-primary">
          <option value="all">Todo stock</option><option value="with">Con stock</option><option value="without">Sin stock</option>
        </select>
        <select value={dormFilter} onChange={e=>setDormFilter(e.target.value as DormFilter)}
          className="rounded-lg border border-border bg-surface px-2 py-1.5 text-xs text-text-primary">
          <option value="all">Todos</option><option value="dormant">Dormidos</option><option value="active">Activos</option>
        </select>
        <select value={abcFilter} onChange={e=>setAbcFilter(e.target.value)}
          className="rounded-lg border border-border bg-surface px-2 py-1.5 text-xs text-text-primary">
          <option value="">ABC: Todo</option><option value="A">A</option><option value="B">B</option><option value="C">C</option>
        </select>
        <select value={sortBy} onChange={e=>setSortBy(e.target.value as SortField)}
          className="rounded-lg border border-border bg-surface px-2 py-1.5 text-xs text-text-primary">
          <option value="valor">Por valor</option><option value="stock">Por stock</option><option value="dias">Por días sin venta</option>
        </select>
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {topPorValor.length > 0 && (
          <Card header={<h3 className="text-xs font-semibold text-text-primary">Top 10 por valor inventario</h3>}>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={topPorValor.map(p=>({name:p.cod_producto.slice(0,10),valor:p.valor_inventario}))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0"/>
                <XAxis dataKey="name" tick={{fontSize:7}} stroke="#a3a3a3" />
                <YAxis tick={{fontSize:9}} stroke="#a3a3a3" tickFormatter={(v:number)=>`$${(v/1e3).toFixed(0)}K`} />
                <Tooltip contentStyle={{borderRadius:"8px",fontSize:"12px"}} />
                <Bar dataKey="valor" fill="#7B1818" radius={[3,3,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        )}
        {bodegaData.length > 0 && (
          <Card header={<h3 className="text-xs font-semibold text-text-primary">Distribución por bodega</h3>}>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={bodegaData} cx="50%" cy="50%" innerRadius={40} outerRadius={70} dataKey="value" stroke="none" nameKey="name" label={({percent}: any) => percent ? `${(percent*100).toFixed(0)}%` : ''}>
                  {bodegaData.map((_,i)=><Cell key={i} fill={PIE_COLORS[i%PIE_COLORS.length]}/>)}
                </Pie>
                <Tooltip contentStyle={{borderRadius:"8px",fontSize:"12px"}}/>
              </PieChart>
            </ResponsiveContainer>
          </Card>
        )}
      </div>

      {/* Product table */}
      <Card header={<h2 className="font-semibold text-text-primary">Productos en inventario ({total})</h2>}>
        {detailLoading ? (
          <div className="space-y-2">{[1,2,3,4,5].map(i=><Skeleton key={i} className="h-10 rounded-lg"/>)}</div>
        ) : filtered.length === 0 ? (
          <p className="py-8 text-center text-sm text-text-muted">Sin productos con los filtros seleccionados.</p>
        ) : (
          <div className="overflow-x-auto">
            <Table
              columns={[
                { header: "SKU", cell: (r: typeof items[number]) => <span className="font-mono text-[0.625rem]">{r.cod_producto}</span> },
                { header: "Producto", cell: (r: typeof items[number]) => <span className="text-xs">{r.nom_producto?.slice(0,50)}</span> },
                { header: "Bodega", cell: (r: typeof items[number]) => <span className="text-xs">{r.nom_bodega?.slice(0,12)||r.cod_bodega}</span> },
                { header: "Stock", cell: (r: typeof items[number]) => <span className="text-xs font-medium">{r.stock_actual}</span>, align: "right" },
                { header: "Costo", cell: (r: typeof items[number]) => <span className="text-xs">{formatMoney(r.costo_unitario)}</span>, align: "right" },
                { header: "Valor", cell: (r: typeof items[number]) => <span className="text-xs">{formatMoney(r.valor_inventario)}</span>, align: "right" },
                { header: "Últ. venta", cell: (r: typeof items[number]) => <span className="text-xs">{r.ultima_venta??"—"}</span> },
                { header: "Días", cell: (r: typeof items[number]) => <span className={`text-xs ${r.dias_sin_venta>90?"text-error":"text-text-muted"}`}>{r.dias_sin_venta??"—"}</span>, align: "right" },
                { header: "Dormido", cell: (r: typeof items[number]) => <Badge variant={r.es_dormido?"error":"success"} size="sm">{r.es_dormido?"Sí":"No"}</Badge> },
                { header: "ABC", cell: (r: typeof items[number]) => <Badge variant={r.abc==="A"?"success":r.abc==="B"?"warning":"default"} size="sm">{r.abc}</Badge> },
              ]}
              data={filtered} keyFn={(r: typeof items[number])=>r.cod_producto} striped
            />
          </div>
        )}
        {/* Pagination */}
        {total > 30 && (
          <div className="flex items-center justify-between mt-2">
            <button onClick={()=>setPage(p=>Math.max(1,p-1))} disabled={page<=1}
              className="rounded-lg bg-surface-alt px-3 py-1 text-xs text-text-secondary disabled:opacity-30">← Anterior</button>
            <span className="text-xs text-text-muted">Pág {page} de {Math.ceil(total/30)}</span>
            <button onClick={()=>setPage(p=>p+1)} disabled={page*30>=total}
              className="rounded-lg bg-surface-alt px-3 py-1 text-xs text-text-secondary disabled:opacity-30">Siguiente →</button>
          </div>
        )}
      </Card>
    </div>
  );
}
