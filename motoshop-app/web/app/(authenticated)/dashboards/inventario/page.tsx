"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  useInventoryDetail,
  useInventoryDiscrepancies,
  useInventorySummary,
} from "@/lib/api/hooks";
import { formatMoney } from "@/lib/format/currency";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { Stat } from "@/components/ui/Stat";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

// ── Types ─────────────────────────────────────────────────────────────

type StockFilter = "todos" | "con_stock" | "sin_stock";
type DormidoFilter = "todos" | "true" | "false";
type SortField =
  | "valor_inventario"
  | "stock_actual"
  | "costo_unitario"
  | "dias_sin_venta"
  | "ultima_venta"
  | "abc"
  | "nom_producto";

type InventoryItem = {
  cod_producto: string;
  nom_producto: string;
  cod_bodega: string;
  nom_bodega: string;
  stock_actual: number;
  costo_unitario: number;
  valor_inventario: number;
  ultima_venta: string | null;
  dias_sin_venta: number;
  es_dormido: boolean;
  abc: string;
};

type LeaderboardMetric = "stock" | "value" | "cost" | "days";

const PIE_COLORS = ["#7B1818", "#D97706", "#334155", "#2563EB", "#16A34A"];
const ABC_COLORS: Record<string, string> = { A: "#16A34A", B: "#D97706", C: "#64748B" };

// ── Helpers ───────────────────────────────────────────────────────────

function compactNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString("es-CO");
}

function toNumber(value: unknown): number {
  return typeof value === "number" ? value : Number(value ?? 0);
}

function stockLabel(qty: number): string {
  return `${qty.toLocaleString("es-CO")} ${qty === 1 ? "unidad" : "unidades"}`;
}

function daysLabel(days: number): string {
  if (days >= 99999) return "Sin venta registrada";
  if (days === 1) return "1 día";
  return `${days.toLocaleString("es-CO")} días`;
}

function productShort(name: string, max = 54): string {
  return name.length > max ? `${name.slice(0, max).trim()}…` : name;
}

function productInitial(name: string): string {
  const first = name.trim().charAt(0);
  return first ? first.toUpperCase() : "#";
}

function metricValue(item: InventoryItem, metric: LeaderboardMetric): number {
  if (metric === "stock") return item.stock_actual;
  if (metric === "cost") return item.costo_unitario;
  if (metric === "days") return item.dias_sin_venta;
  return item.valor_inventario;
}

function metricLabel(item: InventoryItem, metric: LeaderboardMetric): string {
  if (metric === "stock") return stockLabel(item.stock_actual);
  if (metric === "cost") return formatMoney(item.costo_unitario);
  if (metric === "days") return daysLabel(item.dias_sin_venta);
  return formatMoney(item.valor_inventario);
}

function StockBadge({ qty }: { qty: number }): JSX.Element {
  if (qty === 0) return <Badge variant="error" size="sm">Sin stock</Badge>;
  if (qty === 1) return <Badge variant="warning" size="sm">1 unidad</Badge>;
  return <Badge variant="success" size="sm">{qty.toLocaleString("es-CO")} uds</Badge>;
}

