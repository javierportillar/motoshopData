"use client";

import Link from "next/link";
import { useInventorySummary } from "@/lib/api/hooks";
import { formatMoney } from "@/lib/format/currency";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Badge } from "@/components/ui/Badge";

export default function InventarioPage(): JSX.Element {
  const { data, error, isLoading } = useInventorySummary();

  // ── Loading ──────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-accent hover:underline">
          ← Volver a inicio
        </Link>
        <div className="h-5 w-24 animate-pulse rounded bg-surface-alt" />
        <div className="grid grid-cols-2 gap-3">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-surface-alt" />
          ))}
        </div>
        <div className="h-60 animate-pulse rounded-xl bg-surface-alt" />
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
            Error al cargar datos de inventario
          </p>
        </Card>
      </div>
    );
  }

  // ── Render ───────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">
        ← Volver a inicio
      </Link>

      <div>
        <h1 className="text-xl font-bold text-text-primary">Inventario</h1>
        <p className="text-sm text-text-muted">
          {data.num_productos} productos en total
        </p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 gap-3">
        <Card>
          <Stat
            label="Stock total"
            value={data.stock_total.toLocaleString("es-CO")}
            subtitle="unidades"
          />
        </Card>
        <Card>
          <Stat
            label="Valor estimado"
            value={formatMoney(data.valor_total)}
            subtitle="costo total"
          />
        </Card>
      </div>

      {/* Stock por bodega */}
      {data.por_bodega.length > 0 && (
        <Card header={<h2 className="font-semibold text-text-primary">Stock por bodega</h2>}>
          <div className="space-y-2">
            {data.por_bodega.map((b) => (
              <div
                key={b.cod_bodega}
                className="flex items-center justify-between rounded-lg bg-surface-alt p-3"
              >
                <div>
                  <p className="text-sm font-medium text-text-primary">
                    {b.nom_bodega}
                  </p>
                  <p className="font-mono text-xs text-text-muted">{b.cod_bodega}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-semibold text-text-primary">
                    {b.cantidad.toLocaleString("es-CO")}
                  </p>
                  <Badge variant="default" size="sm">{b.porcentaje}%</Badge>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
