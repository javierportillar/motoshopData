// ============================================================
// MotoShop Design Tokens
// Fuente: docs/f7/branding/colors.md (2026-05-30)
// Uso: consumir desde componentes, tailwind @theme, y charts
// ============================================================

// ─── Tipos ───────────────────────────────────────────────────

export interface ColorTokens {
  // Marca
  primary: string;
  primaryHover: string;
  primaryFg: string;

  // Acento
  accent: string;
  accentHover: string;
  accentFg: string;

  // Superficies
  background: string;
  surface: string;
  surfaceAlt: string;

  // Superficies oscuras
  surfaceDark: string;
  surfaceDarkAlt: string;

  // Texto
  textPrimary: string;
  textSecondary: string;
  textMuted: string;
  textInverse: string;

  // Bordes
  border: string;
  borderStrong: string;

  // Estados
  success: string;
  successFg: string;
  warning: string;
  warningFg: string;
  error: string;
  errorFg: string;
  info: string;

  // Charts
  chart: {
    1: string;
    2: string;
    3: string;
    4: string;
    5: string;
  };

  // Deltas
  deltaPositive: string;
  deltaNegative: string;
  deltaNeutral: string;
}

export interface SpacingTokens {
  0: string;
  1: string;
  2: string;
  3: string;
  4: string;
  5: string;
  6: string;
  8: string;
  10: string;
  12: string;
  16: string;
  20: string;
  24: string;
  32: string;
  40: string;
  48: string;
  56: string;
  64: string;
}

export interface TypographyTokens {
  fontFamily: {
    sans: string;
    mono: string;
  };
  fontSize: {
    xs: [string, { lineHeight: string }];
    sm: [string, { lineHeight: string }];
    base: [string, { lineHeight: string }];
    lg: [string, { lineHeight: string }];
    xl: [string, { lineHeight: string }];
    "2xl": [string, { lineHeight: string }];
    "3xl": [string, { lineHeight: string }];
    "4xl": [string, { lineHeight: string }];
  };
  fontWeight: {
    normal: string;
    medium: string;
    semibold: string;
    bold: string;
  };
}

export interface RadiusTokens {
  sm: string;
  md: string;
  lg: string;
  full: string;
}

export interface ShadowTokens {
  sm: string;
  md: string;
  lg: string;
}

export interface BreakpointTokens {
  sm: number;
  md: number;
  lg: number;
  xl: number;
}

export interface DesignTokens {
  colors: ColorTokens;
  spacing: SpacingTokens;
  typography: TypographyTokens;
  radius: RadiusTokens;
  shadow: ShadowTokens;
  breakpoints: BreakpointTokens;
}

// ─── Colores semánticos (copy-paste de colors.md) ──────────

export const colors: ColorTokens = {
  // Marca
  primary: "#C83828", // Brand red — botones principales, marca, CTAs
  primaryHover: "#D82820", // Hover/active sobre primary
  primaryFg: "#FFFFFF", // Texto sobre primary

  // Acento (complementario frío que contrasta con rojo+negro)
  accent: "#0EA5E9", // Cyan vibrante — links secundarios, info destacada
  accentHover: "#0284C7", // Hover sobre accent
  accentFg: "#FFFFFF", // Texto sobre accent

  // Superficies
  background: "#F8F7F5", // Background principal claro (derivado cálido)
  surface: "#FFFFFF", // Cards, paneles, inputs
  surfaceAlt: "#F5F5F5", // Secciones alternas, hover sutil

  // Superficies oscuras (header gerente, sidebar)
  surfaceDark: "#171717", // Header sticky, sidebar desktop
  surfaceDarkAlt: "#262626", // Hover sobre surfaceDark

  // Texto
  textPrimary: "#101010", // Texto principal sobre fondos claros
  textSecondary: "#525252", // Texto secundario, subtitles
  textMuted: "#737373", // Labels, metadatos, hints
  textInverse: "#FAFAFA", // Texto sobre fondos oscuros

  // Bordes y separadores
  border: "#D4D4D4", // Bordes inputs, divisores
  borderStrong: "#A3A3A3", // Bordes énfasis

  // Estados (separados del primary para evitar confusión UX)
  success: "#16A34A", // Verde — confirmaciones, deltas positivos
  successFg: "#FFFFFF",
  warning: "#D97706", // Ámbar — datos stale, alertas no críticas
  warningFg: "#FFFFFF",
  error: "#B91C1C", // Rojo más oscuro que primary — evita confundir error con marca
  errorFg: "#FFFFFF",
  info: "#0284C7", // Azul — información, navegación secundaria

  // Charts (5 colores diferenciables para series múltiples)
  chart: {
    1: "#C83828", // primary (rojo marca)
    2: "#0EA5E9", // accent (cyan)
    3: "#16A34A", // success (verde)
    4: "#D97706", // warning (ámbar)
    5: "#7C3AED", // violeta — para 5ta serie
  },

  // Stats deltas (mostrar variaciones)
  deltaPositive: "#16A34A", // +X% mejora
  deltaNegative: "#B91C1C", // -X% empeoró
  deltaNeutral: "#737373", // 0% sin cambio
};

// ─── Espaciado (escala 4px) ─────────────────────────────────

export const spacing: SpacingTokens = {
  0: "0px",
  1: "4px",
  2: "8px",
  3: "12px",
  4: "16px",
  5: "20px",
  6: "24px",
  8: "32px",
  10: "40px",
  12: "48px",
  16: "64px",
  20: "80px",
  24: "96px",
  32: "128px",
  40: "160px",
  48: "192px",
  56: "224px",
  64: "256px",
};

// ─── Tipografía ─────────────────────────────────────────────

export const typography: TypographyTokens = {
  fontFamily: {
    sans: [
      "Inter",
      "ui-sans-serif",
      "system-ui",
      "-apple-system",
      "sans-serif",
    ].join(", "),
    mono: [
      "JetBrains Mono",
      "ui-monospace",
      "SFMono-Regular",
      "monospace",
    ].join(", "),
  },
  fontSize: {
    xs: ["0.75rem", { lineHeight: "1rem" }],
    sm: ["0.875rem", { lineHeight: "1.25rem" }],
    base: ["1rem", { lineHeight: "1.5rem" }],
    lg: ["1.125rem", { lineHeight: "1.75rem" }],
    xl: ["1.25rem", { lineHeight: "1.75rem" }],
    "2xl": ["1.5rem", { lineHeight: "2rem" }],
    "3xl": ["1.875rem", { lineHeight: "2.25rem" }],
    "4xl": ["2.25rem", { lineHeight: "2.5rem" }],
  },
  fontWeight: {
    normal: "400",
    medium: "500",
    semibold: "600",
    bold: "700",
  },
};

// ─── Bordes redondeados ──────────────────────────────────────

export const radius: RadiusTokens = {
  sm: "0.375rem",
  md: "0.5rem",
  lg: "0.75rem",
  full: "9999px",
};

// ─── Sombras ─────────────────────────────────────────────────

export const shadow: ShadowTokens = {
  sm: "0 1px 2px 0 rgb(0 0 0 / 0.05)",
  md: "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
  lg: "0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)",
};

// ─── Breakpoints (Tailwind defaults) ────────────────────────

export const breakpoints: BreakpointTokens = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
};

// ─── Token completo ─────────────────────────────────────────

export const tokens: DesignTokens = {
  colors,
  spacing,
  typography,
  radius,
  shadow,
  breakpoints,
};
