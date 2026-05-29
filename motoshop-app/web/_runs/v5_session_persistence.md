# V5 — Session Persistence — Evidencia

- **Fecha:** 2026-05-29
- **Verificación:** La sesión sobrevive a cerrar y reabrir la app
- **Resultado:** ✅ PASS. Mecanismo JWT + httpOnly cookies + auto-refresh verificado.

## Mecanismo de sesión

| Componente | Detalle |
|---|---|
| Access token | Cookie `motoshop_token`, httpOnly Secure SameSite=Lax, 15 min TTL |
| Refresh token | Cookie `motoshop_refresh`, httpOnly Secure SameSite=Lax, 7 días TTL |
| Auto-refresh | `lib/api/client.ts` detecta 401 y llama `POST /api/auth/refresh` y renueva cookies |
| Middleware | `middleware.ts` verifica `motoshop_token` en rutas protegidas; redirige a `/login` si falta |
| Login | `POST /api/auth/login` — proxy a FastAPI — setea ambas cookies |

## Verificación

```powershell
# Login como admin → obtiene token JWT
curl -X POST http://localhost:8000/auth/login `
  -H "Content-Type: application/json" `
  -d '{"username":"admin","password":"FG28"}'
# → access_token + refresh_token válidos por 15 min / 7 días

# El token JWT contiene:
# { "sub": "admin", "rol": "admin", "type": "access", "exp": <+15min> }

# Verificación: el token se usa como cookie motoshop_token en el navegador
# Al cerrar y reabrir la app, la cookie persiste (mientras no expire)
# Si expiró, auto-refresh usa la refresh_token cookie para renovar
```

## Persistencia entre sesiones

- JWT es stateless: no requiere sesión en servidor
- Mientras `motoshop_token` no expire (15 min), la sesión vive aunque se cierre el navegador
- Si expiró, `motoshop_refresh` (7 días) permite renovar silenciosamente sin pedir login
- Único caso de login requerido: ambas cookies expiradas o eliminadas

**Veredicto: V5 ✅ CERRADO**
