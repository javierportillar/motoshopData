import type { ReactNode } from "react";

interface EmptyStateProps {
  /** Icono decorativo (emoji, SVG, o componente) */
  icon?: ReactNode;
  /** Título principal */
  title: string;
  /** Descripción secundaria */
  description?: string;
  /** Acción opcional (botón/link) */
  action?: ReactNode;
  /** Tema oscuro */
  dark?: boolean;
  className?: string;
}

// ─── Gradiente atmosférico — luz de taller al amanecer ──────────

function AmbientGlow({ dark }: { dark: boolean }): JSX.Element {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {/* Luz cenital cálida */}
      <div
        className="absolute left-1/2 top-0 h-48 w-96 -translate-x-1/2 rounded-full blur-3xl"
        style={{
          background: dark
            ? "radial-gradient(ellipse at center, rgba(200,56,40,0.08) 0%, transparent 70%)"
            : "radial-gradient(ellipse at center, rgba(200,56,40,0.04) 0%, transparent 70%)",
        }}
      />
      {/* Reflejo inferior frío */}
      <div
        className="absolute bottom-0 left-1/2 h-32 w-64 -translate-x-1/2 rounded-full blur-3xl"
        style={{
          background: dark
            ? "radial-gradient(ellipse at center, rgba(14,165,233,0.05) 0%, transparent 70%)"
            : "radial-gradient(ellipse at center, rgba(14,165,233,0.03) 0%, transparent 70%)",
        }}
      />
    </div>
  );
}

// ─── Componente ─────────────────────────────────────────────────

/**
 * EmptyState — estado vacío con profundidad atmosférica.
 *
 * Gradiente radial dual (rojo cálido arriba, cyan frío abajo)
 * creando sensación de espacio — como un taller vacío al amanecer
 * antes de que lleguen las motos.
 *
 * El espacio vacío no es ausencia: es potencial.
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
  dark = false,
  className = "",
}: EmptyStateProps): JSX.Element {
  return (
    <div
      className={`relative flex flex-col items-center justify-center overflow-hidden rounded-xl border px-8 py-16 text-center ${
        dark
          ? "border-surface-dark-alt bg-surface-dark"
          : "border-border bg-surface"
      } ${className}`}
    >
      {/* Iluminación atmosférica */}
      <AmbientGlow dark={dark} />

      {/* Contenido */}
      <div className="relative z-10 flex flex-col items-center">
        {/* Icono */}
        {icon ? (
          <div
            className={`mb-5 flex h-16 w-16 items-center justify-center rounded-2xl text-2xl ${
              dark ? "bg-surface-dark-alt text-text-muted" : "bg-surface-alt text-text-muted"
            }`}
          >
            {icon}
          </div>
        ) : (
          /* Sin icono: círculo vacío — pura geometría */
          <div className="mb-5">
            <div
              className={`h-16 w-16 rounded-full border-2 border-dashed ${
                dark ? "border-surface-dark-alt" : "border-border"
              }`}
            />
          </div>
        )}

        {/* Título */}
        <h3
          className={`text-lg font-semibold ${
            dark ? "text-text-inverse" : "text-text-primary"
          }`}
        >
          {title}
        </h3>

        {/* Descripción */}
        {description && (
          <p
            className={`mt-2 max-w-sm text-sm leading-relaxed ${
              dark ? "text-text-muted" : "text-text-secondary"
            }`}
          >
            {description}
          </p>
        )}

        {/* Acción */}
        {action && <div className="mt-6">{action}</div>}
      </div>
    </div>
  );
}