function SegmentedButton<T extends string>({
  active,
  value,
  children,
  onClick,
}: {
  active: T;
  value: T;
  children: string;
  // eslint-disable-next-line no-unused-vars
  onClick: (value: T) => void;
}): JSX.Element {
  return (
    <button
      type="button"
      onClick={() => onClick(value)}
      className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-all ${
        active === value
          ? "bg-surface-dark text-text-inverse shadow-sm"
          : "bg-surface-alt text-text-secondary hover:bg-surface-dark/10"
      }`}
    >
      {children}
    </button>
  );
}

function LeaderboardCard({
  title,
  subtitle,
  badge,
  items,
  metric,
  accent,
}: {
  title: string;
  subtitle: string;
  badge: string;
  items: InventoryItem[];
  metric: LeaderboardMetric;
  accent: string;
}): JSX.Element {
  const maxValue = Math.max(...items.map((item) => metricValue(item, metric)), 1);

  return (
    <Card
      className="overflow-hidden"
      header={
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="font-bold text-text-primary">{title}</h2>
            <p className="text-xs font-normal text-text-muted">{subtitle}</p>
          </div>
          <Badge variant="info" size="sm">{badge}</Badge>
        </div>
      }
    >
      <div className="space-y-2.5">
        {items.map((item, index) => {
          const value = metricValue(item, metric);
          const pct = Math.max(7, Math.round((value / maxValue) * 100));
          return (
            <article key={`${title}-${item.cod_producto}-${index}`} className="group rounded-2xl border border-border bg-surface-alt/50 p-3 transition-all hover:-translate-y-0.5 hover:bg-surface hover:shadow-md">
              <div className="flex items-start gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-xs font-black text-white" style={{ backgroundColor: accent }}>
                  {index + 1}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-mono text-[0.68rem] font-semibold text-primary">{item.cod_producto}</p>
                    <Badge variant={item.abc === "A" ? "success" : item.abc === "B" ? "warning" : "default"} size="sm">ABC {item.abc}</Badge>
                    {item.es_dormido && <Badge variant="error" size="sm">Dormido</Badge>}
                  </div>
                  <p className="mt-1 text-sm font-bold leading-snug text-text-primary" title={item.nom_producto}>{productShort(item.nom_producto, 70)}</p>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-border">
                    <div className="h-full rounded-full transition-all group-hover:opacity-80" style={{ width: `${pct}%`, backgroundColor: accent }} />
                  </div>
                </div>
                <p className="shrink-0 text-right text-sm font-black text-text-primary">{metricLabel(item, metric)}</p>
              </div>
            </article>
          );
        })}
      </div>
    </Card>
  );
}

function ProductCard({ item }: { item: InventoryItem }): JSX.Element {
  return (
    <article className="rounded-2xl border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-[0.68rem] uppercase tracking-[0.18em] text-primary">
            {item.cod_producto}
          </p>
          <h3 className="mt-1 text-sm font-bold leading-snug text-text-primary">
            {item.nom_producto}
          </h3>
        </div>
        <StockBadge qty={item.stock_actual} />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-xl bg-surface-alt p-2">
          <p className="text-text-muted">Valor</p>
          <p className="font-semibold text-text-primary">{formatMoney(item.valor_inventario)}</p>
        </div>
        <div className="rounded-xl bg-surface-alt p-2">
          <p className="text-text-muted">Costo</p>
          <p className="font-semibold text-text-primary">{formatMoney(item.costo_unitario)}</p>
        </div>
        <div className="rounded-xl bg-surface-alt p-2">
          <p className="text-text-muted">Última venta</p>
          <p className="font-semibold text-text-primary">{item.ultima_venta ?? "—"}</p>
        </div>
        <div className="rounded-xl bg-surface-alt p-2">
          <p className="text-text-muted">Sin venta</p>
          <p className="font-semibold text-text-primary">{daysLabel(item.dias_sin_venta)}</p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <Badge variant={item.es_dormido ? "error" : "success"} size="sm">
          {item.es_dormido ? "Dormido" : "Activo"}
        </Badge>
        <Badge variant={item.abc === "A" ? "success" : item.abc === "B" ? "warning" : "default"} size="sm">
          ABC {item.abc}
        </Badge>
      </div>
    </article>
  );
}

function ProductTable({ items }: { items: InventoryItem[] }): JSX.Element {
  return (
    <div className="hidden overflow-hidden rounded-2xl border border-border bg-surface shadow-sm md:block">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1080px] text-sm">
          <thead>
            <tr className="border-b border-border bg-surface-alt text-left text-[0.68rem] uppercase tracking-[0.16em] text-text-muted">
              <th className="px-4 py-3">SKU</th>
              <th className="px-4 py-3">Producto</th>
              <th className="px-4 py-3 text-right">Cantidad</th>
              <th className="px-4 py-3 text-right">Costo</th>
              <th className="px-4 py-3 text-right">Valor</th>
              <th className="px-4 py-3">Última venta</th>
              <th className="px-4 py-3 text-right">Días</th>
              <th className="px-4 py-3">Estado</th>
              <th className="px-4 py-3">ABC</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {items.map((item) => (
              <tr key={`${item.cod_producto}-${item.cod_bodega}`} className="transition-colors hover:bg-surface-alt/70">
                <td className="px-4 py-3 font-mono text-xs text-primary">{item.cod_producto}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-surface-dark text-xs font-black text-text-inverse">
                      {productInitial(item.nom_producto)}
                    </div>
                    <p className="font-semibold text-text-primary" title={item.nom_producto}>{productShort(item.nom_producto, 72)}</p>
                  </div>
                </td>
                <td className="px-4 py-3 text-right"><StockBadge qty={item.stock_actual} /></td>
                <td className="px-4 py-3 text-right text-text-secondary">{formatMoney(item.costo_unitario)}</td>
                <td className="px-4 py-3 text-right font-semibold text-text-primary">{formatMoney(item.valor_inventario)}</td>
                <td className="px-4 py-3 text-text-secondary">{item.ultima_venta ?? "—"}</td>
                <td className="px-4 py-3 text-right text-text-secondary">{daysLabel(item.dias_sin_venta)}</td>
                <td className="px-4 py-3">
                  <Badge variant={item.es_dormido ? "error" : "success"} size="sm">{item.es_dormido ? "Dormido" : "Activo"}</Badge>
                </td>
                <td className="px-4 py-3">
                  <Badge variant={item.abc === "A" ? "success" : item.abc === "B" ? "warning" : "default"} size="sm">{item.abc}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────

export default function InventarioPage(): JSX.Element {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [stockFilter, setStockFilter] = useState<StockFilter>("todos");
  const [dormidoFilter, setDormidoFilter] = useState<DormidoFilter>("todos");
  const [abcFilter, setAbcFilter] = useState("");
  const [sortBy, setSortBy] = useState<SortField>("valor_inventario");

  const summary = useInventorySummary();
  const discrepancies = useInventoryDiscrepancies();
  const detail = useInventoryDetail(
    page,
    30,
    search || undefined,
    undefined,
    sortBy,
    stockFilter,
    dormidoFilter,
    abcFilter || undefined,
  );

  // Global slices for real insights, not just the current table page.
  const topStock = useInventoryDetail(1, 10, undefined, undefined, "stock_actual", "con_stock");
  const topValue = useInventoryDetail(1, 10, undefined, undefined, "valor_inventario", "con_stock");
  const topCost = useInventoryDetail(1, 10, undefined, undefined, "costo_unitario", "con_stock");
  const topDormantValue = useInventoryDetail(1, 10, undefined, undefined, "valor_inventario", "con_stock", "true");
  const withStock = useInventoryDetail(1, 1, undefined, undefined, "stock_actual", "con_stock");
  const withoutStock = useInventoryDetail(1, 1, undefined, undefined, "stock_actual", "sin_stock");
  const dormantWithStock = useInventoryDetail(1, 1, undefined, undefined, "stock_actual", "con_stock", "true");
  const abcA = useInventoryDetail(1, 1, undefined, undefined, "abc", "todos", "todos", "A");
  const abcB = useInventoryDetail(1, 1, undefined, undefined, "abc", "todos", "todos", "B");
  const abcC = useInventoryDetail(1, 1, undefined, undefined, "abc", "todos", "todos", "C");

  const items = detail.data?.items ?? [];
  const total = detail.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / 30));
  const heroHighlights = [
    topStock.data?.items?.[0],
    topValue.data?.items?.[0],
    topCost.data?.items?.[0],
    topDormantValue.data?.items?.[0],
  ].filter(Boolean) as InventoryItem[];

  const stockDistribution = useMemo(() => {
    const stock = withStock.data?.total ?? 0;
    const noStock = withoutStock.data?.total ?? 0;
    const dormant = dormantWithStock.data?.total ?? 0;
    return [
      { name: "Con stock", value: stock },
      { name: "Sin stock", value: noStock },
      { name: "Dormidos con stock", value: dormant },
    ].filter((x) => x.value > 0);
  }, [withStock.data?.total, withoutStock.data?.total, dormantWithStock.data?.total]);

  const abcDistribution = useMemo(() => [
    { name: "A", value: abcA.data?.total ?? 0 },
    { name: "B", value: abcB.data?.total ?? 0 },
    { name: "C", value: abcC.data?.total ?? 0 },
  ], [abcA.data?.total, abcB.data?.total, abcC.data?.total]);

  const invariantBroken = discrepancies.data?.summary && !discrepancies.data.summary.invariant_ok;

  if (summary.error || detail.error) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-accent hover:underline">← Volver a inicio</Link>
        <ErrorState title="Error al cargar inventario" message="No se pudieron obtener los productos del inventario." severity="warning" />
      </div>
    );
  }

  return (
    <div className="space-y-5 pb-6">
      <Link href="/" className="text-sm text-accent hover:underline">← Volver a inicio</Link>

      <section className="relative overflow-hidden rounded-[2rem] border border-border bg-[#15110f] p-5 text-text-inverse shadow-2xl md:p-7">
        <div className="absolute -left-24 top-6 h-64 w-64 rounded-full bg-primary/35 blur-3xl" />
        <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-warning/25 blur-3xl" />
        <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-white/40 to-transparent" />
        <div className="relative grid gap-5 lg:grid-cols-[1.1fr_0.9fr] lg:items-end">
          <div>
            <p className="text-[0.68rem] font-semibold uppercase tracking-[0.32em] text-white/45">Inventario físico</p>
            <h1 className="mt-2 max-w-4xl text-3xl font-black tracking-tight md:text-5xl">Radar de existencias: unidades, plata quieta y riesgo.</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-white/65">
              El objetivo no es ver una bodega genérica; es identificar qué productos ocupan capital, cuáles tienen más unidades y cuáles llevan demasiado tiempo sin moverse.
            </p>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {heroHighlights.map((item, index) => (
              <div key={`${item.cod_producto}-${index}`} className="rounded-2xl border border-white/10 bg-white/[0.06] p-3 backdrop-blur">
                <p className="font-mono text-[0.65rem] uppercase tracking-[0.18em] text-white/45">{item.cod_producto}</p>
                <p className="mt-1 truncate text-sm font-bold text-white" title={item.nom_producto}>{item.nom_producto}</p>
                <p className="mt-1 text-xs text-white/55">{index === 0 ? stockLabel(item.stock_actual) : index === 2 ? formatMoney(item.costo_unitario) : formatMoney(item.valor_inventario)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        {!summary.data ? (
          Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)
        ) : (
          <>
            <Card className="lg:col-span-1"><Stat label="SKUs inventario" value={summary.data.num_productos.toLocaleString("es-CO")} subtitle="distintos" /></Card>
            <Card className="lg:col-span-1"><Stat label="Con stock" value={(withStock.data?.total ?? 0).toLocaleString("es-CO")} subtitle="existencia física" /></Card>
            <Card className="lg:col-span-1"><Stat label="Sin stock" value={(withoutStock.data?.total ?? 0).toLocaleString("es-CO")} subtitle="sin unidades" /></Card>
            <Card className="lg:col-span-1"><Stat label="Unidades" value={compactNumber(summary.data.stock_total)} subtitle="stock físico" /></Card>
            <Card className="lg:col-span-1"><Stat label="Valor" value={formatMoney(summary.data.valor_total)} subtitle="a costo" /></Card>
            <Card className="lg:col-span-1"><Stat label="Dormidos" value={(dormantWithStock.data?.total ?? 0).toLocaleString("es-CO")} subtitle="con stock" /></Card>
          </>
        )}
      </section>

      {invariantBroken && (
        <Card className="border-warning bg-warning/5">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-warning/15 text-warning">!</div>
            <div className="text-sm">
              <p className="font-bold text-text-primary">Dormidos pendiente de rebuild del pipeline</p>
              <p className="mt-1 text-text-muted">La vista de inventario físico ya sirve, pero el mart de dormidos en R2 todavía refleja el gold viejo hasta que Dev W reconstruya y suba el DuckDB.</p>
              <p className="mt-2 font-mono text-[0.68rem] text-text-muted">{discrepancies.data?.summary.invariant_msg}</p>
            </div>
          </div>
        </Card>
      )}

      <section className="grid gap-3 xl:grid-cols-2">
        <LeaderboardCard
          title="Top 10 con más unidades"
          subtitle="Los productos que más tenés físicamente"
          badge="Unidades"
          items={topStock.data?.items ?? []}
          metric="stock"
          accent="#7B1818"
        />
        <LeaderboardCard
          title="Top 10 por valor inmovilizado"
          subtitle="Donde hay más plata quieta por stock × costo"
          badge="Valor"
          items={topValue.data?.items ?? []}
          metric="value"
          accent="#D97706"
        />
        <LeaderboardCard
          title="Top 10 costo unitario"
          subtitle="Piezas caras aunque tengan pocas unidades"
          badge="Costo"
          items={topCost.data?.items ?? []}
          metric="cost"
          accent="#334155"
        />
        <LeaderboardCard
          title="Top 10 dormidos con valor"
          subtitle="Prioridad comercial: tienen stock y no se mueven"
          badge="Dormidos"
          items={topDormantValue.data?.items ?? []}
          metric="value"
          accent="#B91C1C"
        />
      </section>

      <section className="grid gap-3 lg:grid-cols-2">
        <Card header={<h2 className="font-bold text-text-primary">Distribución stock vs catálogo</h2>}>
          <ResponsiveContainer width="100%" height={230}>
            <PieChart>
              <Pie data={stockDistribution} cx="50%" cy="50%" innerRadius={56} outerRadius={84} paddingAngle={3} dataKey="value" nameKey="name" stroke="none">
                {stockDistribution.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
              </Pie>
              <Tooltip formatter={(value, name) => [toNumber(value).toLocaleString("es-CO"), String(name)]} contentStyle={{ borderRadius: "12px", fontSize: "12px" }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
            {stockDistribution.map((item, i) => (
              <div key={item.name} className="rounded-xl bg-surface-alt p-2">
                <span className="mb-1 block h-2 w-2 rounded-full" style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }} />
                <p className="font-semibold text-text-primary">{item.value.toLocaleString("es-CO")}</p>
                <p className="text-text-muted">{item.name}</p>
              </div>
            ))}
          </div>
        </Card>

        <Card header={<h2 className="font-bold text-text-primary">Composición ABC del inventario</h2>}>
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={abcDistribution} margin={{ left: 8, right: 12 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eeeeee" />
              <XAxis dataKey="name" tick={{ fontSize: 12 }} stroke="#9ca3af" />
              <YAxis tick={{ fontSize: 10 }} stroke="#9ca3af" />
              <Tooltip formatter={(value, name) => [toNumber(value).toLocaleString("es-CO"), `ABC ${String(name)}`]} contentStyle={{ borderRadius: "12px", fontSize: "12px" }} />
              <Bar dataKey="value" radius={[8, 8, 0, 0]}>
                {abcDistribution.map((item) => <Cell key={item.name} fill={ABC_COLORS[item.name]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className="mt-2 text-xs text-text-muted">Bodega se oculta porque la fuente actual llega sin nombre útil; mostrar “Sin nombre” repetido no ayuda a decidir.</p>
        </Card>
      </section>

      <Card
        header={
          <div className="space-y-3">
            <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
              <div>
                <h2 className="text-lg font-black text-text-primary">Explorador de productos</h2>
                <p className="text-xs text-text-muted">{total.toLocaleString("es-CO")} productos encontrados. Ordená por ABC, días, costo, unidades o valor.</p>
              </div>
              <div className="text-xs text-text-muted">Página {page} de {totalPages}</div>
            </div>

            <div className="grid gap-2 md:grid-cols-[1.35fr_0.75fr_0.5fr]">
              <input
                type="search"
                placeholder="Buscar descripción o SKU, ej: retenedor, balinera, WSHRU…"
                value={search}
                onChange={(event) => { setSearch(event.target.value); setPage(1); }}
                className="rounded-2xl border border-border bg-surface px-4 py-3 text-sm text-text-primary outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
              />
              <select
                value={sortBy}
                onChange={(event) => { setSortBy(event.target.value as SortField); setPage(1); }}
                className="rounded-2xl border border-border bg-surface px-3 py-3 text-sm text-text-primary outline-none focus:border-primary"
              >
                <option value="valor_inventario">Mayor valor inventario</option>
                <option value="stock_actual">Más unidades</option>
                <option value="costo_unitario">Mayor costo unitario</option>
                <option value="abc">ABC: A primero</option>
                <option value="dias_sin_venta">Más días sin venta</option>
                <option value="ultima_venta">Última venta reciente</option>
                <option value="nom_producto">Descripción</option>
              </select>
              <select
                value={abcFilter}
                onChange={(event) => { setAbcFilter(event.target.value); setPage(1); }}
                className="rounded-2xl border border-border bg-surface px-3 py-3 text-sm text-text-primary outline-none focus:border-primary"
              >
                <option value="">ABC todos</option>
                <option value="A">ABC A</option>
                <option value="B">ABC B</option>
                <option value="C">ABC C</option>
              </select>
            </div>

            <div className="flex flex-wrap gap-2">
              <SegmentedButton active={stockFilter} value="todos" onClick={(v) => { setStockFilter(v); setPage(1); }}>Todo stock</SegmentedButton>
              <SegmentedButton active={stockFilter} value="con_stock" onClick={(v) => { setStockFilter(v); setPage(1); }}>Con stock</SegmentedButton>
              <SegmentedButton active={stockFilter} value="sin_stock" onClick={(v) => { setStockFilter(v); setPage(1); }}>Sin stock</SegmentedButton>
              <SegmentedButton active={dormidoFilter} value="todos" onClick={(v) => { setDormidoFilter(v); setPage(1); }}>Todos</SegmentedButton>
              <SegmentedButton active={dormidoFilter} value="true" onClick={(v) => { setDormidoFilter(v); setPage(1); }}>Dormidos</SegmentedButton>
              <SegmentedButton active={dormidoFilter} value="false" onClick={(v) => { setDormidoFilter(v); setPage(1); }}>Activos</SegmentedButton>
            </div>
          </div>
        }
      >
        {detail.isLoading ? (
          <div className="space-y-2">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-14 rounded-xl" />)}</div>
        ) : items.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-border bg-surface-alt p-8 text-center text-sm text-text-muted">Sin productos para esos filtros.</div>
        ) : (
          <>
            <div className="space-y-3 md:hidden">
              {items.map((item) => <ProductCard key={`${item.cod_producto}-${item.cod_bodega}`} item={item} />)}
            </div>
            <ProductTable items={items} />
          </>
        )}

        <div className="mt-4 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="rounded-full bg-surface-alt px-4 py-2 text-xs font-semibold text-text-secondary transition hover:bg-surface-dark/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            ← Anterior
          </button>
          <span className="text-xs text-text-muted">{page} / {totalPages}</span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="rounded-full bg-surface-dark px-4 py-2 text-xs font-semibold text-text-inverse transition hover:bg-primary disabled:cursor-not-allowed disabled:opacity-40"
          >
            Siguiente →
          </button>
        </div>
      </Card>
    </div>
  );
}
