"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth/store";
import { useCatalog, useCatalogTable, useLineage, type CatalogTable, type LineageEdge } from "@/lib/api/hooks";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Table } from "@/components/ui/Table";
import { Skeleton } from "@/components/ui/Skeleton";

// ── Layer config ─────────────────────────────────────────────────────

const LAYER_CONFIG: Record<string, { label: string; hex: string; variant: "success"|"warning"|"error"|"default" }> = {
  bronze: { label: "Bronze", hex: "#B87333", variant: "error" },
  silver: { label: "Silver", hex: "#94A3B8", variant: "warning" },
  gold: { label: "Gold", hex: "#F59E0B", variant: "success" },
};

function getLayer(l: string) { return LAYER_CONFIG[l] ?? { label: l, hex: "#9CA3AF", variant: "default" as const }; }
function statusVariant(s: string): "success"|"warning"|"error"|"default" {
  if (s === "ok" || s === "success") return "success";
  if (s === "stale" || s === "warning") return "warning";
  if (s === "empty" || s === "failed") return "error";
  return "default";
}
function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n/1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n/1_000).toFixed(0)}K`;
  return String(n);
}

// ── Mini Lineage ─────────────────────────────────────────────────────

function MiniLineage({ edges }: { edges?: LineageEdge[] }) {
  const layers = ["bronze", "silver", "gold"] as const;
  if (!edges?.length) {
    return (
      <Card header={<h2 className="font-semibold text-text-primary">Linaje de datos</h2>}>
        <p className="py-4 text-sm text-text-muted text-center">Cargando linaje...</p>
      </Card>
    );
  }
  // Count edges per layer
  const fromLayers: Record<string, Set<string>> = {};
  const toLayers: Record<string, Set<string>> = {};
  edges.forEach(e => {
    if (e.from) (fromLayers[e.transform] ??= new Set()).add(e.from);
    if (e.to) (toLayers[e.transform] ??= new Set()).add(e.to);
  });

  return (
    <Card header={<h2 className="font-semibold text-text-primary">Linaje de datos ({edges.length} conexiones)</h2>}>
      <div className="flex flex-col items-center gap-1 py-3">
        <div className="flex flex-wrap items-center justify-center gap-2 md:gap-4">
          {layers.map((layer, i) => {
            const cfg = getLayer(layer);
            const tables = fromLayers[layer] ?? toLayers[layer] ?? new Set();
            return (
              <div key={layer} className="flex items-center gap-2">
                {i > 0 && <span className="text-text-muted text-lg">→</span>}
                <div className="rounded-lg border-2 px-3 py-2 text-sm font-medium" style={{ borderColor: cfg.hex, color: cfg.hex }}>
                  {layer === "bronze" ? "🟫" : layer === "silver" ? "⬜" : "🟨"} {cfg.label}
                  <div className="text-xs text-text-muted">{tables.size} tablas</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}

// ── Table Detail Modal ────────────────────────────────────────────────

function TableDetailModal({ name, onClose }: { name: string; onClose: () => void }) {
  const { data: detail, isLoading } = useCatalogTable(name);
  const cols = detail?.columns ?? [];
  const rows = detail?.sample_rows ?? [];
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="mx-4 max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-surface p-4 shadow-xl" onClick={e => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold text-text-primary">{detail?.table_name ?? name}</h2>
          <button onClick={onClose} className="text-sm text-text-muted hover:text-text-primary">✕</button>
        </div>
        {isLoading && <div className="space-y-2">{[1,2,3].map(i=><Skeleton key={i} className="h-8 rounded-lg"/>)}</div>}
        {detail && (
          <>
            <div className="flex items-center gap-2 mb-2">
              <Badge variant={getLayer(detail.layer).variant} size="sm">{detail.layer}</Badge>
              <span className="text-xs text-text-muted">{fmt(detail.row_count)} filas · {cols.length} cols</span>
            </div>
            {detail.quality && (
              <div className="mb-3 rounded-lg bg-surface-alt p-2 text-xs">
                {detail.quality.warnings?.length ? detail.quality.warnings.map((w,i)=><p key={i} className="text-warning">⚠️ {w}</p>) : null}
                {detail.quality.max_date && <p className="text-text-muted">Última fecha: {detail.quality.max_date}</p>}
                {detail.quality.null_counts && Object.keys(detail.quality.null_counts).length > 0 && (
                  <details className="mt-1">
                    <summary className="cursor-pointer text-text-muted">Columnas con nulos ({Object.keys(detail.quality.null_counts).length})</summary>
                    <div className="mt-1 space-y-0.5">
                      {Object.entries(detail.quality.null_counts).slice(0,10).map(([col,count])=><p key={col} className="text-text-secondary">{col}: {count}</p>)}
                    </div>
                  </details>
                )}
              </div>
            )}
            {cols.length > 0 && (
              <>
                <h3 className="mt-3 mb-1 text-xs font-semibold uppercase tracking-wider text-text-muted">Columnas ({cols.length})</h3>
                <Table
                  columns={[
                    { header: "Col", cell: (c: any) => <span className="font-mono text-xs">{c.name}</span> },
                    { header: "Tipo", cell: (c: any) => <span className="text-xs">{c.type}</span> },
                    { header: "Nulos", cell: (c: any) => <span className="text-xs">{c.null_count} ({c.null_pct}%)</span> },
                  ]}
                  data={cols} keyFn={(c: any) => c.name} striped
                />
              </>
            )}
            {rows.length > 0 && (
              <>
                <h3 className="mt-3 mb-1 text-xs font-semibold uppercase tracking-wider text-text-muted">Muestra ({rows.length} filas)</h3>
                <div className="overflow-x-auto rounded-lg border border-border">
                  <table className="w-full text-xs">
                    <thead><tr className="border-b border-border bg-surface-alt">{Object.keys(rows[0]??{}).slice(0,6).map(k=><th key={k} className="px-2 py-1 text-left font-medium text-text-secondary">{k}</th>)}</tr></thead>
                    <tbody className="divide-y divide-border">{rows.slice(0,3).map((row,i)=><tr key={i}>{Object.values(row).slice(0,6).map((v,j)=><td key={j} className="px-2 py-1 font-mono text-text-primary">{String(v)}</td>)}</tr>)}</tbody>
                  </table>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────

export default function DataCatalogPage(): JSX.Element {
  const router = useRouter();
  const role = useAuthStore(s => s.role);
  const [search, setSearch] = useState("");
  const [layerFilter, setLayerFilter] = useState<string>("");
  const [selectedTable, setSelectedTable] = useState<string | null>(null);

  const { data: catalogData, isLoading } = useCatalog();
  const { data: lineageEdges } = useLineage();
  const tables = catalogData?.tables ?? [];

  if (role === "vendedor") { router.push("/"); return <></>; }

  const filtered = (tables ?? []).filter(t => {
    if (layerFilter && t.layer !== layerFilter) return false;
    if (search && !t.table_name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  // Compute layer summaries
  const layers = ["bronze", "silver", "gold"];
  const summaries = layers.map(layer => {
    const ts = (tables ?? []).filter(t => t.layer === layer);
    return {
      layer,
      table_count: ts.length,
      total_rows: ts.reduce((s, t) => s + t.row_count, 0),
      max_date: ts.map(t => t.max_date).filter(Boolean).sort().pop() ?? null,
      warnings: ts.filter(t => t.warnings?.length > 0 || t.status !== "ok").length,
    };
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <Link href="/" className="text-sm text-accent hover:underline">← Volver a inicio</Link>
          <h1 className="text-xl font-bold text-text-primary mt-1">Catálogo de datos</h1>
          <p className="text-sm text-text-muted">{tables?.length ? `${tables.length} tablas en 3 capas` : "Cargando..."}</p>
        </div>
        <Link href="/admin/pipeline" className="text-xs text-accent hover:underline">← Pipeline</Link>
      </div>

      {/* Layer cards */}
      {isLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {[1,2,3].map(i => <Skeleton key={i} className="h-28 rounded-xl" />)}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          {summaries.map(s => {
            const cfg = getLayer(s.layer);
            return (
              <Card key={s.layer}>
                <div className="flex flex-col gap-1">
                  <div className="flex items-center justify-between">
                    <Badge variant={cfg.variant} size="sm">{cfg.label}</Badge>
                    {s.warnings > 0 && <Badge variant="warning" size="sm">{s.warnings} ⚠️</Badge>}
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                    <div><span className="text-text-muted">Tablas</span><p className="font-bold text-text-primary">{s.table_count}</p></div>
                    <div><span className="text-text-muted">Filas</span><p className="font-bold text-text-primary">{fmt(s.total_rows)}</p></div>
                    <div className="col-span-2"><span className="text-text-muted">Última fecha</span><p className="font-medium text-text-primary">{s.max_date ?? "—"}</p></div>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Lineage */}
      <MiniLineage edges={lineageEdges} />

      {/* Search + filter */}
      <div className="flex flex-wrap gap-2">
        <input type="text" placeholder="Buscar tabla..." value={search} onChange={e=>setSearch(e.target.value)}
          className="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs text-text-primary flex-1 min-w-[140px]" />
        {["",...layers].map(l => (
          <button key={l} onClick={()=>setLayerFilter(l)}
            className={`rounded-full px-3 py-1 text-xs font-medium ${layerFilter===l?"bg-primary text-primary-fg":"bg-surface-alt text-text-secondary"}`}>
            {l||"Todas"}
          </button>
        ))}
      </div>

      {/* Table list */}
      {isLoading ? (
        <div className="space-y-2">{[1,2,3,4].map(i=><Skeleton key={i} className="h-10 rounded-lg"/>)}</div>
      ) : (
        <Card header={<h2 className="font-semibold text-text-primary">Tablas ({filtered.length})</h2>}>
          <Table
            columns={[
              { header: "Capa", cell: (t: CatalogTable) => { const c=getLayer(t.layer); return <Badge variant={c.variant} size="sm">{c.label}</Badge>; } },
              { header: "Tabla", cell: (t: CatalogTable) => <span className="font-mono text-xs">{t.table_name}</span> },
              { header: "Filas", cell: (t: CatalogTable) => <span className="text-xs">{fmt(t.row_count)}</span>, align: "right" },
              { header: "Cols", cell: (t: CatalogTable) => <span className="text-xs">{t.column_count}</span>, align: "right" },
              { header: "Fecha", cell: (t: CatalogTable) => <span className="text-xs">{t.max_date??"—"}</span> },
              { header: "Estado", cell: (t: CatalogTable) => <Badge variant={statusVariant(t.status)} size="sm">{t.status}</Badge> },
              { header: "", cell: (t: CatalogTable) => <button onClick={()=>setSelectedTable(t.table_name)} className="text-xs font-medium text-accent hover:underline">Detalle</button> },
            ]}
            data={filtered} keyFn={(t: CatalogTable)=>t.table_name} striped
          />
        </Card>
      )}

      {selectedTable && <TableDetailModal name={selectedTable} onClose={()=>setSelectedTable(null)} />}
    </div>
  );
}
