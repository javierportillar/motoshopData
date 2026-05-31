"use client";

import Link from "next/link";
import { useVendedoresSummary } from "@/lib/api/hooks";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Table } from "@/components/ui/Table";
import { DeltaBadge } from "@/components/ui/Badge";
import { formatMoney } from "@/lib/format/currency";

export default function VendedoresPage(): JSX.Element {
  const { data, error, isLoading } = useVendedoresSummary();

  // ── Loading ──────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-accent hover:underline">
          ← Volver a inicio
        </Link>
        <div className="h-5 w-24 animate-pulse rounded bg-surface-alt" />
        <div className="grid grid-cols-3 gap-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-surface-alt" />
          ))}
        </div>
        <div className="h-80 animate-pulse rounded-xl bg-surface-alt" />
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
            Error al cargar datos de vendedores
          </p>
        </Card>
      </div>
    );
  }

  const items = data.items;

  // ── Render ───────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">
        ← Volver a inicio
      </Link>

      <div>
        <h1 className="text-xl font-bold text-text-primary">Vendedores</h1>
        <p className="text-sm text-text-muted">Rendimiento del mes actual</p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-3 gap-3">
        <Card>
          <Stat
            label="Total vendido"
            value={formatMoney(items.reduce((s, v) => s + v.total_ventas, 0))}
            subtitle="este mes"
          />
        </Card>
        <Card>
          <Stat
            label="Facturas"
            value={items.reduce((s, v) => s + v.facturas, 0).toLocaleString("es-CO")}
            subtitle="este mes"
          />
        </Card>
        <Card>
          <Stat
            label="Vendedores"
            value={String(items.length)}
            subtitle="activos"
          />
        </Card>
      </div>

      {/* Tabla ranking */}
      {items.length > 0 ? (
        <Card header={<h2 className="font-semibold text-text-primary">Ranking del mes</h2>}>
          <Table
            columns={[
              { header: "#", cell: (_, i) => i + 1, align: "center", className: "w-8" },
              {
                header: "Vendedor",
                cell: (v) => (
                  <div>
                    <p className="text-sm font-medium">{v.nombre_vendedor}</p>
                    <p className="font-mono text-xs text-text-muted">{v.nit_vendedor}</p>
                  </div>
                ),
              },
              {
                header: "Facturas",
                cell: (v) => v.facturas,
                align: "right",
              },
              {
                header: "Total",
                cell: (v) => formatMoney(v.total_ventas),
                align: "right",
              },
              {
                header: "Ticket",
                cell: (v) => formatMoney(v.ticket_promedio),
                align: "right",
              },
            ]}
            data={items}
            keyFn={(v) => v.nit_vendedor}
            striped
          />
        </Card>
      ) : (
        <Card>
          <p className="py-8 text-center text-sm text-text-muted">Sin datos de vendedores este mes</p>
        </Card>
      )}
    </div>
  );
}
