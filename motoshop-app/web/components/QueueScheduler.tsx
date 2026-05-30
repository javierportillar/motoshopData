"use client";

import { useEffect } from "react";
import { startQueueScheduler, stopQueueScheduler } from "@/lib/offline/queue";

/** Componente invisible que arranca el scheduler de cola offline. */
export function QueueScheduler(): null {
  useEffect(() => {
    startQueueScheduler();
    return () => stopQueueScheduler();
  }, []);

  return null;
}
