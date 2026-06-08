"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth/store";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Table } from "@/components/ui/Table";
import { Skeleton } from "@/components/ui/Skeleton";

// ── Types ────────────────────────────────────────────────────────────

interface ColumnInfo {
  name: string;
  type: string;
  null_count: number;
  null_pct: number;
}

interface TableInfo {
  name: string;
  layer: "bronze" | "silver" | "gold" | "other";
  row_count: number;
  column_count: number;
  date_column: string | null;
  max_date: string | null;
  status: "ok" | "stale" | "empty" | "warning";
  warnings: string[];
}

interface LayerSummary {
  layer: "bronze" | "silver" | "gold" | "other";
  table_count: number;
  total_rows: number;
  max_date: string | null;
  warnings: number;
}

interface TableDetail extends TableInfo {
  columns: ColumnInfo[];
  sample_rows: Record<string, unknown>[];
}

// ── Layer config ─────────────────────────────────────────────────────

const LAYER_COLORS: Record<string, { bg: string; text: string; hex: string; label: string }> = {
  bronze: { bg: "bg-amber-100", text: "text-amber-800", hex: "#B87333", label: "Bronze" },
  silver: { bg: "bg-slate-200", text: "text-slate-700", hex: "#94A3B8", label: "Silver" },
  gold: { bg: "bg-yellow-100", text: "text-yellow-800", hex: "#F59E0B", label: "Gold" },
  other: { bg: "bg-gray-100", text: "text-gray-600", hex: "#9CA3AF", label: "Other" },
};

function layerVariant(layer: string): "success" | "warning" | "error" | "default" {
  if (layer === "gold") return "success";
  if (layer === "silver") return "warning";
  if (layer === "bronze") return "error";
  return "default";
}

