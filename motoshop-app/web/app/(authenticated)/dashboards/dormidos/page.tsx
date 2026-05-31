"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useDormidos } from "@/lib/api/hooks";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { Table } from "@/components/ui/Table";

type SortField = "dias_sin_venta" | "ultimo_movimiento";
type SortDir = "asc" | "desc";

function dormancyVariant(dias: number): "error" | "warning" | "default" {
  if (dias > 180) return "error";
  if (dias >= 90) return "warning";
  return "default";
}

function sortIcon(dir: SortDir): string {
  return dir === "desc" ? " ↓" : " ↑";
}

export default function DormidosPage(): JSX.Element {
  const { data, error, isLoading } = useDormidos();
  const [sortField, setSortField] = useState<SortField>("dias_sin_venta");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  function toggleSort(field: SortField) {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  }

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
          <p className="py-8 text-center text-text-muted">
            Error al cargar datos de productos dormidos
          </p>
        </Card>
      </div>
    );
  }

  const criticos = data.productos.filter((p) => p.dias_sin_venta > 180).length;

  // ── Sort ─────────────────────────────────────────────────────

  const sortedItems = useMemo(() => {
    const items = [...data.productos];
    items.sort((a, b) => {
      let cmp = 0;
      if (sortField === "dias_sin_venta") {
        cmp = a.dias_sin_venta - b.dias_sin_venta;
      } else if (sortField === "ultimo_movimiento") {
        const da = a.ultimo_movimiento ?? "";
        const db = b.ultimo_movimiento ?? "";
        cmp = da.localeCompare(db);
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return items;
  }, [data, sortField, sortDir]);

  // ── Render ───────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">
        ← Volver a inicio
      </Link>

      <div>
        <h1 className="text-xl font-bold text-text-primary">Productos dormidos</h1>
        <p className="text-sm text-text-muted">
          {data.total > 0
            ? `${data.total} producto${data.total !== 1 ? "s" : ""} sin venta en 90+ días`
            : "Sin productos dormidos"}
        </p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 gap-3">
        <Card>
          <Stat
            label="Total dormidos"
            value={String(data.total)}
            subtitle="&gt; 90 días sin venta"
          />
        </Card>
        <Card>
          <Stat
            label="Críticos"
            value={String(criticos)}
            subtitle="&gt; 180 días"
          />
        </Card>
      </div>

      {/* Tabla de dormidos */}
      <Card header={<h2 className="font-semibold text-text-primary">Lista de dormidos</h2>}>
        <Table
          columns={[
            {
              header: "SKU",
              cell: (p) => (
                <div>
                  <p className="truncate text-sm font-medium text-text-primary">
                    {p.nom_producto}
                  </p>
                  <p className="font-mono text-xs text-text-muted">{p.cod_producto}</p>
                </div>
              ),
            },
            {
              header: (
                <button
                  onClick={() => toggleSort("dias_sin_venta")}
                  className="flex items-center gap-1 font-medium text-text-secondary hover:text-text-primary"
                >
                  Días sin venta{sortField === "dias_sin_venta" ? sortIcon(sortDir) : ""}
                </button>
              ),
              cell: (p) => (
                <Badge variant={dormancyVariant(p.dias_sin_venta)} size="md">
                  {p.dias_sin_venta}d
                </Badge>
              ),
              align: "center",
            },
            {
              header: (
                <button
                  onClick={() => toggleSort("ultimo_movimiento")}
                  className="flex items-center gap-1 font-medium text-text-secondary hover:text-text-primary"
                >
                  Última compra{sortField === "ultimo_movimiento" ? sortIcon(sortDir) : ""}
                </button>
              ),
              cell: (p) =>
                p.ultimo_movimiento ? (
                  <span className="text-sm text-text-primary">{p.ultimo_movimiento}</span>
                ) : (
                  <span className="text-xs text-text-muted">—</span>
                ),
              align: "center",
            },
            {
              header: "Stock",
              cell: (p) =>
                p.stock_actual != null ? (
                  <span className="text-sm text-text-primary">
                    {p.stock_actual.toLocaleString("es-CO")}
                  </span>
                ) : (
                  <span className="text-xs text-text-muted">—</span>
                ),
              align: "right",
            },
          ]}
          data={sortedItems}
          keyFn={(p) => p.cod_producto}
          striped
          emptyMessage="No hay productos dormidos en este período"
        />
      </Card>
    </div>
  );
}
