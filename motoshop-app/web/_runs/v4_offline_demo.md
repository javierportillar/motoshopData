# V4 · Modo Offline — Evidencia

- **Fecha:** 2026-05-29
- **Verificación:** ¿La PWA funciona sin conexión después de cargada?
- **Resultado:** ✅ Implementación completa — pendiente de validación en dispositivo móvil con navegador real

## Stack offline implementado

| Componente | Detalle |
|---|---|
| Service Worker | `next-pwa` genera `sw.js` + `workbox-*.js` en build productivo. Estrategia CacheFirst para app shell. |
| Cache API | `lib/offline/cache.ts` — IndexedDB vía `idb-keyval` con TTL configurable |
| Estrategia datos | StaleWhileRevalidate (catálogo 1h), NetworkOnly + fallback (stock 5 min) |
| App shell | HTML/JS/CSS cacheados por Workbox automáticamente |
| .gitignore | `sw.js` y `workbox-*.js` excluidos del repo — regenerados en cada build |

## Datos cacheados (verificados en `lib/api/hooks.ts` y `lib/offline/cache.ts`)

| Endpoint | TTL | Estrategia |
|---|---|---|
| `GET /api/products?q=...` | 1 h | NetworkFirst → IndexedDB fallback |
| `GET /api/products/{sku}/stock` | 5 min | NetworkFirst → IndexedDB fallback |

## Cómo validar offline real

1. Build productivo: `npm run build && npm start`
2. Abrir en Chrome Android
3. Navegar a productos y SKUs (llena cache)
4. Activar modo avión
5. Reabrir app → app shell visible
6. Navegar a productos ya vistos → datos desde IndexedDB
7. Buscar nuevo término → "Sin conexión y sin datos cacheados"

## Build verification

```bash
npm run build  # Genera sw.js + workbox
```

El Service Worker se registra automáticamente en producción. En desarrollo (`NODE_ENV=development`) next-pwa se desactiva.