function statusVariant(s: string): "success" | "warning" | "error" | "default" {
  if (s === "ok") return "success";
  if (s === "stale" || s === "warning") return "warning";
  if (s === "empty") return "error";
  return "default";
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

// ── Mock data (V1.8.1 — reemplazar con API cuando Dev D entregue) ──

const MOCK_TABLES: TableInfo[] = [
  { name: "bronze_productos", layer: "bronze", row_count: 6185, column_count: 16, date_column: "fecapa", max_date: "2024-07-27", status: "stale", warnings: ["Última actualización: Jul 2024"] },
  { name: "bronze_bodegas", layer: "bronze", row_count: 1, column_count: 6, date_column: null, max_date: null, status: "stale", warnings: ["Solo 1 bodega"] },
  { name: "bronze_facventas", layer: "bronze", row_count: 6339, column_count: 24, date_column: "fecfven", max_date: "2026-06-08", status: "ok", warnings: [] },
  { name: "bronze_detfventas", layer: "bronze", row_count: 27771, column_count: 15, date_column: null, max_date: null, status: "ok", warnings: [] },
  { name: "motoshop_silver_dim_producto", layer: "silver", row_count: 6185, column_count: 22, date_column: "snapshot_date", max_date: "2026-06-08", status: "ok", warnings: [] },
  { name: "motoshop_silver_fact_ventas", layer: "silver", row_count: 6339, column_count: 26, date_column: "fecha_documento_ts", max_date: "2026-06-08", status: "ok", warnings: [] },
  { name: "motoshop_silver_fact_ventas_detalle", layer: "silver", row_count: 27771, column_count: 18, date_column: null, max_date: null, status: "ok", warnings: [] },
  { name: "motoshop_silver_fact_compras", layer: "silver", row_count: 762, column_count: 23, date_column: "business_date", max_date: "2024-07-27", status: "stale", warnings: ["Última compra: Jul 2024"] },
  { name: "motoshop_silver_fact_compras_detalle", layer: "silver", row_count: 11623, column_count: 18, date_column: null, max_date: null, status: "ok", warnings: [] },
  { name: "motoshop_gold_mart_ventas_diarias_sku", layer: "gold", row_count: 24374, column_count: 8, date_column: "business_date", max_date: "2026-06-08", status: "ok", warnings: [] },
  { name: "motoshop_gold_mart_rotacion_abc", layer: "gold", row_count: 13415, column_count: 6, date_column: "business_month", max_date: "2026-05-01", status: "ok", warnings: [] },
  { name: "motoshop_gold_mart_inventario_actual", layer: "gold", row_count: 4829, column_count: 7, date_column: null, max_date: null, status: "ok", warnings: [] },
  { name: "motoshop_gold_mart_productos_dormidos", layer: "gold", row_count: 8129, column_count: 7, date_column: null, max_date: null, status: "warning", warnings: ["Incluye productos sin ventas > 90 días"] },
  { name: "motoshop_gold_mart_cohortes_clientes", layer: "gold", row_count: 198, column_count: 9, date_column: null, max_date: null, status: "ok", warnings: [] },
  { name: "motoshop_gold_forecast_categoria", layer: "gold", row_count: 685, column_count: 5, date_column: "business_date", max_date: "2026-06-07", status: "ok", warnings: [] },
];

function getLayerSummary(): LayerSummary[] {
  const layers = ["bronze", "silver", "gold"] as const;
  return layers.map(layer => {
    const tables = MOCK_TABLES.filter(t => t.layer === layer);
    return {
      layer,
      table_count: tables.length,
      total_rows: tables.reduce((s, t) => s + t.row_count, 0),
      max_date: tables.map(t => t.max_date).filter(Boolean).sort().pop() ?? null,
      warnings: tables.filter(t => t.warnings.length > 0 || t.status !== "ok").length,
    };
  });
}

function getTableDetail(name: string): TableDetail | null {
  const t = MOCK_TABLES.find(t => t.name === name);
  if (!t) return null;
  const sampleCols: ColumnInfo[] = [
    { name: "id", type: "INTEGER", null_count: 0, null_pct: 0 },
    { name: "cod_producto", type: "VARCHAR", null_count: 0, null_pct: 0 },
    { name: "nombre", type: "VARCHAR", null_count: 12, null_pct: 0.2 },
    { name: "valor", type: "DOUBLE", null_count: 0, null_pct: 0 },
    { name: "fecha", type: "DATE", null_count: 5, null_pct: 0.1 },
  ];
  return {
    ...t,
    columns: sampleCols,
    sample_rows: [
      { id: 1, cod_producto: "MOTS1297", nombre: "ACEITE 20W50", valor: 8550000, fecha: "2026-06-01" },
      { id: 2, cod_producto: "MOTS0412", nombre: "FILTRO ACEITE", valor: 5740000, fecha: "2026-06-02" },
    ],
  };
}

// ── Mini Lineage ─────────────────────────────────────────────────────

function MiniLineage() {
  return (
    <Card header={<h2 className="font-semibold text-text-primary">Linaje de datos</h2>}>
      <div className="flex flex-col items-center gap-1 py-4">
        <div className="flex items-center gap-3">
          <div className="rounded-lg border-2 px-4 py-2 text-sm font-medium" style={{ borderColor: LAYER_COLORS.bronze!.hex, color: LAYER_COLORS.bronze!.hex }}>
            🟫 Bronze
            <div className="text-xs text-text-muted">4 tablas · 40.3K filas</div>
          </div>
          <span className="text-lg text-text-muted">→</span>
          <div className="rounded-lg border-2 px-4 py-2 text-sm font-medium" style={{ borderColor: LAYER_COLORS.silver!.hex, color: LAYER_COLORS.silver!.hex }}>
            ⬜ Silver
            <div className="text-xs text-text-muted">6 tablas · 52.7K filas</div>
          </div>
          <span className="text-lg text-text-muted">→</span>
          <div className="rounded-lg border-2 px-4 py-2 text-sm font-medium" style={{ borderColor: LAYER_COLORS.gold!.hex, color: LAYER_COLORS.gold!.hex }}>
            🟨 Gold
            <div className="text-xs text-text-muted">5 tablas · 51.4K filas</div>
          </div>
        </div>
        <p className="text-xs text-text-muted mt-2">Pipeline refresh_v15 · 6 pasos</p>
      </div>
    </Card>
  );
}

// ── Table Detail Modal ────────────────────────────────────────────────

function TableDetailModal({ name, onClose }: { name: string; onClose: () => void }) {
  const detail = getTableDetail(name);
  if (!detail) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="mx-4 max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-surface p-4 shadow-xl" onClick={e => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-text-primary">{detail.name}</h2>
            <div className="flex items-center gap-2 mt-1">
              <Badge variant={layerVariant(detail.layer)} size="sm">{detail.layer}</Badge>
              <Badge variant={statusVariant(detail.status)} size="sm">{detail.status}</Badge>
              <span className="text-xs text-text-muted">{formatNumber(detail.row_count)} filas · {detail.column_count} cols</span>
            </div>
          </div>
          <button onClick={onClose} className="text-sm text-text-muted hover:text-text-primary">✕</button>
        </div>

        {detail.warnings.length > 0 && (
          <div className="mb-3 rounded-lg bg-warning/10 p-2 text-xs text-warning">
            {detail.warnings.map((w, i) => <p key={i}>⚠️ {w}</p>)}
          </div>
        )}

        <h3 className="mt-3 mb-1 text-xs font-semibold uppercase tracking-wider text-text-muted">Columnas</h3>
        <Table
          columns={[
            { header: "Columna", cell: (c: ColumnInfo) => <span className="font-mono text-xs">{c.name}</span> },
            { header: "Tipo", cell: (c: ColumnInfo) => <span className="text-xs">{c.type}</span> },
            { header: "Nulos", cell: (c: ColumnInfo) => <span className="text-xs">{c.null_count} ({c.null_pct}%)</span> },
          ]}
          data={detail.columns}
          keyFn={(c: ColumnInfo) => c.name}
          striped
        />

        <h3 className="mt-3 mb-1 text-xs font-semibold uppercase tracking-wider text-text-muted">Muestra</h3>
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border bg-surface-alt">
                {Object.keys(detail.sample_rows[0] ?? {}).map(k => (
                  <th key={k} className="px-2 py-1 text-left font-medium text-text-secondary">{k}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {detail.sample_rows.map((row, i) => (
                <tr key={i}>
                  {Object.values(row).map((v, j) => (
                    <td key={j} className="px-2 py-1 font-mono text-text-primary">{String(v)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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

  if (role === "vendedor") { router.push("/"); return <></>; }

  const summary = getLayerSummary();
  const filtered = MOCK_TABLES.filter(t => {
    if (layerFilter && t.layer !== layerFilter) return false;
    if (search && !t.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <Link href="/" className="text-sm text-accent hover:underline">← Volver a inicio</Link>
          <h1 className="text-xl font-bold text-text-primary mt-1">Catálogo de datos</h1>
          <p className="text-sm text-text-muted">Tablas por capa del pipeline DuckDB</p>
        </div>
        <Link href="/admin/pipeline" className="text-xs text-accent hover:underline">
          ← Pipeline
        </Link>
      </div>

      {/* Layer summary cards */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        {summary.map(s => (
          <Card key={s.layer}>
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <Badge variant={layerVariant(s.layer)} size="sm">
                  {LAYER_COLORS[s.layer]?.label ?? s.layer}
                </Badge>
                {s.warnings > 0 && <Badge variant="warning" size="sm">{s.warnings} ⚠️</Badge>}
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                <div><span className="text-text-muted">Tablas</span><p className="font-bold text-text-primary">{s.table_count}</p></div>
                <div><span className="text-text-muted">Filas</span><p className="font-bold text-text-primary">{formatNumber(s.total_rows)}</p></div>
                <div className="col-span-2"><span className="text-text-muted">Última fecha</span><p className="font-medium text-text-primary">{s.max_date ?? "—"}</p></div>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Mini lineage */}
      <MiniLineage />

      {/* Search + filter */}
      <div className="flex flex-wrap gap-2">
        <input
          type="text" placeholder="Buscar tabla..." value={search}
          onChange={e => setSearch(e.target.value)}
          className="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs text-text-primary flex-1 min-w-[140px]"
        />
        {["", "bronze", "silver", "gold"].map(l => (
          <button key={l} onClick={() => setLayerFilter(l)}
            className={`rounded-full px-3 py-1 text-xs font-medium ${layerFilter === l ? "bg-primary text-primary-fg" : "bg-surface-alt text-text-secondary"}`}>
            {l || "Todas"}
          </button>
        ))}
      </div>

      {/* Table list */}
      <Card header={<h2 className="font-semibold text-text-primary">Tablas ({filtered.length})</h2>}>
        <Table
          columns={[
            { header: "Capa", cell: (t: TableInfo) => <Badge variant={layerVariant(t.layer)} size="sm">{t.layer}</Badge> },
            { header: "Tabla", cell: (t: TableInfo) => <span className="font-mono text-xs">{t.name}</span> },
            { header: "Filas", cell: (t: TableInfo) => <span className="text-xs">{formatNumber(t.row_count)}</span>, align: "right" },
            { header: "Columnas", cell: (t: TableInfo) => <span className="text-xs">{t.column_count}</span>, align: "right" },
            { header: "Última fecha", cell: (t: TableInfo) => <span className="text-xs">{t.max_date ?? "—"}</span> },
            { header: "Estado", cell: (t: TableInfo) => <Badge variant={statusVariant(t.status)} size="sm">{t.status}</Badge> },
            { header: "", cell: (t: TableInfo) => <button onClick={() => setSelectedTable(t.name)} className="text-xs font-medium text-accent hover:underline">Detalle</button> },
          ]}
          data={filtered}
          keyFn={(t: TableInfo) => t.name}
          striped
        />
      </Card>

      {selectedTable && <TableDetailModal name={selectedTable} onClose={() => setSelectedTable(null)} />}
    </div>
  );
}
