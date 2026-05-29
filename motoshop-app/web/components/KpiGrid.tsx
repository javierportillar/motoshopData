"use client";

import type { ReactNode } from "react";

interface KpiGridProps {
  children: ReactNode;
  className?: string;
}

export function KpiGrid({
  children,
  className = "",
}: KpiGridProps): JSX.Element {
  return (
    <div
      className={`flex flex-col gap-4 md:grid md:grid-cols-2 lg:grid-cols-3 ${className}`}
    >
      {children}
    </div>
  );
}
