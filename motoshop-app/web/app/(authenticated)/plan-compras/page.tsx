"use client";

import { useState } from "react";
import Link from "next/link";
import { usePlanCompras } from "@/lib/api/hooks";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Table } from "@/components/ui/Table";
import { Badge, StockBadge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatMoney } from "@/lib/format/currency";

const ABC_VARIANT: Record<string, "success" | "warning" | "error"> = {
  A: "success",
  B: "warning",
  C: "error",
};

export default function PlanComprasPage(): JSX.Element {
  const { data, error, isLoading } = usePlanCompras();
  const [filterAbc, setFilterAbc] = useState<string | null>(null);
  const [filterUrgencia, setFilterUrgencia] = useState<string | null>(null);
  const [filterDormido, setFilterDormido] = useState<boolean | null>(null);

  // ── Loading ──────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-accent hover:underline">
          ← Volver a inicio
        </Link>
        <Skeleton className="h-5 w-24" />
        <div className="grid grid-cols-3 gap-3">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-80 rounded-xl" />
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
          <p className="py-8 text-center text-sm text-text-muted">
            Error al cargar datos del plan de compras
          </p>
        </Card>
      </div>
    );
  }

  // ── Filtros ──────────────────────────────────────────────────

  let items = data.items;
  if (filterAbc) items = items.filter((i) => i.abc === filterAbc);
  if (filterUrgencia) items = items.filter((i) => i.urgencia === filterUrgencia);
  if (filterDormido !== null) items = items.filter((i) => i.dormido === filterDormido);

  // ── Render ───────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">
        ← Volver a inicio
      </Link>

      <div>
        <h1 className="text-xl font-bold text-text-primary">Plan de compras</h1>
        <p className="text-sm text-text-muted">
          Sugerencia combinando alertas, forecast, ABC y dormidos
        </p>
      </div>

      {/* Resumen */}
      <div className="grid grid-cols-3 gap-3">
        <Card>
          <Stat
            label="SKUs en plan"
            value={String(data.total_skus)}
            subtitle={`${data.skus_urgentes} urgentes`}
          />
        </Card>
        <Card>
          <Stat
            label="Unidades"
            value={Math.round(data.total_unidades).toLocaleString("es-CO")}
            subtitle="cantidad sugerida"
          />
        </Card>
        <Card>
          <Stat
            label="Valor estimado"
            value={formatMoney(data.total_valor_estimado)}
            subtitle={`${data.skus_dormidos} dormidos`}
          />
        </Card>
      </div>

      {/* Filtros */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setFilterAbc(null)}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
            filterAbc === null
              ? "bg-surface-dark text-text-inverse"
              : "bg-surface-alt text-text-secondary hover:bg-surface-dark/10"
          }`}
        >
          Todos
        </button>
        {(["A", "B", "C"] as const).map((abc) => (
          <button
            key={abc}
            onClick={() => setFilterAbc(abc === filterAbc ? null : abc)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
              filterAbc === abc
                ? "bg-surface-dark text-text-inverse"
                : "bg-surface-alt text-text-secondary hover:bg-surface-dark/10"
            }`}
          >
            ABC {abc}
          </button>
        ))}
        <span className="mx-2 border-l border-border" />
        <button
          onClick={() => setFilterUrgencia(null)}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
            filterUrgencia === null
              ? "bg-surface-dark text-text-inverse"
              : "bg-surface-alt text-text-secondary hover:bg-surface-dark/10"
          }`}
        >
          Todas
        </button>
        {(["alta", "media", "baja"] as const).map((u) => (
          <button
            key={u}
            onClick={() => setFilterUrgencia(u === filterUrgencia ? null : u)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
              filterUrgencia === u
                ? "bg-surface-dark text-text-inverse"
                : "bg-surface-alt text-text-secondary hover:bg-surface-dark/10"
            }`}
          >
            {u.charAt(0).toUpperCase() + u.slice(1)}
          </button>
        ))}
        <span className="mx-2 border-l border-border" />
        <button
          onClick={() => setFilterDormido(filterDormido === true ? null : true)}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
            filterDormido === true
              ? "bg-surface-dark text-text-inverse"
              : "bg-surface-alt text-text-secondary hover:bg-surface-dark/10"
          }`}
        >
          {filterDormido === true ? "Solo dormidos" : "Incluir dormidos"}
        </button>
      </div>

      {/* Tabla */}
      {items.length > 0 ? (
        <Card>
          <div className="overflow-x-auto">
            <Table
              columns={[
                {
                  header: "SKU",
                  cell: (item) => (
                    <div>
                      <p className="text-sm font-medium">{item.nombre}</p>
                      <p className="font-mono text-xs text-text-muted">{item.sku}</p>
                    </div>
                  ),
                },
                {
                  header: "Stock",
                  cell: (item) => (
                    <div className="text-center">
                      <StockBadge qty={Math.round(item.stock_actual)} />
                    </div>
                  ),
                  align: "center",
                },
                {
                  header: "Demanda 7d",
                  cell: (item) => Math.round(item.demanda_7d),
                  align: "right",
                },
                {
                  header: "Comprar",
                  cell: (item) => {
                    const qty = Math.round(item.cantidad_a_comprar);
                    if (qty <= 0) return <span className="text-text-muted">—</span>;
                    return <span className="font-bold text-text-primary">{qty}</span>;
                  },
                  align: "right",
                },
                {
                  header: "ABC",
                  cell: (item) => (
                    <Badge variant={ABC_VARIANT[item.abc] ?? "default"} size="sm">
                      {item.abc}
                    </Badge>
                  ),
                  align: "center",
                },
                {
                  header: "Urgencia",
                  cell: (item) =>
                    item.urgencia ? (
                      <Badge
                        variant={
                          item.urgencia === "alta"
                            ? "error"
                            : item.urgencia === "media"
                              ? "warning"
                              : "info"
                        }
                        size="sm"
                      >
                        {item.urgencia}
                      </Badge>
                    ) : (
                      <span className="text-text-muted">—</span>
                    ),
                  align: "center",
                },
                {
                  header: "Dormido",
                  cell: (item) =>
                    item.dormido ? (
                      <Badge variant="warning" size="sm">
                        Dormido
                      </Badge>
                    ) : null,
                  align: "center",
                },
                {
                  header: "Proveedor",
                  cell: (item) => (
                    <span className="text-xs text-text-secondary">{item.supplier}</span>
                  ),
                },
              ]}
              data={items}
              keyFn={(item) => item.sku}
              striped
            />
          </div>
        </Card>
      ) : (
        <Card>
          <p className="py-8 text-center text-sm text-text-muted">
            Sin SKUs que coincidan con los filtros
          </p>
        </Card>
      )}
    </div>
  );
}
