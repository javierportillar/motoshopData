"use client";

import Link from "next/link";
import { useAbcSegmentation } from "@/lib/api/hooks";
import { formatMoney } from "@/lib/format/currency";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";
import { Badge } from "@/components/ui/Badge";
import { AbcChart } from "@/components/AbcChart";

const BUCKET_VARIANTS: Record<string, "error" | "warning" | "success"> = {
  A: "success",
  B: "warning",
  C: "error",
};

export default function AbcPage(): JSX.Element {
  const { data, error, isLoading } = useAbcSegmentation();

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
            Error al cargar datos ABC
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
        <h1 className="text-xl font-bold text-text-primary">
          Segmentación ABC
        </h1>
        <p className="text-sm text-text-muted">
          {data.business_month} — {data.total_skus} SKUs
        </p>
      </div>

      {/* Buckets */}
      <div className="grid grid-cols-3 gap-3">
        {[data.bucket_a, data.bucket_b, data.bucket_c].map((b) => (
          <Card key={b.categoria}>
            <div className="flex flex-col items-center gap-1 text-center">
              <Badge
                variant={BUCKET_VARIANTS[b.categoria] ?? "default"}
                size="md"
              >
                {b.categoria}
              </Badge>
              <p className="text-2xl font-bold text-text-primary">{b.num_skus}</p>
              <p className="text-xs text-text-muted">
                {b.porcentaje_ingreso}% ingresos
              </p>
            </div>
          </Card>
        ))}
      </div>

      {/* Chart */}
      <Card header={<h2 className="font-semibold text-text-primary">Distribución ABC</h2>}>
        <AbcChart
          bucketA={data.bucket_a}
          bucketB={data.bucket_b}
          bucketC={data.bucket_c}
        />
      </Card>

      {/* Resumen por categoría */}
      <Card header={<h2 className="font-semibold text-text-primary">Resumen por categoría</h2>}>
        <div className="space-y-2">
          {[data.bucket_a, data.bucket_b, data.bucket_c].map((b) => (
            <div
              key={b.categoria}
              className="flex items-center justify-between rounded-lg bg-surface-alt p-3"
            >
              <div className="flex items-center gap-3">
                <Badge
                  variant={BUCKET_VARIANTS[b.categoria] ?? "default"}
                  size="md"
                >
                  {b.categoria}
                </Badge>
                <div>
                  <p className="text-sm font-medium text-text-primary">
                    {b.num_skus} SKUs
                  </p>
                  <p className="text-xs text-text-muted">
                    {b.porcentaje_ingreso}% de ingresos
                  </p>
                </div>
              </div>
              <span className="text-sm font-semibold text-text-primary">
                {formatMoney(b.valor_total)}
              </span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
