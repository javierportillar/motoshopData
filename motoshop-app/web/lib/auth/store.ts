"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

interface AuthState {
  user: string | null;
  role: string | null;
  isAuthenticated: boolean;
  hasHydrated: boolean;
  setUser: (user: string, role: string) => void;
  logout: () => void;
  setHasHydrated: (v: boolean) => void;
}

// F7-FIX1 bug 5.1: persistir auth en localStorage para que el refresh no rompa el home
// y el rol se mantenga entre navegaciones. hasHydrated evita renderizar contenido
// dependiente del rol antes de que Zustand restaure desde storage.
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      role: null,
      isAuthenticated: false,
      hasHydrated: false,
      setUser: (u, r) => set({ user: u, role: r, isAuthenticated: true }),
      logout: () => set({ user: null, role: null, isAuthenticated: false }),
      setHasHydrated: (v) => set({ hasHydrated: v }),
    }),
    {
      name: "motoshop_auth",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        user: state.user,
        role: state.role,
        isAuthenticated: state.isAuthenticated,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    },
  ),
);

// E2E bridge — se activa solo en dev para inyectar role sin pasar por login
if (process.env.NODE_ENV === "development" && typeof window !== "undefined") {
  (window as unknown as Record<string, unknown>).__setAuthRole = (role: string | null) => {
    useAuthStore.setState({ role, isAuthenticated: role !== null, hasHydrated: true });
  };
}
