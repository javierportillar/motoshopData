import type { ReactNode } from "react";

type BadgeVariant = "success" | "warning" | "error" | "info" | "default";

type BadgeSize = "sm" | "md";

interface BadgeProps {
  variant?: BadgeVariant;
  /** sm: más compacto para tablas densas, md: default */
  size?: BadgeSize;
  children: ReactNode;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  success: "bg-success/10 text-success",
  warning: "bg-warning/10 text-warning",
  error: "bg-error/10 text-error",
  info: "bg-info/10 text-info",
  default: "bg-surface-alt text-text-secondary",
};

const sizeStyles: Record<BadgeSize, string> = {
  sm: "px-1.5 py-0 text-[0.625rem]",
  md: "px-2 py-0.5 text-xs",
};

/**
 * Badge — etiqueta de estado del design system MotoShop.
 *
 * Usa tokens semánticos de color con opacidad (ej: bg-success/10).
 * Variantes: success (verde), warning (ámbar), error (rojo oscuro),
 * info (azul), default (neutro).
 *
 * Diferencia clave con lib/ui/Badge: esta versión usa tokens
 * MotoShop en lugar de Tailwind green-100/800, amber-100/800, etc.
 */
export function Badge({
  variant = "default",
  size = "md",
  children,
  className = "",
}: BadgeProps): JSX.Element {
  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${sizeStyles[size]} ${variantStyles[variant]} ${className}`}
    >
      {children}
    </span>
  );
}

// ─── Compuestos ────────────────────────────────────────────

/** Badge con indicador de stock (usa colores semánticos MotoShop) */
export function StockBadge({ qty }: { qty: number }): JSX.Element {
  if (qty === 0) return <Badge variant="error">Sin stock</Badge>;
  if (qty <= 4) return <Badge variant="warning">{qty} uds</Badge>;
  return <Badge variant="success">{qty} uds</Badge>;
}

/** Badge para mostrar delta porcentual (usar en tablas/dashboards) */
export function DeltaBadge({
  value,
}: {
  value: number;
}): JSX.Element {
  if (value > 0) {
    return <Badge variant="success">↑ {value.toFixed(1)}%</Badge>;
  }
  if (value < 0) {
    return <Badge variant="error">↓ {Math.abs(value).toFixed(1)}%</Badge>;
  }
  return <Badge variant="default">→ 0%</Badge>;
}

/** Badge de severidad para alertas */
export function AlertBadge({
  severity,
}: {
  severity: "critical" | "warning" | "info";
}): JSX.Element {
  const map: Record<string, { variant: BadgeVariant; label: string }> = {
    critical: { variant: "error", label: "Crítica" },
    warning: { variant: "warning", label: "Atención" },
    info: { variant: "info", label: "Info" },
  };
  const { variant, label } = map[severity] ?? {
    variant: "default" as BadgeVariant,
    label: severity,
  };
  return <Badge variant={variant}>{label}</Badge>;
}
