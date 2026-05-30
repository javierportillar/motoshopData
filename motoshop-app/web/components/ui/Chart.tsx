"use client";

import type { ReactNode } from "react";
import { CartesianGrid, ResponsiveContainer, XAxis, YAxis } from "recharts";

// ─── Tipos ──────────────────────────────────────────────────────

type ChartColor = 1 | 2 | 3 | 4 | 5;

interface PayloadEntry {
  name?: string;
  value?: number;
  color?: string;
  payload?: Record<string, unknown>;
}

interface ChartTooltipProps {
  active?: boolean;
  payload?: PayloadEntry[];
  label?: string;
}

interface ChartProps {
  children: ReactNode;
  /** Tema oscuro (default true — consistente con header/sidebar MotoShop) */
  dark?: boolean;
  /** Altura del contenedor (default: 320px) */
  height?: number;
  /** Margen interno */
  margin?: { top: number; right: number; bottom: number; left: number };
  className?: string;
}

// ─── Colores del chart desde tokens ─────────────────────────────

const CHART_COLORS: Record<ChartColor, string> = {
  1: "#C83828",
  2: "#0EA5E9",
  3: "#16A34A",
  4: "#D97706",
  5: "#7C3AED",
};

const CHART_COLORS_ARRAY = Object.values(CHART_COLORS);

// ─── Tooltip personalizado — estilo diagnóstico mecánico ───────

function MotoTooltip({
  active,
  payload,
  label,
}: ChartTooltipProps): JSX.Element | null {
  if (!active || !payload?.length) return null;

  return (
    <div className="rounded-lg border border-surface-dark-alt bg-surface-dark px-3 py-2 shadow-lg">
      {label && (
        <p className="mb-1 text-xs font-medium uppercase tracking-wider text-text-muted">
          {label}
        </p>
      )}
      {payload.map((entry, i) => (
        <div key={i} className="flex items-center gap-2 text-sm">
          <span
            className="h-2.5 w-2.5 rounded-sm"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-text-inverse font-medium">
            {entry.value?.toLocaleString("es-CO")}
          </span>
          <span className="text-text-muted text-xs">{entry.name}</span>
        </div>
      ))}
    </div>
  );
}

// ─── Componente ─────────────────────────────────────────────────

/**
 * Chart — wrapper industrial para recharts con estética MotoShop.
 *
 * Tema oscuro por defecto (consistente con header/sidebar).
 * Grid sutil como papel milimetrado de taller.
 * Tooltip estilo diagnóstico de tablero de moto.
 * Colores rotan entre chart-1..chart-5.
 *
 * @example
 * ```tsx
 * <Chart height={280}>
 *   <LineChart data={data}>
 *     <Line dataKey="ventas" stroke={chartColor(1)} strokeWidth={2} />
 *   </LineChart>
 * </Chart>
 * ```
 */
export function Chart({
  children,
  dark = true,
  height = 320,
  margin = { top: 8, right: 12, bottom: 8, left: 12 },
  className = "",
}: ChartProps): JSX.Element {
  return (
    <div
      className={`relative overflow-hidden rounded-xl border ${
        dark
          ? "border-surface-dark-alt bg-surface-dark"
          : "border-border bg-surface"
      } ${className}`}
      style={{ height }}
    >
      {/* Fondo texturizado sutil — ruido de taller */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            "radial-gradient(circle, currentColor 1px, transparent 1px)",
          backgroundSize: "16px 16px",
          color: dark ? "#FFFFFF" : "#101010",
        }}
      />

      <ResponsiveContainer width="100%" height="100%">
        {children as React.ReactElement}
      </ResponsiveContainer>

      {/* Tooltip global del chart (se inyecta vía children) */}
      {/* Recharts maneja el render del tooltip internamente */}
    </div>
  );
}

// ─── Helpers exportados ─────────────────────────────────────────

/** Color del chart por índice (1-5). Cicla si > 5. */
export function chartColor(n: number): string {
  return CHART_COLORS_ARRAY[(n - 1) % CHART_COLORS_ARRAY.length]!;
}

/** Array de 5 colores para series múltiples. */
export function chartPalette(): string[] {
  return [...CHART_COLORS_ARRAY];
}

/** Tooltip personalizado MotoShop (pasar como `content` a `<Tooltip>`) */
export { MotoTooltip as ChartTooltip };

// ─── Grid component para charts internos ─────────────────────────

interface ChartGridProps {
  dark?: boolean;
}

export function ChartGrid({ dark = true }: ChartGridProps): JSX.Element {
  return (
    <>
      <CartesianGrid
        stroke={dark ? "#262626" : "#E5E5E5"}
        strokeDasharray="4 4"
        strokeWidth={0.5}
        vertical={false}
      />
      <XAxis
        tick={{
          fill: dark ? "#737373" : "#525252",
          fontSize: 11,
          fontFamily: "Inter, sans-serif",
        }}
        axisLine={false}
        tickLine={false}
        dy={8}
      />
      <YAxis
        tick={{
          fill: dark ? "#737373" : "#525252",
          fontSize: 11,
          fontFamily: "Inter, sans-serif",
        }}
        axisLine={false}
        tickLine={false}
        dx={-4}
      />
    </>
  );
}
