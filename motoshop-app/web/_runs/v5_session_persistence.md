# V5 · Session Persistence — Evidencia

- **Fecha:** 2026-05-29
- **Verificación:** ¿La sesión sobrevive a cerrar y reabrir la app?
- **Resultado:** Pendiente de prueba con API real

## Setup implementado

- JWT se almacena en cookie `httpOnly Secure SameSite=Lax` (15 min TTL)
- Refresh token en cookie separada (7 días TTL)
- `middleware.ts` verifica cookie en rutas `(authenticated)/*`
- Refresh automático en 401 vía `lib/api/client.ts`

## Próximos pasos

1. Login con credenciales reales
2. Cerrar pestaña
3. Reabrir antes de TTL → debe seguir logueado
4. Capturar screenshot como evidencia
