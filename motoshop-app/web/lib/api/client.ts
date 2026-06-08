let refreshPromise: Promise<boolean> | null = null;

async function doRefresh(): Promise<boolean> {
  try {
    const resp = await fetch("/api/auth/refresh", { method: "POST" });
    return resp.ok;
  } catch {
    return false;
  }
}

export async function apiFetch(
  input: string,
  init?: RequestInit,
): Promise<Response> {
  const resp = await fetch(input, { ...init, credentials: "include" });

  if (resp.status === 401) {
    if (!refreshPromise) {
      refreshPromise = doRefresh().finally(() => {
        refreshPromise = null;
      });
    }

    const ok = await refreshPromise;
    if (!ok) {
      // Clear stale auth state before redirecting to login
      try {
        const { useAuthStore } = await import("@/lib/auth/store");
        useAuthStore.getState().logout();
      } catch {
        // Zustand might not be available in SSR context, ignore
      }
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
      return resp;
    }

    return fetch(input, { ...init, credentials: "include" });
  }

  return resp;
}

export async function apiFetchJson<T = unknown>(
  input: string,
  init?: RequestInit,
): Promise<T> {
  const resp = await apiFetch(input, init);
  if (!resp.ok) {
    const body = await resp.text().catch(() => "(no body)");
    throw new Error(`API error ${resp.status} on ${input}: ${body}`);
  }
  return resp.json();
}
