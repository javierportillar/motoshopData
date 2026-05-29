"use client";

import { useAuthStore } from "@/lib/auth/store";
import { useRouter } from "next/navigation";
import { useToast } from "./Toast";

export function Header(): JSX.Element {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const router = useRouter();
  const { addToast } = useToast();

  const handleLogout = async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch {
      // ignore
    }
    logout();
    addToast("Sesión cerrada", "info");
    router.push("/login");
  };

  return (
    <header className="sticky top-0 z-30 border-b border-gray-200 bg-white/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-lg items-center justify-between px-4">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-bold text-white">
            M
          </div>
          <span className="text-lg font-semibold text-secondary-dark">
            MotoShop
          </span>
        </div>
        <div className="flex items-center gap-3">
          {user && (
            <span className="hidden text-sm text-gray-500 sm:inline">
              {user}
            </span>
          )}
          <button
            onClick={handleLogout}
            className="rounded-lg p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
            title="Cerrar sesión"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
              <polyline points="16,17 21,12 16,7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
          </button>
        </div>
      </div>
    </header>
  );
}
