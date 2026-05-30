"use client";

import { formatMoney } from "@/lib/format/currency";

interface TopListItem {
  label: string;
  value: number;
  secondary?: string;
  rank: number;
}

interface TopListProps {
  items: TopListItem[];
  formatValue?: (v: number) => string;
  maxItems?: number;
}

function defaultFormat(v: number): string {
  return formatMoney(v);
}

export function TopList({
  items,
  formatValue = defaultFormat,
  maxItems = 10,
}: TopListProps): JSX.Element {
  if (!items || items.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-sm text-gray-400">
        Sin datos
      </div>
    );
  }

  const displayed = items.slice(0, maxItems);
  const maxVal = Math.max(...displayed.map((i) => i.value));

  return (
    <div className="space-y-2">
      {displayed.map((item) => (
        <div key={item.rank} className="flex items-center gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
            {item.rank}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline justify-between gap-2">
              <p className="truncate text-sm font-medium text-secondary-dark">
                {item.label}
              </p>
              <span className="shrink-0 text-sm font-semibold text-secondary">
                {formatValue(item.value)}
              </span>
            </div>
            {item.secondary && (
              <p className="text-xs text-gray-400">{item.secondary}</p>
            )}
            {/* Barra de progreso relativa */}
            <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{
                  width: `${Math.max(2, (item.value / maxVal) * 100)}%`,
                }}
              />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
