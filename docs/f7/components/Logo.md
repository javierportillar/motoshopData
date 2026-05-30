# Logo · Componente de marca

- **File:** `motoshop-app/web/components/Logo.tsx`
- **Asset:** `motoshop-app/web/public/logo.png` (1200×470, 175 KB PNG, fondo negro)
- **Fase:** F7-B (Design System)

## Estados / Variantes

### 1. Logo default (md, no link)

```tsx
<Logo />
```

Renderiza el logo PNG dentro de un card oscuro (`bg-surface-dark`, `#171717`) para mantener legibilidad del texto blanco sobre cualquier fondo.

### 2. Logo pequeño (sm, con link a home)

```tsx
<Logo size="sm" link />
```

32px de ancho, link a `/`. Ideal para header sticky en mobile.

### 3. Logo grande (lg, hero / splash)

```tsx
<Logo size="lg" className="mx-auto" />
```

64px de ancho, `priority` loading para LCP. Usar en landing/splash.

### 4. LogoMark (solo engranaje, sin texto)

```tsx
<LogoMark size={24} />
```

Solo el isotipo rojo, para espacios reducidos: favicon alternativo, loading states, mobile nav minimal.

## Deuda conocida

- **Logo SVG vectorial:** el archivo actual es PNG raster. Para escalabilidad perfecta (alta densidad, dark/light variants), se recomienda generar SVG real desde Figma/Illustrator. **Diferido a F8 / post-defensa.**
- **Logo variants (light/dark/mark only):** existe solo el logo full sobre fondo negro. Si el header gerente usa `surface` blanco, el logo se ve mal. Solución temporal F7: wrapper `bg-surface-dark`. Solución definitiva F8: variantes vectoriales.
- **Tipografía corporativa:** no se definió fuente propia. F7-B usa Inter (Google Fonts) como default profesional moderno.

## WCAG

- Contraste texto blanco sobre `#171717`: 13.62:1 ✅ AAA
- Alt text descriptivo incluido en `<Image alt="...">`
