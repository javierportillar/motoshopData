"use client";

import { useEffect, useState } from "react";

export function SyncStatus(): JSX.Element {
  const [online, setOnline] = useState(true);

  useEffect(() => {
    setOnline(navigator.onLine);

    const handleOnline = () => setOnline(true);
    const handleOffline = () => setOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  if (!online) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
        <span className="h-2 w-2 rounded-full bg-amber-400" />
        Sin conexión — datos cacheados
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-xs text-gray-500">
      <span className="h-2 w-2 rounded-full bg-green-400" />
      Conectado
    </div>
  );
}
