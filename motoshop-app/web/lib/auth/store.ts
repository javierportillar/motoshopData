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
