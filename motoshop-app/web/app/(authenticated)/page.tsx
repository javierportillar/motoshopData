"use client";

import { Card } from "@/lib/ui/Card";

export default function DashboardPage(): JSX.Element {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-secondary-dark">Dashboard</h1>
        <p className="text-sm text-gray-500">Resumen de actividad</p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <div className="text-center">
            <p className="text-3xl font-bold text-primary">—</p>
            <p className="mt-1 text-sm text-gray-500">Ventas hoy</p>
          </div>
        </Card>
        <Card>
          <div className="text-center">
            <p className="text-3xl font-bold text-primary">—</p>
            <p className="mt-1 text-sm text-gray-500">Stock total</p>
          </div>
        </Card>
      </div>

      <Card>
        <h2 className="mb-3 font-semibold text-secondary-dark">
          Acceso rápido
        </h2>
        <div className="space-y-2">
          <a
            href="/products"
            className="flex items-center gap-3 rounded-lg border border-gray-100 p-3 text-sm transition-colors hover:bg-gray-50"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8" />
                <path d="M21 21l-4.35-4.35" />
              </svg>
            </span>
            <div>
              <p className="font-medium text-secondary-dark">
                Buscar productos
              </p>
              <p className="text-xs text-gray-500">
                Consulta catálogo y stock por bodega
              </p>
            </div>
          </a>
        </div>
      </Card>
    </div>
  );
}
