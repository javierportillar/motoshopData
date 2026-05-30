# F7-A · Branding (Discovery)

- **Fecha:** 2026-05-30 (Sesión 50)
- **Status:** 🟡 PENDIENTE — humano sube logo + colores a este directorio

---

## Decisión humana

Existe branding corporativo MotoShop. **NO usamos paleta inventada**, usamos la existente.

## Pendiente del humano

Subir al repo en `docs/f7/branding/`:

1. **Logo MotoShop** en formato:
   - Preferible: `logo.svg` (vectorial, escalable)
   - Aceptable: `logo.png` con transparencia alta resolución (≥ 512px ancho)
   - Si hay variantes: `logo-light.svg`, `logo-dark.svg`, `logo-mark.svg` (solo isotipo)

2. **`docs/f7/branding/colors.md`** con paleta corporativa:
   ```markdown
   # Paleta MotoShop

   ## Primarios
   - Primary: #XXXXXX  (color principal)
   - Secondary: #XXXXXX (acento)

   ## Neutros
   - Background: #XXXXXX
   - Surface: #XXXXXX
   - Text Primary: #XXXXXX
   - Text Secondary: #XXXXXX

   ## Estados
   - Success: #XXXXXX (verde, alertas resueltas)
   - Warning: #XXXXXX (amarillo, datos stale)
   - Error: #XXXXXX (rojo, errores)
   - Info: #XXXXXX (azul, información)
   ```

3. **`docs/f7/branding/typography.md`** (opcional pero recomendado):
   ```markdown
   # Tipografía MotoShop

   - Heading font: <nombre> (URL si es de Google Fonts)
   - Body font: <nombre>
   - Mono font: <nombre o "system mono">
   ```

4. **Imágenes de referencia (opcional):**
   - Material existente (flyers, tarjetas, web actual)
   - Screenshots de inspiración (apps que te gustan visualmente)

## Cuando subas los assets

Dev T (en F7-B) los toma directamente de `docs/f7/branding/` para generar:
- `motoshop-app/web/lib/design/tokens.ts` con la paleta
- `motoshop-app/web/public/logo.svg` (servido por Next.js)
- `motoshop-app/web/tailwind.config.ts` actualizado con tokens
- Componente `<Logo>` con variantes

## Si NO subís los assets en 24h

F7-B arranca con paleta neutra placeholder:
- Primary: indigo-600 (`#4F46E5`)
- Neutros: gray-50 a gray-900
- Logo: marca "MotoShop" en texto con tipografía Inter

Y después vos podés reemplazar cuando subas el branding real.

## Mientras tanto · paleta placeholder propuesta

Para que Dev T pueda arrancar SI tardás en subir el branding:

```ts
// motoshop-app/web/lib/design/tokens.ts (placeholder)
export const colors = {
  primary: {
    50: '#EEF2FF',
    100: '#E0E7FF',
    500: '#6366F1',
    600: '#4F46E5',  // primary brand
    700: '#4338CA',
    900: '#312E81',
  },
  neutral: {
    50: '#FAFAFA',
    100: '#F5F5F5',
    200: '#E5E5E5',
    400: '#A3A3A3',
    600: '#525252',
    900: '#171717',
  },
  success: { 500: '#10B981', 600: '#059669' },
  warning: { 500: '#F59E0B', 600: '#D97706' },
  error: { 500: '#EF4444', 600: '#DC2626' },
  info: { 500: '#3B82F6', 600: '#2563EB' },
};
```

**Esto se REEMPLAZA con el branding real apenas vos lo subas.**
