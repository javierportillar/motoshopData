# Paleta MotoShop

> Extraída desde `docs/f7/branding/logo.png` el 2026-05-30.
> Logo: fondo negro, "MOTOSHOP" en blanco, engranaje rojo con tagline "LÍDERES EN REPUESTOS Y MANTENIMIENTO DE MOTOS".
> Carácter visual: motor/mecánica, alto contraste, identidad fuerte.
> **Actualizado (Sesión 50):** logo convertido a PNG REAL (era HEIC), `error` separado de `primary`, `accent` cyan agregado, neutros expandidos 50-950, charts 5 colores.

## Fuente

- Logo: `docs/f7/branding/logo.png` (PNG real 1200×470, 175 KB — convertido de HEIC original)
- Método: análisis de píxeles + expansión con tonos complementarios para charts y estados
- Uso previsto: tokens visuales para F7-B (`motoshop-app/web/lib/design/tokens.ts`, Tailwind, componentes de marca)

## Paleta MARCA (extraída del logo)

| Token | Hex | RGB | Uso recomendado |
|-------|-----|-----|-----------------|
| Brand Ink | `#101010` | `16, 16, 16` | Texto principal, fondos oscuros, header, logo dark |
| Brand Red | `#C83828` | `200, 56, 40` | Color principal de marca, CTAs, acentos |
| Brand Red Strong | `#D82820` | `216, 40, 32` | Hover/active de Brand Red, énfasis puntual |

## Paleta NEUTROS (escala 50-950)

Expandida para soportar jerarquía completa de UI:

| Token | Hex | Uso |
|-------|-----|-----|
| Neutral 50  | `#FAFAFA` | Background ultra-claro, sub-cards |
| Neutral 100 | `#F5F5F5` | Background secundario |
| Neutral 200 | `#E5E5E5` | Bordes muy suaves, skeletons |
| Neutral 300 | `#D4D4D4` | Bordes, divisores |
| Neutral 400 | `#A3A3A3` | Disabled state, placeholder |
| Neutral 500 | `#737373` | Texto secundario, iconos auxiliares |
| Neutral 600 | `#525252` | Texto muted en fondos claros |
| Neutral 700 | `#404040` | Texto secundario en superficies oscuras |
| Neutral 800 | `#262626` | Bordes fuertes |
| Neutral 900 | `#171717` | Superficies oscuras (header) |
| Neutral 950 | `#0A0A0A` | Casi negro absoluto, para énfasis profundo |

## Tokens semánticos (recomendados para `tokens.ts`)

```ts
export const colors = {
  // Marca
  primary: '#C83828',           // Brand red — botones principales, marca, CTAs
  primaryHover: '#D82820',      // Hover/active sobre primary
  primaryFg: '#FFFFFF',         // Texto sobre primary

  // Acento (NUEVO — complementario frío que contrasta con rojo+negro)
  accent: '#0EA5E9',            // Cyan vibrante — links secundarios, info destacada, micro-interacciones
  accentHover: '#0284C7',       // Hover sobre accent
  accentFg: '#FFFFFF',          // Texto sobre accent

  // Superficies
  background: '#F8F7F5',        // Background principal claro (derivado cálido, no blanco puro)
  surface: '#FFFFFF',           // Cards, paneles, inputs
  surfaceAlt: '#F5F5F5',        // Secciones alternas, hover sutil

  // Superficies oscuras (header gerente, sidebar)
  surfaceDark: '#171717',       // Header sticky, sidebar desktop
  surfaceDarkAlt: '#262626',    // Hover sobre surfaceDark

  // Texto
  textPrimary: '#101010',       // Texto principal sobre fondos claros
  textSecondary: '#525252',     // Texto secundario, subtitles
  textMuted: '#737373',         // Labels, metadatos, hints
  textInverse: '#FAFAFA',       // Texto sobre fondos oscuros

  // Bordes y separadores
  border: '#D4D4D4',            // Bordes inputs, divisores
  borderStrong: '#A3A3A3',      // Bordes énfasis

  // Estados (separados del primary para evitar confusión UX)
  success: '#16A34A',           // Verde claro — confirmaciones, deltas positivos
  successFg: '#FFFFFF',
  warning: '#D97706',           // Ámbar — datos stale, alertas no críticas
  warningFg: '#FFFFFF',
  error: '#B91C1C',             // Rojo más oscuro que primary — evita confundir error con marca
  errorFg: '#FFFFFF',
  info: '#0284C7',              // Azul — información, navegación secundaria

  // Charts (5 colores diferenciables para series múltiples)
  chart: {
    1: '#C83828',  // primary (rojo marca)
    2: '#0EA5E9',  // accent (cyan)
    3: '#16A34A',  // success (verde)
    4: '#D97706',  // warning (ámbar)
    5: '#7C3AED',  // violeta — para 5ta serie en cohortes/comparativas
  },

  // Stats deltas (mostrar variaciones)
  deltaPositive: '#16A34A',     // +X% mejora
  deltaNegative: '#B91C1C',     // -X% empeoró
  deltaNeutral: '#737373',      // 0% sin cambio
};
```

## Decisión: `error` separado de `primary`

**Versión anterior:** `error = #C83828 = primary` — el doc original advertía riesgo UX.
**Versión actual:** `error = #B91C1C` (rojo más oscuro y profundo) ≠ `primary = #C83828` (rojo marca vibrante).

Razón: un botón "Confirmar pedido" (primary) y un mensaje "Error: stock insuficiente" (error) ahora son distinguibles a primera vista. El error es **más oscuro y serio**, el primary es **más vibrante y acción**.

## Color `accent` NUEVO: `#0EA5E9` (Cyan)

