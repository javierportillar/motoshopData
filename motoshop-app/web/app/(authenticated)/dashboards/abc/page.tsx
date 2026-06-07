"use client";

import { useState } from "react";
import Link from "next/link";
import { useAbcSegmentation, useAbcDetalle } from "@/lib/api/hooks";
import { formatMoney } from "@/lib/format/currency";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { AbcChart } from "@/components/AbcChart";
import { Skeleton } from "@/components/ui/Skeleton";

const BUCKET_VARIANTS: Record<string, "error" | "warning" | "success"> = {
  A: "success",
  B: "warning",
  C: "error",
};

function BucketDetail({ bucket }: { bucket: string }): JSX.Element {
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useAbcDetalle(open ? bucket : null, 20);

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="mt-2 flex w-full items-center justify-between rounded-lg bg-surface-alt px-3 py-2 text-xs font-medium text-text-secondary hover:bg-surface-alt/80"
      >
        <span>{open ? "Ocultar detalle" : "Ver detalle de productos"}</span>
        <span className={`transition-transform ${open ? "rotate-180" : ""}`}>▼</span>
      </button>
      {open && (
        <div className="mt-2 space-y-1">
          {isLoading && (
            <div className="space-y-1">
              {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-8 rounded-lg" />)}
            </div>
          )}
          {data?.items.map((item) => (
            <div
              key={item.cod_producto}
              className="flex items-center justify-between rounded-lg bg-surface px-3 py-1.5"
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className="font-mono text-xs text-text-muted truncate">{item.cod_producto}</span>
                <span className="text-xs text-text-primary truncate">{item.nom_producto}</span>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <span className="text-xs text-text-muted">{item.porcentaje_bucket.toFixed(1)}%</span>
                <span className="text-xs font-medium text-text-primary">{formatMoney(item.valor_total)}</span>
              </div>
            </div>
          ))}
          {data && data.items.length === 0 && (
            <p className="py-4 text-center text-xs text-text-muted">Sin productos en este bucket</p>
          )}
        </div>
      )}
    </div>
  );
}


export default function AbcPage(): JSX.Element {
  const { data, error, isLoading } = useAbcSegmentation();

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

      {/* ¿Qué es ABC? */}
      <Card>
        <h2 className="mb-2 font-semibold text-text-primary">¿Qué es la segmentación ABC?</h2>
        <p className="text-sm text-text-muted leading-relaxed">
          Clasifica tus productos según su impacto en los ingresos. Ayuda a decidir
          dónde enfocar stock, atención y capital.
        </p>
        <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
          <div className="rounded-lg bg-success/10 p-2 text-center">
            <p className="font-bold text-success">A</p>
            <p className="text-text-secondary">20% productos → 80% ingresos</p>
            <p className="text-text-muted">Alta rotación</p>
          </div>
          <div className="rounded-lg bg-warning/10 p-2 text-center">
            <p className="font-bold text-warning">B</p>
            <p className="text-text-secondary">30% productos → 15% ingresos</p>
            <p className="text-text-muted">Rotación media</p>
          </div>
          <div className="rounded-lg bg-error/10 p-2 text-center">
            <p className="font-bold text-error">C</p>
            <p className="text-text-secondary">50% productos → 5% ingresos</p>
            <p className="text-text-muted">Baja rotación</p>
          </div>
        </div>
      </Card>

      {/* Insight accionable */}
      <Card>
        <div className="flex items-start gap-3">
          <span className="mt-0.5 text-lg">💡</span>
          <div>
            <p className="text-sm font-semibold text-text-primary">Insight accionable</p>
            <p className="text-sm text-text-muted">
              Priorizá stock de productos <strong className="text-success">A</strong> para
              evitar quiebres de los artículos que más venden. Revisá periódicamente los{" "}
              <strong className="text-error">C</strong> para evaluar liquidación o
              descuento.
            </p>
          </div>
        </div>
      </Card>

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
            <BucketDetail bucket={b.categoria} />
          </Card>
        ))}
      </div>

      {/* Chart */}
      <Card header={<h2 className="font-semibold text-text-primary">Distribución ABC</h2>}>
        <AbcChart
          bucketA={data.bucket_a}
          bucketB={data.bucket_b}
          bucketC={data.bucket_c}
          explanations={{
            A: "20% productos que generan 80% ingresos — alta rotación",
            B: "30% productos que generan 15% ingresos — rotación media",
            C: "50% productos que generan 5% ingresos — baja rotación",
          }}
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
