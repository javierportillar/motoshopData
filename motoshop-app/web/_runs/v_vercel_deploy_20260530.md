# Vercel Deploy · F6-C · PWA producción

**Fecha:** 2026-05-30 17:37 UTC  
**Commit:** `03142df`  
**Build:** ✅ 0 errores

## URL producción

- **Alias:** `https://motoshop-web-tau.vercel.app`
- **Deploy URL:** `https://motoshop-8v7havoc0-javierportillars-projects.vercel.app`
- **Dominio custom (pendiente DNS):** `app.fragloesja.uk`

## DNS record para Cloudflare

Vercel solicita un **A record** (no CNAME):

```
Type:  A
Name:  app
Value: 76.76.21.21
```

Actualmente los nameservers apuntan a Cloudflare:
- `daisy.ns.cloudflare.com`
- `ed.ns.cloudflare.com`

El humano debe agregar este registro en Cloudflare DNS para activar `app.fragloesja.uk`.

## Env vars configuradas

| Variable | Value | Environments |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://api.fragloesja.uk` | Production, Development |

## Smoke test

| Endpoint | Status | Resultado |
|---|---|---|
| `/login` (page) | ✅ 200 | Página carga |
| `/api/health` | ✅ 200 | `{"status":"ok","version":"0.0.0","env":"dev"}` |
| `/api/demo` | ✅ 200 | HTML demo page |
| `/api/auth/login` (POST) | ✅ 200 | `{"user":"admin","message":"Login exitoso"}` |
| `/api/alerts/stockout` | ❌ 500 | Backend `api.fragloesja.uk` responde 500 |

### Nota: `/alerts/stockout` 500

El error NO es de Vercel ni de la PWA. El backend en `https://api.fragloesja.uk/alerts/stockout` también devuelve `Internal Server Error`. La PWA proxy funciona correctamente.

## Deploy history

1. `8c0d0a9` — rename env var + .env.example
2. `03142df` — fix route conflict (removed `/(authenticated)/page.tsx`, added redirect to `/dashboards`)
3. Production deploy: `motoshop-8v7havoc0` → alias `motoshop-web-tau`

## Commands run

```bash
npx vercel --yes
npx vercel env add NEXT_PUBLIC_API_URL production
npx vercel env add NEXT_PUBLIC_API_URL development
npx vercel --prod --yes
npx vercel domains add app.fragloesja.uk
```
