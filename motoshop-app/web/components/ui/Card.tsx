import type { ReactNode } from "react";

type CardVariant = "default" | "dark" | "bordered";

interface CardProps {
  children: ReactNode;
  header?: ReactNode;
  footer?: ReactNode;
  /** default: surface blanco, dark: surfaceDark #171717, bordered: borde visible sin shadow */
  variant?: CardVariant;
  /** Hover: levanta shadow (default true para default variant) */
  hover?: boolean;
  className?: string;
}

const variantStyles: Record<CardVariant, string> = {
  default: "bg-surface border border-border shadow-sm",
  dark: "bg-surface-dark text-text-inverse border border-surface-dark-alt shadow-sm",
  bordered: "bg-surface border border-border-strong",
};

const hoverStyles: Record<CardVariant, string> = {
  default: "transition-shadow hover:shadow-md",
  dark: "transition-shadow hover:shadow-lg hover:border-surface-dark",
  bordered: "transition-shadow hover:shadow-sm",
};

/**
 * Card — contenedor estándar del design system MotoShop.
 *
 * Variantes:
 * - `default`: surface blanco con borde sutil y shadow (cards, paneles)
 * - `dark`: surface oscuro para headers, sidebars, wraps de logo
 * - `bordered`: borde fuerte sin shadow (inputs groups, listas)
 */
export function Card({
  children,
  header,
  footer,
  variant = "default",
  hover = true,
  className = "",
}: CardProps): JSX.Element {
  return (
    <div
      className={`overflow-hidden rounded-xl ${variantStyles[variant]} ${hover ? hoverStyles[variant] : ""} ${className}`}
    >
      {header && (
        <div className="border-b border-border px-4 py-3 font-medium text-text-primary">
          {header}
        </div>
      )}
      <div className="p-4">{children}</div>
      {footer && (
        <div className="border-t border-border px-4 py-3 text-sm text-text-muted">
          {footer}
        </div>
      )}
    </div>
  );
}
