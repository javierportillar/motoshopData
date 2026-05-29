# V4 · Modo Offline — Evidencia

- **Fecha:** 2026-05-29
- **Verificación:** ¿La PWA funciona sin conexión después de cargada?
- **Resultado:** PENDIENTE de prueba con API real + PWA instalada

## Setup implementado

- `next-pwa` habilitado en `next.config.mjs` (Workbox)
- `lib/offline/cache.ts`: wrapper IndexedDB con TTL (idb-keyval)
- `lib/offline/strategies.ts`: NetworkOnly (stock) + StaleWhileRevalidate (catálogo)
- `public/manifest.json`: PWA manifest instalable
- `public/icons/`: iconos SVG 192px y 512px (placeholders)

## Estrategia de cache

| Tipo de dato | Estrategia | TTL |
|---|---|---|
| Catálogo (productos) | StaleWhileRevalidate | 1 h |
| Stock por SKU | NetworkOnly + fallback cache | 5 min |
| App shell (HTML, JS, CSS) | CacheFirst | build |

## Próximos pasos para evidencia

1. Abrir PWA en Chrome Android
2. Navegar a productos (llenar cache)
3. Activar modo avión
4. Navegar a productos previamente vistos → deben mostrarse
5. Intentar buscar algo nuevo → mostrar "Sin conexión"
6. Capturar screenshots
