"use client";

import Link from "next/link";
import { useAbcSegmentation, useAbcDetalle } from "@/lib/api/hooks";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { AbcChart } from "@/components/AbcChart";
import { Skeleton } from "@/components/ui/Skeleton";

type BucketKey = "A" | "B" | "C";

type BucketConfig = {
  key: BucketKey;
  title: string;
  intent: string;
  action: string;
  variant: "success" | "warning" | "error";
  accent: string;
  borderClass: string;
};

type AbcDetalleItem = {
  cod_producto: string;
  nom_producto: string;
  valor_total: number;
  porcentaje_bucket: number;
};

const BUCKETS: BucketConfig[] = [
  {
    key: "A",
    title: "Alta prioridad",
    intent: "Productos que más sostienen los ingresos.",
    action: "Cuidar stock y evitar quiebres.",
    variant: "success",
    accent: "#16A34A",
    borderClass: "border-l-success",
  },
  {
    key: "B",
    title: "Prioridad media",
    intent: "Productos importantes, pero no críticos.",
    action: "Revisar reposición con rotación real.",
    variant: "warning",
    accent: "#D97706",
    borderClass: "border-l-warning",
  },
  {
    key: "C",
    title: "Baja contribución",
    intent: "Muchos SKUs con bajo impacto relativo.",
    action: "Evaluar descuentos, liquidación o menor compra.",
    variant: "error",
    accent: "#7B1818",
    borderClass: "border-l-primary",
  },
];

function formatCurrencyFull(value: number): string {
  return `$${Math.round(value || 0).toLocaleString("es-CO")}`;
}

function shortName(name: string, max = 58): string {
  return name.length > max ? `${name.slice(0, max).trim()}…` : name;
}

function BucketProducts({ config, items, isLoading }: { config: BucketConfig; items: AbcDetalleItem[]; isLoading: boolean }): JSX.Element {
  return (
    <Card className="overflow-hidden">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <Badge variant={config.variant} size="md">ABC {config.key}</Badge>
          <h2 className="mt-2 text-base font-black text-text-primary">{config.title}</h2>
          <p className="mt-1 text-xs text-text-muted">{config.intent}</p>
        </div>
        <div className="h-10 w-10 rounded-2xl" style={{ background: `${config.accent}22` }} />
      </div>

      <div className="rounded-2xl border border-border bg-surface-alt p-3 text-xs text-text-secondary">
        <span className="font-bold text-text-primary">Acción:</span> {config.action}
      </div>

      <div className="mt-3 space-y-2">
        {isLoading && Array.from({ length: 6 }).map((_, index) => <Skeleton key={index} className="h-14 rounded-xl" />)}
        {!isLoading && items.slice(0, 12).map((item, index) => (
          <article key={`${config.key}-${item.cod_producto}-${index}`} className="rounded-2xl border border-border bg-surface p-3 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
            <div className="flex items-start gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-xs font-black text-white" style={{ backgroundColor: config.accent }}>
                {index + 1}
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-mono text-[0.68rem] font-semibold text-primary">{item.cod_producto}</p>
                <p className="mt-0.5 text-sm font-semibold leading-snug text-text-primary" title={item.nom_producto}>{shortName(item.nom_producto)}</p>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-border">
                  <div className="h-full rounded-full" style={{ width: `${Math.min(100, Math.max(5, item.porcentaje_bucket))}%`, backgroundColor: config.accent }} />
                </div>
              </div>
              <div className="shrink-0 text-right">
                <p className="text-sm font-black text-text-primary">{formatCurrencyFull(item.valor_total)}</p>
                <p className="text-[0.68rem] text-text-muted">{item.porcentaje_bucket.toFixed(1)}%</p>
              </div>
            </div>
          </article>
        ))}
        {!isLoading && items.length === 0 && (
          <p className="py-8 text-center text-xs text-text-muted">Sin productos en ABC {config.key}</p>
        )}
      </div>
    </Card>
  );
}

export default function AbcPage(): JSX.Element {
  const { data, error, isLoading } = useAbcSegmentation();
  const detailA = useAbcDetalle("A", 50);
  const detailB = useAbcDetalle("B", 50);
  const detailC = useAbcDetalle("C", 50);

  const detailByBucket: Record<BucketKey, { items: AbcDetalleItem[]; isLoading: boolean }> = {
    A: { items: detailA.data?.items ?? [], isLoading: detailA.isLoading },
    B: { items: detailB.data?.items ?? [], isLoading: detailB.isLoading },
    C: { items: detailC.data?.items ?? [], isLoading: detailC.isLoading },
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-accent hover:underline">← Volver a inicio</Link>
        <Skeleton className="h-28 rounded-3xl" />
        <div className="grid gap-3 md:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-72 rounded-xl" />)}
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-accent hover:underline">← Volver a inicio</Link>
        <Card><p className="py-8 text-center text-text-muted">Error al cargar datos ABC</p></Card>
      </div>
    );
  }

  const summary = { A: data.bucket_a, B: data.bucket_b, C: data.bucket_c };

  return (
    <div className="space-y-4 pb-6">
      <Link href="/" className="text-sm text-accent hover:underline">← Volver a inicio</Link>

      <section className="relative overflow-hidden rounded-[2rem] border border-border bg-surface-dark p-5 text-text-inverse shadow-xl md:p-7">
        <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-primary/30 blur-3xl" />
        <div className="relative">
          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.3em] text-white/45">Segmentación ABC</p>
          <h1 className="mt-2 text-3xl font-black tracking-tight md:text-5xl">Qué productos sostienen la caja.</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-white/65">
            A, B y C no son etiquetas decorativas: indican dónde cuidar stock, dónde monitorear y dónde liberar capital.
          </p>
          <p className="mt-2 text-xs text-white/45">{data.business_month} · {data.total_skus.toLocaleString("es-CO")} SKUs · {formatCurrencyFull(data.total_ingresos)} ingresos</p>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-3">
        {BUCKETS.map((config) => {
          const bucket = summary[config.key];
          return (
            <Card key={config.key} className={`border-l-4 ${config.borderClass}`}>
              <div className="flex items-center justify-between gap-3">
                <Badge variant={config.variant} size="md">ABC {config.key}</Badge>
                <p className="text-xs font-semibold text-text-muted">{bucket.porcentaje_ingreso}% ingresos</p>
              </div>
              <p className="mt-3 text-3xl font-black text-text-primary">{bucket.num_skus.toLocaleString("es-CO")}</p>
              <p className="text-xs text-text-muted">productos</p>
              <p className="mt-2 text-sm font-bold text-text-primary">{formatCurrencyFull(bucket.valor_total)}</p>
            </Card>
          );
        })}
      </section>

      <Card header={<h2 className="font-semibold text-text-primary">Distribución ABC</h2>}>
        <AbcChart
          bucketA={data.bucket_a}
          bucketB={data.bucket_b}
          bucketC={data.bucket_c}
          explanations={{
            A: "Productos que más generan ingresos — cuidar stock",
            B: "Productos de contribución media — monitorear reposición",
            C: "Productos de baja contribución — revisar capital quieto",
          }}
        />
      </Card>

      <section className="grid gap-3 xl:grid-cols-3">
        {BUCKETS.map((config) => (
          <BucketProducts
            key={config.key}
            config={config}
            items={detailByBucket[config.key].items}
            isLoading={detailByBucket[config.key].isLoading}
          />
        ))}
      </section>
    </div>
  );
}
