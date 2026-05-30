"use client";

import { create } from "zustand";

interface AuthState {
  user: string | null;
  role: string | null;
  isAuthenticated: boolean;
  setUser: (user: string, role: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  role: null,
  isAuthenticated: false,
  setUser: (u, r) => set({ user: u, role: r, isAuthenticated: true }),
  logout: () => set({ user: null, role: null, isAuthenticated: false }),
}));

// E2E bridge — se activa solo en dev para inyectar role sin pasar por login
if (process.env.NODE_ENV === "development" && typeof window !== "undefined") {
  (window as unknown as Record<string, unknown>).__setAuthRole = (role: string | null) => {
    useAuthStore.setState({ role, isAuthenticated: role !== null });
  };
}
