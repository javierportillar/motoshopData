"use client";

import { useState } from "react";
import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Table } from "@/components/ui/Table";
import { Badge, StockBadge } from "@/components/ui/Badge";
import { formatMoney } from "@/lib/format/currency";

// ── Mock data (reemplazar cuando Dev A2 cree /metrics/plan-compras) ──

interface PlanCompraItem {
  sku: string;
  nombre: string;
  stock_actual: number;
  demanda_7d: number;
  cantidad_a_comprar: number;
  abc: "A" | "B" | "C";
  urgencia: "alta" | "media" | "baja" | null;
  dormido: boolean;
  supplier: string;
}

const MOCK_PLAN: PlanCompraItem[] = [
  {
    sku: "MOTS1297",
    nombre: "ACEITE 20W50 MOTUL 1L",
    stock_actual: 2,
    demanda_7d: 18,
    cantidad_a_comprar: 16,
    abc: "A",
    urgencia: "alta",
    dormido: false,
    supplier: "Motul Colombia",
  },
  {
    sku: "MOTS0412",
    nombre: "FILTRO ACEITE YAMAHA YBR125",
    stock_actual: 0,
    demanda_7d: 12,
    cantidad_a_comprar: 12,
    abc: "A",
    urgencia: "alta",
    dormido: false,
    supplier: "Yamaha Parts SA",
  },
  {
    sku: "MOTS0834",
    nombre: "PASTILLAS FRENO DELANTERAS",
    stock_actual: 5,
    demanda_7d: 8,
    cantidad_a_comprar: 3,
    abc: "B",
    urgencia: "media",
    dormido: false,
    supplier: "Frenos del Sur",
  },
  {
    sku: "MOTS1205",
    nombre: "CADENA TRANSMISIÓN 428H",
    stock_actual: 1,
    demanda_7d: 4,
    cantidad_a_comprar: 3,
    abc: "A",
    urgencia: "alta",
    dormido: false,
    supplier: "DID Chains Intl",
  },
  {
    sku: "MOTS0560",
    nombre: "ESPEJO RETROVISOR UNIVERSAL",
    stock_actual: 20,
    demanda_7d: 3,
    cantidad_a_comprar: 0,
    abc: "C",
    urgencia: null,
    dormido: true,
    supplier: "Genéricos Express",
  },
];

const ABC_VARIANT: Record<string, "success" | "warning" | "error"> = {
  A: "success",
  B: "warning",
  C: "error",
};

// ── Page ───────────────────────────────────────────────────────

export default function PlanComprasPage(): JSX.Element {
  const [filterAbc, setFilterAbc] = useState<string | null>(null);
  const [filterUrgencia, setFilterUrgencia] = useState<string | null>(null);
  const [filterDormido, setFilterDormido] = useState<boolean | null>(null);

  // TODO: reemplazar por usePlanCompras() cuando Dev A2 cree el endpoint
  let data = MOCK_PLAN;

  // Filtros
  if (filterAbc) data = data.filter((i) => i.abc === filterAbc);
  if (filterUrgencia) data = data.filter((i) => i.urgencia === filterUrgencia);
  if (filterDormido !== null) data = data.filter((i) => i.dormido === filterDormido);

  const totalSkus = data.length;
  const totalUnidades = data.reduce((s, i) => s + i.cantidad_a_comprar, 0);
  const totalValor = data.reduce((s, i) => s + i.cantidad_a_comprar * 25000, 0); // placeholder

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">
        ← Volver a inicio
      </Link>

      <div>
        <h1 className="text-xl font-bold text-text-primary">Plan de compras</h1>
        <p className="text-sm text-text-muted">
          Sugerencia combinando alertas, forecast, ABC y dormidos — datos de muestra
        </p>
      </div>

      {/* Resumen */}
      <div className="grid grid-cols-3 gap-3">
        <Card>
          <Stat label="SKUs a pedir" value={String(totalSkus)} subtitle="en el plan" />
        </Card>
        <Card>
          <Stat
            label="Unidades"
            value={totalUnidades.toLocaleString("es-CO")}
            subtitle="cantidad sugerida"
          />
        </Card>
        <Card>
          <Stat label="Valor estimado" value={formatMoney(totalValor)} subtitle="orden propuesta" />
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
                    <StockBadge qty={item.stock_actual} />
                  </div>
                ),
                align: "center",
              },
              {
                header: "Demanda 7d",
                cell: (item) => item.demanda_7d,
                align: "right",
              },
              {
                header: "Comprar",
                cell: (item) => (
                  <span className={item.cantidad_a_comprar > 0 ? "font-bold text-text-primary" : "text-text-muted"}>
                    {item.cantidad_a_comprar > 0 ? item.cantidad_a_comprar : "—"}
                  </span>
                ),
                align: "right",
              },
              {
                header: "ABC",
                cell: (item) => (
                  <Badge variant={ABC_VARIANT[item.abc]} size="sm">
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
                      variant={item.urgencia === "alta" ? "error" : item.urgencia === "media" ? "warning" : "info"}
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
            data={data}
            keyFn={(item) => item.sku}
            striped
          />
        </div>
      </Card>

      <p className="text-center text-xs text-text-muted">
        Datos de muestra — endpoint real en desarrollo por Dev A2
      </p>
    </div>
  );
}
