type BadgeVariant = "success" | "warning" | "error" | "default";

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  success: "bg-green-100 text-green-800",
  warning: "bg-amber-100 text-amber-800",
  error: "bg-red-100 text-red-800",
  default: "bg-gray-100 text-gray-700",
};

export function Badge({
  variant = "default",
  children,
  className = "",
}: BadgeProps): JSX.Element {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${variantStyles[variant]} ${className}`}
    >
      {children}
    </span>
  );
}

export function StockBadge({ qty }: { qty: number }): JSX.Element {
  if (qty === 0) return <Badge variant="error">Sin stock</Badge>;
  if (qty <= 4) return <Badge variant="warning">{qty} uds</Badge>;
  return <Badge variant="success">{qty} uds</Badge>;
}
