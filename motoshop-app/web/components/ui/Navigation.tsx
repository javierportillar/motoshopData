"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { LogoMark } from "@/components/Logo";

// ─── Tipos ──────────────────────────────────────────────────────

interface NavItem {
  label: string;
  href: string;
  icon: ReactNode;
}

interface NavigationProps {
  /** Items de navegación */
  items: NavItem[];
  /** Rol del usuario (vendedor | admin | gerente) */
  role?: "vendedor" | "admin" | "gerente";
  /** Acción de logout */
  onLogout?: () => void;
  className?: string;
}

// ─── Iconos inline SVG — sin dependencia de librería ────────────

const Icons = {
  home: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
      <path d="M3 9.5L12 3l9 6.5V20a1 1 0 01-1 1H4a1 1 0 01-1-1V9.5z" />
      <path d="M9 21V12h6v9" />
    </svg>
  ),
  ventas: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
      <path d="M3 20h18M3 14l4-4 3 3 5-5 3 3" />
    </svg>
  ),
  inventario: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  ),
  abc: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
      <path d="M12 20V10M18 20V4M6 20v-6" />
    </svg>
  ),
  dormidos: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 3" />
    </svg>
  ),
  forecast: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
      <path d="M3 3v18h18" />
      <path d="M7 16l4-5 3 2 4-6" />
    </svg>
  ),
  alerts: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
      <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 01-3.46 0" />
    </svg>
  ),
  acciones: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
      <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" />
      <rect x="9" y="3" width="6" height="4" rx="1" />
      <path d="M9 14l2 2 4-4" />
    </svg>
  ),
  planCompras: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
      <path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z" />
      <path d="M3 6h18" />
      <path d="M16 10a4 4 0 01-8 0" />
    </svg>
  ),
  logout: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
      <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
      <path d="M16 17l5-5-5-5" />
      <path d="M21 12H9" />
    </svg>
  ),
};

const iconMap: Record<string, ReactNode> = {
  home: Icons.home,
  ventas: Icons.ventas,
  inventario: Icons.inventario,
  abc: Icons.abc,
  dormidos: Icons.dormidos,
  forecast: Icons.forecast,
  alerts: Icons.alerts,
  acciones: Icons.acciones,
  "plan-compras": Icons.planCompras,
};

// ─── Sidebar Desktop (≥ lg) ─────────────────────────────────────

