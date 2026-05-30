import type { ReactNode } from "react";

type ErrorSeverity = "critical" | "warning" | "info";

interface ErrorStateProps {
  /** Título del error */
  title?: string;
  /** Mensaje descriptivo */
  message?: string;
  /** Acción de recuperación (botón/link) */
  action?: ReactNode;
  /** Severidad visual: critical (rojo), warning (ámbar), info (azul) */
  severity?: ErrorSeverity;
  /** Tema oscuro (para dashboards con surface-dark) */
  dark?: boolean;
  className?: string;
}

// ─── Estética hazard-stripe industrial ──────────────────────────
// Franjas diagonales sutiles de advertencia como fondo

const severityColors: Record<ErrorSeverity, string> = {
  critical: "#B91C1C",
  warning: "#D97706",
  info: "#0284C7",
};

const severityIcons: Record<ErrorSeverity, string> = {
  critical: "⚠",
  warning: "⚡",
  info: "ℹ",
};

function HazardStripes({ color }: { color: string }): JSX.Element {
  return (
    <div
      className="pointer-events-none absolute inset-0 opacity-[0.04]"
      style={{
        backgroundImage: `repeating-linear-gradient(
          -45deg,
          ${color} 0px,
          ${color} 2px,
          transparent 2px,
          transparent 12px
        )`,
      }}
    />
  );
}

// ─── Componente ─────────────────────────────────────────────────

/**
 * ErrorState — estado de error con estética industrial.
 *
 * Franjas diagonales de advertencia (hazard stripes) como fondo,
 * recordando cintas de seguridad en taller mecánico.
 * El icono late con pulso sutil — como luz de tablero.
 */
export function ErrorState({
  title = "Error al cargar",
  message = "Ocurrió un problema al obtener los datos. Verificá la conexión e intentá de nuevo.",
  action,
  severity = "critical",
  dark = false,
  className = "",
}: ErrorStateProps): JSX.Element {
  const accentColor = severityColors[severity];
  const icon = severityIcons[severity];

  return (
    <div
      className={`relative flex flex-col items-center justify-center overflow-hidden rounded-xl border px-6 py-12 text-center ${
        dark
          ? "border-surface-dark-alt bg-surface-dark"
          : "border-border bg-surface"
      } ${className}`}
    >
      {/* Hazard stripes background */}
      <HazardStripes color={accentColor} />

      {/* Icono con pulso — como testigo del tablero */}
      <div className="relative mb-5">
        <div
          className="absolute inset-0 animate-ping rounded-full opacity-20"
          style={{
            backgroundColor: accentColor,
            width: 56,
            height: 56,
            left: -4,
            top: -4,
          }}
        />
        <div
          className="relative flex h-12 w-12 items-center justify-center rounded-full text-2xl"
          style={{
            backgroundColor: `${accentColor}18`,
            color: accentColor,
          }}
        >
          {icon}
        </div>
      </div>

      {/* Texto */}
      <h3
        className={`text-lg font-bold ${
          dark ? "text-text-inverse" : "text-text-primary"
        }`}
      >
        {title}
      </h3>
      <p
        className={`mt-2 max-w-md text-sm ${
          dark ? "text-text-muted" : "text-text-secondary"
        }`}
      >
        {message}
      </p>

      {/* Acción */}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
