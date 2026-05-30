"use client";

import Link from "next/link";
import { useDormidos } from "@/lib/api/hooks";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Badge } from "@/components/ui/Badge";

function dormancyVariant(dias: number): "error" | "warning" | "default" {
  if (dias > 180) return "error";
  if (dias >= 90) return "warning";
  return "default";
}

export default function DormidosPage(): JSX.Element {
  const { data, error, isLoading } = useDormidos();

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
            Error al cargar datos de productos dormidos
          </p>
        </Card>
      </div>
    );
  }

  const criticos = data.productos.filter((p) => p.dias_sin_venta > 180).length;

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

      {/* Lista de dormidos */}
      <Card header={<h2 className="font-semibold text-text-primary">Lista de dormidos</h2>}>
        {data.productos.length === 0 ? (
          <p className="py-8 text-center text-sm text-text-muted">
            No hay productos dormidos en este período
          </p>
        ) : (
          <div className="space-y-2">
            {data.productos.map((p) => (
              <div
                key={p.cod_producto}
                className="flex items-center justify-between rounded-lg bg-surface-alt p-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-text-primary">
                    {p.nom_producto}
                  </p>
                  <p className="font-mono text-xs text-text-muted">{p.cod_producto}</p>
                </div>
                <div className="ml-2 shrink-0 text-right">
                  <Badge variant={dormancyVariant(p.dias_sin_venta)} size="md">
                    {p.dias_sin_venta}d
                  </Badge>
                  {p.stock_actual != null && (
                    <p className="mt-1 text-xs text-text-muted">
                      Stock: {p.stock_actual.toLocaleString("es-CO")}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