function Sidebar({
  items,
  role,
  onLogout,
  isActive,
}: {
  items: NavItem[];
  role?: string;
  onLogout?: () => void;
  isActive: (href: string) => boolean;
}): JSX.Element {
  return (
    <aside className="hidden lg:flex lg:fixed lg:inset-y-0 lg:left-0 lg:z-40 lg:w-60 lg:flex-col">
      {/* Fondo oscuro texturizado — acero de taller */}
      <div className="flex grow flex-col gap-y-5 overflow-y-auto bg-surface-dark px-4 py-6">
        {/* Marca */}
        <div className="mb-2 flex items-center gap-3 px-2">
          <LogoMark size={28} />
          <div>
            <p className="text-sm font-bold text-text-inverse tracking-tight">
              MOTOSHOP
            </p>
            <p className="text-[0.625rem] text-text-muted uppercase tracking-widest">
              {role === "vendedor" ? "Vendedor" : "Gerencia"}
            </p>
          </div>
        </div>

        {/* Separador — línea de soldadura */}
        <div className="h-px bg-gradient-to-r from-surface-dark-alt via-border-strong/30 to-surface-dark-alt" />

        {/* Navegación */}
        <nav className="flex flex-1 flex-col gap-1">
          {items.map((item) => {
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200 ${
                  active
                    ? "bg-primary text-primary-fg shadow-sm"
                    : "text-text-muted hover:bg-surface-dark-alt hover:text-text-inverse"
                }`}
              >
                {/* Ícono */}
                <span
                  className={`transition-transform duration-200 ${
                    active
                      ? ""
                      : "group-hover:translate-x-0.5"
                  }`}
                >
                  {item.icon}
                </span>

                {/* Label */}
                <span className="flex-1">{item.label}</span>

                {/* Indicador activo — barra lateral */}
                {active && (
                  <span className="ml-auto h-1.5 w-1.5 rounded-full bg-white/60" />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Footer — logout */}
        {onLogout && (
          <>
            <div className="h-px bg-surface-dark-alt" />
            <button
              onClick={onLogout}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-text-muted transition-colors hover:bg-error/10 hover:text-error"
            >
              {Icons.logout}
              <span>Salir</span>
            </button>
          </>
        )}
      </div>
    </aside>
  );
}

// ─── Bottom Nav Mobile (< lg) ───────────────────────────────────

function BottomNav({
  items,
  isActive,
}: {
  items: NavItem[];
  isActive: (href: string) => boolean;
}): JSX.Element {
  // Mostrar máximo 5 items en bottom nav (los más importantes)
  const visibleItems = items.slice(0, 5);

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 border-t border-surface-dark-alt bg-surface-dark lg:hidden">
      {/* Safe area para iOS */}
      <div className="pb-[env(safe-area-inset-bottom,0px)]">
        <div className="flex items-center justify-around px-1 pt-1.5 pb-1">
          {visibleItems.map((item) => {
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-lg py-1.5 transition-colors ${
                  active
                    ? "text-primary"
                    : "text-text-muted hover:text-text-inverse"
                }`}
              >
                {/* Icono */}
                <span className="transition-transform duration-150 active:scale-90">
                  {item.icon}
                </span>

                {/* Label — compacto */}
                <span className="text-[0.625rem] font-medium leading-tight truncate max-w-[64px]">
                  {item.label}
                </span>

                {/* Indicador activo — línea superior */}
                {active && (
                  <span className="absolute top-0 left-1/2 h-0.5 w-6 -translate-x-1/2 rounded-full bg-primary" />
                )}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}

// ─── Navigation ─────────────────────────────────────────────────

/**
 * Navigation — sistema de navegación adaptable MotoShop.
 *
 * Mobile (< lg): bottom nav con máximo 5 items + indicador active.
 * Desktop (≥ lg): sidebar fijo izquierdo con items completos + logo + logout.
 *
 * Diseño industrial: fondo surface-dark #171717, acero texturizado,
 * active state en rojo primary, hover con desplazamiento sutil.
 */
export function Navigation({
  items,
  role = "gerente",
  onLogout,
  className = "",
}: NavigationProps): JSX.Element {
  const pathname = usePathname();

  const isActive = (href: string): boolean => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  // Enriquecer items con iconos del mapa
  const enrichedItems: NavItem[] = items.map((item) => ({
    ...item,
    icon: item.icon ?? iconMap[item.href.replace(/^\/|\/$/g, "")] ?? Icons.home,
  }));

  return (
    <div className={className}>
      {/* Sidebar desktop */}
      <Sidebar
        items={enrichedItems}
        role={role}
        onLogout={onLogout}
        isActive={isActive}
      />

      {/* Bottom nav mobile */}
      <BottomNav items={enrichedItems} isActive={isActive} />
    </div>
  );
}

// ─── Helpers para construir items ────────────────────────────────

export function gerenteNavItems(): NavItem[] {
  return [
    { label: "Inicio", href: "/", icon: Icons.home },
    { label: "Ventas", href: "/dashboards/ventas", icon: Icons.ventas },
    { label: "Inventario", href: "/dashboards/inventario", icon: Icons.inventario },
    { label: "ABC", href: "/dashboards/abc", icon: Icons.abc },
    { label: "Dormidos", href: "/dashboards/dormidos", icon: Icons.dormidos },
    { label: "Forecast", href: "/forecast", icon: Icons.forecast },
    { label: "Alertas", href: "/alerts", icon: Icons.alerts },
    { label: "Acciones", href: "/acciones", icon: Icons.acciones },
    { label: "Cohortes", href: "/cohortes", icon: Icons.home },
    { label: "Vendedores", href: "/vendedores", icon: Icons.home },
    { label: "Drift", href: "/drift", icon: Icons.alerts },
    { label: "Plan Compras", href: "/plan-compras", icon: Icons.planCompras },
  ];
}

export function vendedorNavItems(): NavItem[] {
  return [
    { label: "Inicio", href: "/", icon: Icons.home },
    { label: "Alertas", href: "/alerts", icon: Icons.alerts },
    { label: "Acciones", href: "/acciones", icon: Icons.acciones },
  ];
}
