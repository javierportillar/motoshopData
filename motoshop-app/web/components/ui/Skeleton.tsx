"use client";

// ─── Keyframe shimmer metálico — reflejo de cromo sobre acero ───
// Inyectado vía <style> para evitar dependencia de Tailwind config

const shimmerStyles = `
@keyframes shimmer-metal {
  0%   { transform: translateX(-100%) skewX(-12deg); }
  100% { transform: translateX(200%) skewX(-12deg); }
}
@keyframes pulse-metal {
  0%, 100% { opacity: 0.4; }
  50%      { opacity: 0.7; }
}
`;

// ─── Componentes ─────────────────────────────────────────────────

interface SkeletonProps {
  className?: string;
}

/**
 * Skeleton — loading state con shimmer metálico.
 *
 * En vez de gris plano genérico, usa un gradiente de acero oscuro
 * con reflejo diagonal cromado. Sugiere precisión mecánica incluso
 * mientras carga — como ver el reflejo en una pieza de motor.
 */
export function Skeleton({ className = "" }: SkeletonProps): JSX.Element {
  return (
    <>
      <style>{shimmerStyles}</style>
      <div
        aria-hidden="true"
        className={`relative overflow-hidden rounded bg-surface-alt ${className}`}
      >
        {/* Base sólida */}
        <div className="absolute inset-0 bg-surface-alt" />

        {/* Reflejo cromado diagonal */}
        <div
          className="absolute inset-y-0 w-1/2 bg-gradient-to-r from-transparent via-white/[0.06] to-transparent"
          style={{
            animation: "shimmer-metal 1.8s ease-in-out infinite",
          }}
        />

        {/* Pulso de opacidad para variación rítmica */}
        <div
          className="absolute inset-0 bg-surface-dark/5"
          style={{
            animation: "pulse-metal 2.4s ease-in-out infinite",
          }}
        />
      </div>
    </>
  );
}

// ─── Compuestos ──────────────────────────────────────────────────

/** SkeletonCard — placeholder de Card durante carga */
export function SkeletonCard(): JSX.Element {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface p-4 shadow-sm">
      <div className="space-y-3">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
        <Skeleton className="h-3 w-full" />
        <div className="flex gap-2 pt-2">
          <Skeleton className="h-6 w-16 rounded-full" />
          <Skeleton className="h-6 w-20 rounded-full" />
        </div>
      </div>
    </div>
  );
}

/** SkeletonStat — placeholder de Stat durante carga */
export function SkeletonStat(): JSX.Element {
  return (
    <div className="space-y-2">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-7 w-32" />
      <Skeleton className="h-3 w-20" />
    </div>
  );
}

/** SkeletonTable — placeholder de tabla con N filas */
export function SkeletonTable({ rows = 5 }: { rows?: number }): JSX.Element {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface">
      {/* Header */}
      <div className="flex gap-4 border-b border-border bg-surface-alt px-4 py-3">
        <Skeleton className="h-4 w-1/4" />
        <Skeleton className="h-4 w-1/4" />
        <Skeleton className="h-4 w-1/4" />
        <Skeleton className="h-4 w-1/6" />
      </div>

      {/* Rows */}
      <div className="divide-y divide-border">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex gap-4 px-4 py-3">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-4 w-1/4" />
            <Skeleton className="h-4 w-1/5" />
            <Skeleton className="h-5 w-12 rounded-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** SkeletonList — N SkeletonCards en columna */
export function SkeletonList({ count = 5 }: { count?: number }): JSX.Element {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}
