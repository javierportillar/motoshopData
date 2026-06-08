"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth/store";
import {
  usePipelineRuns,
  usePipelineRun,
  usePipelineSummary,
  type PipelineRun,
  type PipelineStep,
} from "@/lib/api/hooks";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Table } from "@/components/ui/Table";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";

// ── Helpers ──────────────────────────────────────────────────────────

function statusLabel(s: string): string {
  if (s === "running") return "En ejecución";
  if (s === "success") return "Exitosa";
  if (s === "failed") return "Fallida";
  return s;
}

function statusBadge(s: string) {
  if (s === "running") return "info" as const;
  if (s === "success") return "success" as const;
  if (s === "failed") return "error" as const;
  return "default" as const;
}

function formatDuration(sec: number | null): string {
  if (sec == null) return "—";
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}m ${s}s`;
}

function isStaleRunning(run: PipelineRun): boolean {
  if (run.status !== "running" || !run.started_at) return false;
  const elapsed = (Date.now() - new Date(run.started_at).getTime()) / 1000 / 60;
  return elapsed > 60;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-CO", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

// ── Step Detail Modal ────────────────────────────────────────────────

function StepDetail({ step }: { step: PipelineStep }) {
  return (
    <div className="rounded-lg border border-border bg-surface-alt px-3 py-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Badge variant={statusBadge(step.status)} size="sm">
            {statusLabel(step.status)}
          </Badge>
          <span className="text-sm font-medium text-text-primary">{step.step_name}</span>
        </div>
        <span className="text-xs text-text-muted">
          {step.rows_processed != null ? `${step.rows_processed.toLocaleString("es-CO")} filas` : ""}
          {step.duration_seconds != null ? ` · ${formatDuration(step.duration_seconds)}` : ""}
        </span>
      </div>
      {step.error_message && (
        <p className="mt-1 text-xs text-error">{step.error_message}</p>
      )}
      {step.log_excerpt && (
        <details className="mt-1">
          <summary className="cursor-pointer text-xs text-text-muted">Mostrar registro</summary>
          <pre className="mt-1 max-h-32 overflow-auto rounded bg-surface-dark px-2 py-1 text-[0.625rem] text-text-inverse/70">
            {step.log_excerpt}
          </pre>
        </details>
      )}
    </div>
  );
}

// ── Run Detail Modal ─────────────────────────────────────────────────

function RunDetail({ runId, onClose }: { runId: number; onClose: () => void }) {
  const { data, isLoading } = usePipelineRun(runId);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="mx-4 max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-xl bg-surface p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold text-text-primary">Detalle de corrida #{runId}</h2>
          <button onClick={onClose} className="text-sm text-text-muted hover:text-text-primary">✕</button>
        </div>
        {isLoading && (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 rounded-lg" />)}
          </div>
        )}
        {data && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs text-text-muted">
              <Badge variant={statusBadge(data.status)} size="sm">{statusLabel(data.status)}</Badge>
              <span>Inicio: {formatDate(data.started_at)}</span>
              {data.duration_seconds != null && <span>· {formatDuration(data.duration_seconds)}</span>}
            </div>
            {data.error_message && (
              <p className="text-xs text-error">{data.error_message}</p>
            )}
            {data.log_excerpt && (
              <details className="mt-1">
                <summary className="cursor-pointer text-xs text-text-muted">Registro completo</summary>
                <pre className="mt-1 max-h-40 overflow-auto rounded bg-surface-dark px-2 py-1 text-[0.625rem] text-text-inverse/70">
                  {data.log_excerpt}
                </pre>
              </details>
            )}
            {data.steps && data.steps.length > 0 && (
              <>
                <h3 className="mt-3 text-xs font-semibold uppercase tracking-wider text-text-muted">Pasos de la corrida</h3>
                <div className="space-y-1.5">
                  {data.steps.map((step) => (
                    <StepDetail key={step.id} step={step} />
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Summary Cards ────────────────────────────────────────────────────

function SummaryCards() {
  const { data, isLoading } = usePipelineSummary();
  if (isLoading) return <Card><Skeleton className="h-20 rounded-xl" /></Card>;
  if (!data) return null;

  const cards = [
    { label: "Última corrida", value: data.last_run_status ? statusLabel(data.last_run_status) : "Sin datos",
      sub: data.last_run_finished_at ? formatDate(data.last_run_finished_at) : "" },
    { label: "Efectividad 30d", value: `${data.success_rate_30d_pct.toFixed(0)}%`,
      sub: `${data.total_runs_30d} corridas` },
    { label: "Duración promedio", value: formatDuration(Math.round(data.avg_duration_seconds)),
      sub: "últimos 30 días" },
    { label: "Total corridas", value: String(data.total_runs_30d),
      sub: "últimos 30 días" },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {cards.map((c) => (
        <Card key={c.label}>
          <div className="flex flex-col gap-0.5">
            <p className="text-xs font-medium uppercase tracking-wider text-text-muted">{c.label}</p>
            <p className="text-xl font-bold text-text-primary">{c.value}</p>
            {c.sub && <p className="text-xs text-text-muted">{c.sub}</p>}
          </div>
        </Card>
      ))}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────

export default function PipelinePage(): JSX.Element {
  const router = useRouter();
  const role = useAuthStore((s) => s.role);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [selectedRun, setSelectedRun] = useState<number | null>(null);
  const { data, error, isLoading } = usePipelineRuns(30, "refresh_v15", statusFilter || undefined);

  // Redirect vendedor
  if (role === "vendedor") {
    router.push("/");
    return <></>;
  }

  const runs = data?.runs ?? [];

  if (error) return <ErrorState title="Error" message="No se pudieron cargar los datos del pipeline." severity="warning" />;

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">← Volver a inicio</Link>

      <div>
        <h1 className="text-xl font-bold text-text-primary">Actualización de datos</h1>
        <p className="text-sm text-text-muted">Estado de las corridas del pipeline de datos</p>
      </div>

      <SummaryCards />

      {/* Filter chips */}
      <div className="flex flex-wrap gap-2">
        {["", "success", "running", "failed"].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              statusFilter === s
                ? "bg-primary text-primary-fg"
                : "bg-surface-alt text-text-secondary hover:bg-surface-alt/80"
            }`}
          >
            {s === "" ? "Todas" : statusLabel(s)}
          </button>
        ))}
      </div>

      {/* Runs table */}
      {isLoading && (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-12 rounded-lg" />)}
        </div>
      )}

      {!isLoading && runs.length === 0 && (
        <Card>
          <p className="py-8 text-center text-sm text-text-muted">
            No hay corridas registradas para los filtros seleccionados.
          </p>
        </Card>
      )}

      {!isLoading && runs.length > 0 && (
        <Card header={<h2 className="font-semibold text-text-primary">Últimas corridas</h2>}>
          <div className="overflow-x-auto">
            <Table
              columns={[
                { header: "ID", cell: (r: PipelineRun) => <span className="font-mono text-xs">#{r.id}</span> },
                {
                  header: "Estado",
                  cell: (r: PipelineRun) => (
                    <div className="flex items-center gap-1">
                      <Badge variant={statusBadge(r.status)} size="sm">{statusLabel(r.status)}</Badge>
                      {isStaleRunning(r) && (
                        <Badge variant="warning" size="sm">Revisar</Badge>
                      )}
                    </div>
                  ),
                },
                { header: "Inicio", cell: (r: PipelineRun) => <span className="text-xs">{formatDate(r.started_at)}</span> },
                { header: "Fin", cell: (r: PipelineRun) => <span className="text-xs">{formatDate(r.finished_at)}</span> },
                { header: "Duración", cell: (r: PipelineRun) => <span className="text-xs">{formatDuration(r.duration_seconds)}</span> },
                { header: "Filas", cell: (r: PipelineRun) => <span className="text-xs">{r.rows_processed?.toLocaleString("es-CO") ?? "—"}</span> },
                {
                  header: "",
                  cell: (r: PipelineRun) => (
                    <button
                      onClick={() => setSelectedRun(r.id)}
                      className="text-xs font-medium text-accent hover:underline"
                    >
                      Detalle
                    </button>
                  ),
                },
              ]}
              data={runs}
              keyFn={(r: PipelineRun) => String(r.id)}
              striped
            />
          </div>
        </Card>
      )}

      {/* Detail modal */}
      {selectedRun != null && (
        <RunDetail runId={selectedRun} onClose={() => setSelectedRun(null)} />
      )}
    </div>
  );
}
