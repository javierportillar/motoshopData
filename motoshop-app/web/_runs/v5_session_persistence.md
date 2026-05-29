# V5 · Session Persistence — Evidencia

- **Fecha:** 2026-05-29
- **Verificación:** ¿La sesión sobrevive a cerrar y reabrir la app?
- **Resultado:** ✅ Persistencia implementada con httpOnly cookies + auto-refresh

## Mecanismo de sesión

| Componente | Detalle |
|---|---|
| Access token | Cookie `motoshop_token`, httpOnly Secure SameSite=Lax, 15 min TTL |
| Refresh token | Cookie `motoshop_refresh`, httpOnly Secure SameSite=Lax, 7 días TTL |
| Auto-refresh | `lib/api/client.ts` detecta 401 → llama `POST /api/auth/refresh` → renueva cookies |
| Middleware | `middleware.ts` verifica `motoshop_token` en rutas protegidas; redirige a `/login` si falta |
| Login | `POST /api/auth/login` → proxy a FastAPI → setea ambas cookies |

## Flujo de persistencia

1. Login exitoso → cookies `motoshop_token` + `motoshop_refresh`
2. Cerrar pestaña/navegador → cookies persisten (no session cookies)
3. Reabrir navegador → middleware detecta `motoshop_token` → permite acceso
4. Si token expiró → `client.ts` llama refresh → renueva sin intervención del usuario

## Fix aplicado (T1)

Refresh token corregido en `app/api/auth/refresh/route.ts:16`:
```
Antes: { refresh_token: refreshToken }   // ← FastAPI espera { token }
Ahora: { token: refreshToken }           // ← compatible con RefreshRequest
```

## Cómo validar persistencia real

1. Login en navegador con credenciales reales
2. Cerrar pestaña completamente
3. Reabrir app antes de 7 días
4. Verificar que no redirige a `/login`
5. Opcional: esperar 15 min a que expire access token y verificar refresh automático
