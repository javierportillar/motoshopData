"use client";

import { useEffect, useState } from "react";
import { getQueueCount } from "@/lib/offline/queue";

export function OfflineQueueBadge(): JSX.Element | null {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let mounted = true;
    let interval: ReturnType<typeof setInterval>;

    async function refresh() {
      if (!mounted) return;
      const n = await getQueueCount();
      if (mounted) setCount(n);
    }

    refresh();
    interval = setInterval(refresh, 5_000);

    const onFlush = () => setTimeout(refresh, 500);
    window.addEventListener("queue-flushed", onFlush);

    return () => {
      mounted = false;
      clearInterval(interval);
      window.removeEventListener("queue-flushed", onFlush);
    };
  }, []);

  if (count === 0) return null;

  return (
    <div className="fixed bottom-20 right-4 z-50 flex items-center gap-2 rounded-full bg-amber-400 px-3 py-1.5 text-xs font-medium text-amber-900 shadow-lg">
      <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="10" />
        <polyline points="12,6 12,12 16,14" />
      </svg>
      {count} acción{count !== 1 ? "es" : ""} pendiente{count !== 1 ? "s" : ""}
    </div>
  );
}
