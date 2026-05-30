# Diagnosis /alerts/stockout y /forecast — 2026-05-30

## Causa raíz

**(b) SQL Warehouse paused + config ausente**

Dos problemas simultáneos:

1. **SQL Warehouse `43bc044eaef4cca4` estaba STOPPED** (auto-stop 10 min). Al recibir query via SDK, el auto-resume tarda 60-90s, superando el `wait_timeout` de 50s en el código.

2. **Variables Databricks ausentes del API `.env`**:
   - `DATABRICKS_HOST` — no estaba en `motoshop-app\api\.env`
   - `DATABRICKS_TOKEN` — no estaba en `motoshop-app\api\.env`
   - `DATABRICKS_HTTP_PATH` — no existía en ningún `.env`
   
   El `Settings()` de config.py lee `.env` desde el working directory (`motoshop-app\api\.env`). Sin esas vars, `WorkspaceClient(host="", token="")` fallaba silenciosamente y la query al warehouse nunca se ejecutaba.

## Cambios aplicados

1. **Agregado `DATABRICKS_HTTP_PATH`** a `motoshop-app\api\.env`:
   ```
   DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/43bc044eaef4cca4
   ```
   (valor obtenido de la API REST de Databricks: `GET /api/2.0/sql/warehouses`)

2. **Agregados `DATABRICKS_HOST` y `DATABRICKS_TOKEN`** a `motoshop-app\api\.env` (copiados del root `.env`)

3. **Arrancado SQL Warehouse** vía API:
   ```
   POST /api/2.0/sql/warehouses/43bc044eaef4cca4/start
   ```
   Warehouse transitó a RUNNING en segundos (probablemente porque el auto-stop reciente mantenía el cluster caliente).

4. **Actualizado `infra/start_api.ps1`**: agregadas las 3 vars Databricks (leyendo del API `.env`) para que futuros reinicios no pierdan la config.

5. **Reiniciada la API** con las nuevas vars.

## Tiempo warm-up del warehouse

~2-3 segundos. El warehouse había sido auto-stopped hacía poco, el cluster seguía en cache. En un escenario real con warehouse frío, el warm-up tarda 60-90s.

## Smoke test final (vía túnel Cloudflare)

```
GET https://api.fragloesja.uk/alerts/stockout  → 200 OK (46 alertas)
GET https://api.fragloesja.uk/forecast/MOTS1297 → 200 OK (1 entry, predicted_qty: 2.34)
```

Ambos endpoints responden 200 con datos desde el túnel público.

## Deuda técnica

- **SQL Warehouse auto-stop 10 min**: agresivo para una PWA de operador que se usa en momentos discretos (cuando entra un cliente). Idealmente subirlo a 1h. Sin embargo, Databricks Serverless Starter Warehouse no permite cambiar auto_stop_mins desde la API gratuita (solo desde UI Premium). Diferir a F7 (migración MySQL 5.7+) o cuando se contrate un plan superior.
- **`start_api.ps1` falla si `MYSQL_ROOT_PASSWORD` no está en `.env`**: la verificación de MySQL usa `mysqladmin -u root` pero el root `.env` no tiene esa var. No crítico porque la API arranca igual (el error es solo en la verificación previa).
