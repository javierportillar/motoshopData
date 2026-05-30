"use client";

import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Table } from "@/components/ui/Table";
import { Badge, DeltaBadge } from "@/components/ui/Badge";
import { formatMoney } from "@/lib/format/currency";

// ── Mock data (reemplazar cuando Dev A2 cree /metrics/vendedores-summary) ──

interface VendedorItem {
  nit_vendedor: string;
  nombre_vendedor: string;
  facturas: number;
  total: number;
  ticket_promedio: number;
  variacion: number;
}

const MOCK_VENDEDORES: VendedorItem[] = [
  {
    nit_vendedor: "123456",
    nombre_vendedor: "Carlos Martínez",
    facturas: 245,
    total: 8_500_000,
    ticket_promedio: 34_693,
    variacion: 12.5,
  },
  {
    nit_vendedor: "234567",
    nombre_vendedor: "María López",
    facturas: 198,
    total: 6_200_000,
    ticket_promedio: 31_313,
    variacion: -3.2,
  },
  {
    nit_vendedor: "345678",
    nombre_vendedor: "Pedro Ramírez",
    facturas: 167,
    total: 4_800_000,
    ticket_promedio: 28_742,
    variacion: 8.1,
  },
];

// ── Page ───────────────────────────────────────────────────────

export default function VendedoresPage(): JSX.Element {
  // TODO: reemplazar por useVendedores() cuando Dev A2 cree el endpoint
  const data = MOCK_VENDEDORES;

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">
        ← Volver a inicio
      </Link>

      <div>
        <h1 className="text-xl font-bold text-text-primary">Vendedores</h1>
        <p className="text-sm text-text-muted">
          Rendimiento del mes actual — datos de muestra
        </p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-3 gap-3">
        <Card>
          <Stat
            label="Total vendido"
            value={formatMoney(data.reduce((s, v) => s + v.total, 0))}
            subtitle="este mes"
          />
        </Card>
        <Card>
          <Stat
            label="Facturas"
            value={data.reduce((s, v) => s + v.facturas, 0).toLocaleString("es-CO")}
            subtitle="este mes"
          />
        </Card>
        <Card>
          <Stat
            label="Vendedores"
            value={String(data.length)}
            subtitle="activos"
          />
        </Card>
      </div>

      {/* Tabla ranking */}
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
              cell: (v) => formatMoney(v.total),
              align: "right",
            },
            {
              header: "Ticket",
              cell: (v) => formatMoney(v.ticket_promedio),
              align: "right",
            },
            {
              header: "Δ",
              cell: (v) => <DeltaBadge value={v.variacion} />,
              align: "center",
            },
          ]}
          data={data}
          keyFn={(v) => v.nit_vendedor}
          striped
        />
      </Card>

      {/* Nota mock */}
      <p className="text-center text-xs text-text-muted">
        Datos de muestra — endpoint real en desarrollo por Dev A2
      </p>
    </div>
  );
}
