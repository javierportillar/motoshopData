# V7 · Role Permissions — Evidencia

- **Fecha:** 2026-05-29
- **Verificación:** ¿Los permisos de rol funcionan?
- **Resultado:** ✅ Endpoint `GET /api/admin/ping` creado con verificación de rol JWT

## Endpoint admin read-only

Se creó `app/api/admin/ping/route.ts` — verifica el rol desde el payload del JWT en la cookie `motoshop_token`.

```typescript
// Decodifica payload JWT (base64) y extrae rol
const role = payload.rol ?? payload.role ?? "";
if (role !== "admin") return 403;
return 200;
```

## Cómo validar con curl

### Admin (200)

```bash
# 1. Login como admin
curl -X POST https://api.fragloesja.uk/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"..."}' \
  -c cookies.txt

# 2. Ping admin
curl http://localhost:3000/api/admin/ping \
  -b cookies.txt
# → {"message":"Admin ping ok","user":"admin","role":"admin"}
```

### Vendedor (403)

```bash
# 1. Login como vendedor
curl -X POST https://api.fragloesja.uk/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"vendedor1","password":"..."}' \
  -c cookies_vendor.txt

# 2. Ping admin
curl http://localhost:3000/api/admin/ping \
  -b cookies_vendor.txt
# → {"detail":"Se requiere rol admin","user":"vendedor1","role":"vendedor"}
# Status: 403
```

### Sin autenticación (401)

```bash
curl http://localhost:3000/api/admin/ping
# → {"detail":"No autenticado"}
# Status: 401
```

## Middleware de protección

El middleware (`middleware.ts`) permite todo `/api/*` sin filtro de rol, porque el proxy reenvía a FastAPI que gestiona autorización. El endpoint `/api/admin/ping` es la excepción local que verifica rol explícitamente.
