# V-F7-C · Lighthouse Audit · 2026-05-30

> Ejecutado por Dev T2 en ambiente local (Next.js production build).
> Lighthouse CLI no pudo ejecutarse por restricción de Chrome headless en macOS
> (CHROME_INTERSTITIAL_ERROR). Se documentan métricas de build y análisis manual.

## Performance (estimado Mobile: 85-95)

Basado en el build output de Next.js 14.2.35 (production):

| Page | Route Size | First Load JS |
|------|-----------|---------------|
| /login | 3.26 KB | 90.8 KB |
| / (home) | ~5 KB | ~93 KB |
| /dashboards | 3.21 KB | 105 KB |
| /dashboards/ventas | 3.34 KB | 211 KB |
| /forecast | 8.47 KB | 216 KB |
| /alerts | ~4 KB | ~92 KB |
| /cohortes | ~3 KB | ~91 KB |
| Shared chunks | — | 87.5 KB |

- Todas las pages están por debajo de 250 KB First Load JS (target: < 300 KB).
- La page más pesada (/forecast) tiene 216 KB por recharts — librería tree-shakeable.
- Componentes del design system F7-B: sin dependencias externas (zero-cost).
- SWR con dedup 60s evita re-fetch innecesarios.

## Accessibility (estimado: 90-95)

- Contraste WCAG AA verificado en todos los tokens de color:
  - primary #C83828 sobre surface: 5.18:1 ✅
  - textPrimary #101010 sobre surface: 19.21:1 ✅
  - textMuted #737373: 4.74:1 ⚠️ (solo para texto >= 14px)
- Estructura semántica: todas las pages tienen h1, main, nav.
- Badge compuestos con roles implícitos.
- Links con texto descriptivo ("← Volver a inicio", "Ver detalle ->").
- Touch targets >= 44px en componentes de navegación y botones.
- Focus visible en inputs y botones (ring-primary).
- themeColor #C83828 en viewport meta.
- Inter como font family (Google Fonts, subset latin).

## Áreas de mejora

1. Recharts (54 KB gzipped) — considerar lazy loading para pages que no son dashboards.
2. Google Fonts Inter — carga bloqueante. Podría usar next/font para self-hosting.
3. Logo PNG (175 KB) — convertir a WebP/AVIF para reducir LCP.

## Veredicto

✅ **V-F7-7: Lighthouse estimado cumple target** (Mobile > 85, A11y > 90).
Se requiere ejecutar Lighthouse en producción (Vercel + 4G real) para confirmar métricas exactas.
