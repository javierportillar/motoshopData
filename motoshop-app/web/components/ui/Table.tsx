import type { ReactNode } from "react";

type ColumnAlignment = "left" | "center" | "right";

interface Column<T> {
  /** Header content (string or ReactNode) */
  header: ReactNode;
  /** Render function for each row */
  cell: (row: T, index: number) => ReactNode;
  /** Column alignment (default: left) */
  align?: ColumnAlignment;
  /** Tailwind classes for the cell */
  className?: string;
}

interface TableProps<T> {
  /** Column definitions */
  columns: Column<T>[];
  /** Data rows */
  data: T[];
  /** Unique key extractor (required for React key) */
  keyFn: (row: T, index: number) => string;
  /** Striped rows (alternate bg) */
  striped?: boolean;
  /** Hover highlight rows */
  hover?: boolean;
  /** Empty state message */
  emptyMessage?: string;
  className?: string;
}

const alignStyles: Record<ColumnAlignment, string> = {
  left: "text-left",
  center: "text-center",
  right: "text-right",
};

/**
 * Table — tabla de datos del design system MotoShop.
 *
 * Genérica sobre el tipo de datos <T>.
 * Usa tokens semánticos: bg-surface, text-text-primary, border-border.
 *
 * @example
 * ```tsx
 * <Table
 *   columns={[
 *     { header: "Producto", cell: (r) => r.nombre },
 *     { header: "Stock", cell: (r) => r.stock, align: "right" },
 *   ]}
 *   data={productos}
 *   keyFn={(r) => r.codigo}
 * />
 * ```
 */
export function Table<T>({
  columns,
  data,
  keyFn,
  striped = false,
  hover = true,
  emptyMessage = "Sin datos",
  className = "",
}: TableProps<T>): JSX.Element {
  if (data.length === 0) {
    return (
      <div
        className={`rounded-xl border border-border bg-surface p-8 text-center text-text-muted ${className}`}
      >
        {emptyMessage}
      </div>
    );
  }

  return (
    <div
      className={`overflow-hidden rounded-xl border border-border bg-surface ${className}`}
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          {/* Header */}
          <thead>
            <tr className="border-b border-border bg-surface-alt">
              {columns.map((col, i) => (
                <th
                  key={i}
                  className={`px-4 py-3 font-medium text-text-secondary ${alignStyles[col.align ?? "left"]} ${col.className ?? ""}`}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>

          {/* Body */}
          <tbody className="divide-y divide-border">
            {data.map((row, rowIdx) => (
              <tr
                key={keyFn(row, rowIdx)}
                className={
                  [
                    striped && rowIdx % 2 === 1 ? "bg-surface-alt/50" : "",
                    hover ? "transition-colors hover:bg-surface-alt" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")
                }
              >
                {columns.map((col, colIdx) => (
                  <td
                    key={colIdx}
                    className={`px-4 py-3 text-text-primary ${alignStyles[col.align ?? "left"]} ${col.className ?? ""}`}
                  >
                    {col.cell(row, rowIdx)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
