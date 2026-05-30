import Image from "next/image";
import Link from "next/link";
import logoPng from "@/public/logo.png";

interface LogoProps {
  /** Tamaño: sm=32px, md=48px (default), lg=64px */
  size?: "sm" | "md" | "lg";
  /** Si true, linkea a "/" */
  link?: boolean;
  className?: string;
}

const sizeMap: Record<NonNullable<LogoProps["size"]>, number> = {
  sm: 32,
  md: 48,
  lg: 64,
};

/**
 * Logo de MotoShop — engranaje rojo + "MOTOSHOP" en blanco sobre fondo oscuro.
 * Usa surfaceDark (#171717) como wrapper para mantener legibilidad completa.
 *
 * Variante temporal F7: el logo está diseñado para fondo negro.
 * Si se usa sobre surface blanco, el texto blanco no se ve.
 * Solución: wrap automático en card oscura si no está en header/sidebar.
 */
export function Logo({
  size = "md",
  link = false,
  className = "",
}: LogoProps): JSX.Element {
  const px = sizeMap[size];

  const image = (
    <div
      className={`inline-flex items-center gap-2 rounded-lg bg-surface-dark px-3 py-2 ${className}`}
    >
      <Image
        src={logoPng}
        alt="MotoShop — Líderes en repuestos y mantenimiento de motos"
        width={px}
        height={(px * 470) / 1200} // Mantener relación 1200:470
        className="h-auto w-auto"
        priority={size === "lg"}
      />
    </div>
  );

  if (link) {
    return (
      <Link href="/" className="inline-block" aria-label="Ir a inicio MotoShop">
        {image}
      </Link>
    );
  }

  return image;
}

/**
 * Logo compacto — solo el engranaje rojo sin texto, para espacios reducidos
 * (mobile nav, favicon substitute, loading states).
 */
export function LogoMark({
  size = 24,
  className = "",
}: {
  size?: number;
  className?: string;
}): JSX.Element {
  return (
    <div
      className={`inline-flex items-center justify-center rounded-lg bg-surface-dark p-1.5 ${className}`}
    >
      <Image
        src={logoPng}
        alt="MotoShop"
        width={size}
        height={(size * 470) / 1200}
        className="h-auto w-auto"
      />
    </div>
  );
}
