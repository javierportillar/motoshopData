# V7 — Role Permissions — Evidencia

- **Fecha:** 2026-05-29
- **Verificación:** Los permisos de rol funcionan correctamente
- **Resultado:** ✅ PASS. Admin=200, Vendedor=403, No auth=401.

## Endpoint

`GET /api/admin/ping` — implementado en `app/api/admin/ping/route.ts`.
Decodifica el payload del JWT desde la cookie `motoshop_token` y extrae el rol.
No consulta BD — validación exclusivamente desde el token.

## Resultados

### Admin → 200 ✅

```powershell
curl -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"FG28"}'
curl http://localhost:3000/api/admin/ping -b "motoshop_token=<token>"
```

```json
HTTP 200
{"message":"Admin ping ok","user":"admin","role":"admin"}
```

### Vendedor → 403 ✅

```powershell
curl -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d '{"username":"vendedor1","password":"FG28"}'
curl http://localhost:3000/api/admin/ping -b "motoshop_token=<token>"
```

```json
HTTP 403
{"detail":"Se requiere rol admin","user":"vendedor1","role":"vendedor"}
```

### Sin autenticación → 401 ✅

```powershell
curl http://localhost:3000/api/admin/ping
```

```json
HTTP 401
{"detail":"No autenticado"}
```

## Lógica del endpoint

```typescript
const payload = JSON.parse(Buffer.from(token.split(".")[1], "base64"));
const role = payload.rol ?? payload.role ?? "";
if (role !== "admin") return 403;
return 200;
```

**Veredicto: V7 ✅ CERRADO**
