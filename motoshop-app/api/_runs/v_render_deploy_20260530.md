# Render Deploy · F6-D · API cloud 24/7

**Fecha:** 2026-05-30  
**Commit:** `44dda32`  
**Plataforma:** Render free (Python buildpack)  
**UptimeRobot:** Configurado por humano

## URL producción

- **URL Render:** `https://motoshop-cloud-api.onrender.com`
- **Domino custom (pendiente CNAME):** `cloud-api.fragloesja.uk`
  - Humano: agregar CNAME `cloud-api` → `motoshop-cloud-api.onrender.com` en Cloudflare DNS (proxy OFF)
  - Luego: Render dashboard → Settings → Custom Domain → Add `cloud-api.fragloesja.uk`

## Dockerfile

El Dockerfile existe en `motoshop-app/api/Dockerfile` para referencias futuras, pero Render usa Python buildpack (más simple, sin Docker). Si en F7 se migra a Docker, ya está listo.

## Secrets configurados

| Variable | sync: false? | Nota |
|---|---|---|
| `DATABRICKS_HOST` | ✅ sync:false | Humano setea en dashboard |
| `DATABRICKS_TOKEN` | ✅ sync:false | Idem |
| `DATABRICKS_HTTP_PATH` | No | Fijo en render.yaml |
| `JWT_SECRET` | ✅ sync:false | Mismo que Windows |
| `CORS_ORIGINS` | No | Vercel + app.fragloesja.uk |
| `ENV` | No | `dev` |
| `USERS_FILE_PATH` | No | `users.yaml` |
| `PYTHON_VERSION` | No | `3.11.9` |

## Degradación MySQL

Commit `44dda32` agregó un exception handler global en `main.py` que captura `sqlalchemy.exc.OperationalError` y devuelve 503 limpio:

```json
{
  "detail": "Funcionalidad no disponible en cloud. Requiere el sistema operativo encendido. Predicciones y alertas están disponibles 24/7.",
  "status": "degraded",
  "available_endpoints": ["/health", "/auth/*", "/alerts/*", "/forecast/*", "/metrics/*"]
}
```

## Smoke test

| Endpoint | Status | Detalle |
|---|---|---|
| `/health` | ✅ 200 | `{"status":"ok"}` |
| `/auth/login` | ✅ 200 | JWT válido |
| `/alerts/stockout` | ✅ 200 | 46 alertas |
| `/forecast/MOTS1297` | ✅ 200 | Datos forecast |
| `/products?q=aceite` | ✅ 503 | Degradación limpia |
| `/products/MOTS1297/stock` | ✅ 503 | Degradación limpia |

## Build time

~3-5 min (Render auto-deploy desde GitHub main).

## Próximo paso: UptimeRobot

El humano debe configurar en https://uptimerobot.com:
- Type: HTTP(s)
- URL: `https://motoshop-cloud-api.onrender.com/health`
- Interval: 5 minutes
- Name: `motoshop-cloud-api-keepalive`
