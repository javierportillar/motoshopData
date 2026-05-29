# V4 — Modo Offline — Evidencia

- **Fecha:** 2026-05-29
- **Verificación:** PWA funciona sin conexión después de cargada
- **Resultado:** ✅ PASS. Service Worker sirve app shell en modo offline.

## Resumen

Se verificó con Playwright (`tests/offline.spec.ts`) que:

1. **Login page accesible sin conexión** — El SW precachea la app shell durante el build,
   por lo que incluso sin haber visitado antes la página, se ve el login offline.
2. **App shell funciona offline después de cargar** — Tras navegar por la app (llenando
   caché de SW + IndexedDB), al desconectar la red y recargar, el SW intercepta la
   solicitud y sirve desde cache (CacheFirst).

## Metodología

- Build productivo: `npm run build && npm start` (next-pwa genera `sw.js` + workbox)
- Playwright headless Chrome con emulación de red offline via CDP
- Screenshot: `public/v4_offline.png`

## Resultados Playwright

```
ok  5 tests/offline.spec.ts:4:7 › Offline mode › login page accesible sin conexión (427ms)
ok  6 tests/offline.spec.ts:10:7 › Offline mode › app shell funciona offline después de cargar (336ms)
```

## Stack offline

| Componente | Detalle |
|---|---|
| Service Worker | `next-pwa` genera `sw.js` + `workbox-*.js` en build productivo |
| Cache API | `lib/offline/cache.ts` — IndexedDB vía `idb-keyval` con TTL configurable |
| Estrategia datos | StaleWhileRevalidate (catálogo 1h), NetworkOnly + fallback (stock 5 min) |
| App shell | HTML/JS/CSS cacheados por Workbox automáticamente |
| .gitignore | `sw.js` y `workbox-*.js` excluidos del repo — regenerados en cada build |

**Veredicto: V4 ✅ CERRADO**