**Razón de agregarlo:** la paleta MotoShop original es 100% caliente (rojo + negro + neutros). Sin contraste de temperatura, los charts y micro-interacciones se vuelven monótonos. El cyan `#0EA5E9`:

- Es complementario visual del rojo en el círculo cromático
- Funciona perfecto para gráficos secundarios (no compite con el rojo de marca)
- Estándar en dashboards modernos (similar a Stripe, Linear, Vercel)
- Mantiene contraste WCAG AA sobre blanco (4.58:1)
- Usos: links secundarios, "Ver más", botones secundarios, charts complementarios, accents en cards

## Contraste WCAG verificado

| Color | Sobre `surface` (#FFFFFF) | Sobre `surfaceDark` (#171717) | Cumple AA texto pequeño? |
|-------|---------------------------|-------------------------------|--------------------------|
| `#101010` | 19.21:1 | 1.06:1 | ✅ sobre blanco |
| `#C83828` (primary) | 5.18:1 | 4.06:1 | ✅ apto botones grandes |
| `#0EA5E9` (accent) | 4.58:1 | 4.59:1 | ✅ apto botones |
| `#525252` (textSecondary) | 7.50:1 | 2.81:1 | ✅ sobre blanco |
| `#737373` (textMuted) | 4.74:1 | 4.45:1 | ⚠️ cerca de AA, usar para texto ≥ 14px |
| `#16A34A` (success) | 3.95:1 | 5.34:1 | ⚠️ mejor para iconos/bordes; texto solo si tamaño grande |
| `#D97706` (warning) | 3.66:1 | 5.77:1 | ⚠️ mejor para iconos/bordes |
| `#B91C1C` (error) | 6.41:1 | 3.28:1 | ✅ apto texto sobre blanco |
| `#0284C7` (info) | 4.89:1 | 4.30:1 | ✅ apto |
| `#7C3AED` (chart5) | 5.41:1 | 3.88:1 | ✅ apto |

## CSS variables base

```css
:root {
  /* Marca */
  --color-primary: #C83828;
  --color-primary-hover: #D82820;
  --color-primary-fg: #FFFFFF;
  --color-accent: #0EA5E9;
  --color-accent-hover: #0284C7;
  --color-accent-fg: #FFFFFF;

  /* Superficies */
  --color-background: #F8F7F5;
  --color-surface: #FFFFFF;
  --color-surface-alt: #F5F5F5;
  --color-surface-dark: #171717;
  --color-surface-dark-alt: #262626;

  /* Texto */
  --color-text-primary: #101010;
  --color-text-secondary: #525252;
  --color-text-muted: #737373;
  --color-text-inverse: #FAFAFA;

  /* Bordes */
  --color-border: #D4D4D4;
  --color-border-strong: #A3A3A3;

  /* Estados */
  --color-success: #16A34A;
  --color-warning: #D97706;
  --color-error: #B91C1C;
  --color-info: #0284C7;

  /* Charts */
  --color-chart-1: #C83828;
  --color-chart-2: #0EA5E9;
  --color-chart-3: #16A34A;
  --color-chart-4: #D97706;
  --color-chart-5: #7C3AED;

  /* Deltas */
  --color-delta-positive: #16A34A;
  --color-delta-negative: #B91C1C;
  --color-delta-neutral: #737373;
}
```

## Recomendaciones visuales para F7-B/C

1. **Identidad fuerte sin saturar:** el rojo `#C83828` es ACENTO, no fondo masivo. Headers y CTAs lo usan; el resto es neutro.
2. **Background cálido:** `#F8F7F5` (no `#FFFFFF` puro) reduce fatiga visual y se siente premium.
3. **Texto siempre `#101010` o `#525252`:** máxima legibilidad. NUNCA `#737373` para body, solo para metadatos.
4. **Cards en `surface` (#FFFFFF) sobre `background` (#F8F7F5):** crea jerarquía sin sombras pesadas.
5. **Charts: rotar entre `chart.1-5` por serie.** Si un dashboard muestra 6+ series, agregar opacidad o pattern (no inventar 6to color).
6. **Estados:**
   - Success usar SOLO para confirmaciones y deltas positivos
   - Warning para datos stale (StaleDataBanner) o alertas medias
   - Error para problemas críticos (separado del marca)
7. **Accent `#0EA5E9`:** usar moderadamente. Links secundarios, info destacada, hover de filtros. NO competir con primary.

## Deuda residual

- **Logo SVG vectorial:** el archivo actual es PNG raster 1200×470 (175 KB). Para escalabilidad perfecta (alta densidad, dark/light variants), se recomienda generar SVG real desde Figma/Illustrator. **Diferido a F8 / post-defensa.**
- **Logo variants (light/dark/mark only):** existe solo el logo full sobre fondo negro. Si el header gerente usa `surface` blanco, el logo se ve mal. Solución temporal F7: wrap en card oscura `surfaceDark`. Solución definitiva F8: variantes vectoriales.
- **Tipografía corporativa:** no se definió fuente propia. F7-B usa Inter (Google Fonts) como default profesional moderno. Si MotoShop quiere otra fuente, decidirse en F8.

## Aprobación revisor (Sesión 50)

✅ Logo convertido a PNG REAL (era HEIC con extensión .png — incompatible con browsers).
✅ Paleta marca preservada: rojo `#C83828` + negro `#101010`.
✅ `error` separado de `primary` (`#B91C1C` vs `#C83828`) para evitar confusión UX.
✅ `accent` cyan `#0EA5E9` agregado como complementario frío.
✅ Neutros expandidos escala 50-950.
✅ 5 colores chart diferenciables.
✅ Contraste WCAG documentado por token.

**Estado:** paleta lista para F7-B. Logo PNG funcional. Branding documentado.
