"use client";

import Link from "next/link";
import { Card } from "@/lib/ui/Card";

interface KpiCardProps {
  title: string;
  value: string;
  subtitle?: string;
  delta?: number | null;
  deltaLabel?: string;
  href?: string;
  icon?: React.ReactNode;
}

export function KpiCard({
  title,
  value,
  subtitle,
  delta,
  deltaLabel,
  href,
  icon,
}: KpiCardProps): JSX.Element {
  const content = (
    <div className="space-y-1">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-gray-500">
            {title}
          </p>
          <p className="text-2xl font-bold text-secondary-dark">{value}</p>
        </div>
        {icon && (
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
            {icon}
          </div>
        )}
      </div>
      {(delta !== undefined && delta !== null) || subtitle ? (
        <div className="flex items-center gap-2 text-xs">
          {delta !== undefined && delta !== null && (
            <span
              className={`inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 font-medium ${
                delta >= 0
                  ? "bg-green-50 text-green-700"
                  : "bg-red-50 text-red-700"
              }`}
            >
              {delta >= 0 ? "↑" : "↓"} {Math.abs(delta).toFixed(1)}%
            </span>
          )}
          {deltaLabel && <span className="text-gray-400">{deltaLabel}</span>}
          {subtitle && !deltaLabel && (
            <span className="text-gray-400">{subtitle}</span>
          )}
        </div>
      ) : null}
    </div>
  );

  if (href) {
    return (
      <Link href={href} className="block transition-opacity hover:opacity-80">
        <Card className="cursor-pointer">{content}</Card>
      </Link>
    );
  }

  return <Card>{content}</Card>;
}
