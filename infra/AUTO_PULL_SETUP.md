# Auto-Pull Windows · Setup

> Cierra el gap operativo: Windows backend se actualiza solo cuando hay commits, igual que Vercel (PWA) y Render (cloud-api).
> El humano (Javier) ya no tiene que disparar Dev W para ciclos rutinarios. Dev W sigue existiendo solo para casos no-rutinarios (FIX1, migrations, troubleshooting).

---

## Qué hace

Cada 5 min, un Scheduled Task en Windows ejecuta `infra\auto_pull_and_apply.ps1` que:

1. `git fetch origin main`
2. Compara HEAD local vs origin/main
3. Si difieren:
   - `git pull --ff-only origin main`
   - Detecta qué cambió (paths)
   - Si cambió `motoshop-app/api/**` → **reinicia API automáticamente**
   - Si cambió `notebooks/gold/**` → **sync notebooks a Databricks**
   - Si cambió `infra/create_full_workflow.py` → **re-deploya workflow**
   - Si hay migrations SQL nuevas (`F7-*` o `F8-*`) → **WARN al log** (humano debe aplicar manual con backup)
4. Logea resultado en `infra\logs\auto_pull.log`

---

## Setup (una sola vez)

### 1. Verificar pre-requisitos

```powershell
cd C:\Users\MotoShop\Documents\javidevmoto

# Git accesible
git --version

# Python con databricks-sdk
python -c "from databricks.sdk import WorkspaceClient; print('OK')"

# .env tiene DATABRICKS_HOST/TOKEN configurados
Get-Content motoshop-app\api\.env | Select-String "DATABRICKS_"
```

### 2. Probar manual primero

```powershell
# Dry-run (no aplica cambios, solo loguea qué haría)
powershell -ExecutionPolicy Bypass -File infra\auto_pull_and_apply.ps1 -DryRun -Verbose

# Run real con verbose
powershell -ExecutionPolicy Bypass -File infra\auto_pull_and_apply.ps1 -Verbose

# Ver log
Get-Content infra\logs\auto_pull.log -Tail 20
```

### 3. Crear Scheduled Task

```powershell
# Ejecutar como administrador en PowerShell

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File C:\Users\MotoShop\Documents\javidevmoto\infra\auto_pull_and_apply.ps1"

$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 5)

$principal = New-ScheduledTaskPrincipal `
    -UserId "MotoShop" `
    -LogonType S4U `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName "MotoShop_AutoPull" `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Auto-pull + restart API + sync notebooks cada 5 min cuando hay cambios en main"
```

### 4. Verificar Scheduled Task

```powershell
Get-ScheduledTask -TaskName "MotoShop_AutoPull"
Get-ScheduledTaskInfo -TaskName "MotoShop_AutoPull"

# Ejecutar manualmente para test
Start-ScheduledTask -TaskName "MotoShop_AutoPull"

# Ver log después de unos segundos
Start-Sleep -Seconds 10
Get-Content infra\logs\auto_pull.log -Tail 20
```

---

## Cómo deshabilitar temporalmente

Para mantenimiento o debug, sin desinstalar el task:

```powershell
# Deshabilitar
New-Item -ItemType File -Path "C:\Users\MotoShop\Documents\javidevmoto\infra\AUTO_PULL_DISABLED"

# Habilitar
Remove-Item "C:\Users\MotoShop\Documents\javidevmoto\infra\AUTO_PULL_DISABLED"
```

El script detecta el flag y aborta sin tocar nada.

---

## Casos que el script NO maneja (intervención humana sigue requerida)

| Caso | Por qué no se automatiza | Acción humana |
|------|-------------------------|---------------|
| **Migrations SQL nuevas** (`infra/migrations/F7-*.sql`, `F8-*.sql`) | Requiere backup explícito + revisión humana antes de aplicar a producción | Script loguea WARN. Dev W aplica manual: `mysql -u root motoshop2024 < migration.sql` con backup previo |
| **users.yaml** modificaciones | Gitignored — no se versiona | Editar manualmente en Windows |
| **Rotación tokens Databricks** | Requiere generar nuevo PAT en UI + actualizar `.env` | Manual |
| **Cambios en `.env`** | Gitignored | Manual |
| **Migración MySQL major version** | Riesgo alto, requiere DR plan | Manual con backup completo |
| **Cambios en este script** | Auto-actualizarse podría romper el ciclo | Manual (después de testing en otro ambiente) |

---

## Monitoreo

```powershell
# Últimas 50 líneas
Get-Content infra\logs\auto_pull.log -Tail 50

# Ver solo errores
Select-String -Path infra\logs\auto_pull.log -Pattern "\[ERROR\]" | Select-Object -Last 20

# Ver solo warnings
Select-String -Path infra\logs\auto_pull.log -Pattern "\[WARN\]" | Select-Object -Last 20

# Stats: cuántas ejecuciones hoy
$today = (Get-Date).ToString("yyyy-MM-dd")
(Select-String -Path infra\logs\auto_pull.log -Pattern "^\[$today").Count
```

### Rotación de log

El log puede crecer mucho. Configurar rotación mensual:

```powershell
# Ejecutar mensual via Scheduled Task separado, o cron equivalente
$logFile = "C:\Users\MotoShop\Documents\javidevmoto\infra\logs\auto_pull.log"
$archive = "$logFile.$(Get-Date -Format 'yyyyMM').archive"
if (Test-Path $logFile) {
    Move-Item $logFile $archive
}
```

---

## Comparativa con plataformas existentes

| Plataforma | Auto-deploy | Trigger | Notas |
|------------|-------------|---------|-------|
| **Vercel (PWA)** | ✅ | Push a `main` via webhook GitHub | Sin intervención humana |
| **Render (cloud-api)** | ✅ | Push a `main` via webhook GitHub | Sin intervención humana |
| **Windows (api)** | ✅ desde F7-E-FIX2 | **Scheduled Task cada 5 min** (polling) | Sin intervención humana excepto migrations |

Asimetría histórica resuelta: ahora los 3 ambientes son self-updating.

---

## V1.5 Refresh — DuckDB Data Refresh (NEW)

> **Sprint 3** · Reemplaza el nightly push a Databricks con un refresh directo del archivo DuckDB desde R2.
> El pipeline `run_all.py` corre en Linux/Mac (via GitHub Actions o manual) y sube `motoshop_gold.duckdb` a R2.
> Windows solo necesita refrescar el archivo local desde R2 sin reiniciar uvicorn.

### Qué hace

1. `POST /api/admin/data/refresh` (admin-only) descarga el nuevo DuckDB desde R2 y limpia el cache
2. El endpoint NUNCA reinicia uvicorn — la próxima request usa los datos frescos
3. `/health/data-freshness` reporta el lag desde el último refresh (mtime del archivo)

### Setup (una sola vez)

#### 1. Configurar R2 en el .env

```powershell
# Agregar a motoshop-app\api\.env:
R2_ENDPOINT=https://<account>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=<key>
R2_SECRET_ACCESS_KEY=<secret>
R2_BUCKET=motoshop-gold
DATA_BACKEND=duckdb
DUCKDB_PATH=C:\Users\MotoShop\Documents\javidevmoto\out\motoshop_gold.duckdb
```

#### 2. Obtener token JWT de admin

```powershell
# Desde el mismo directorio que la API
cd motoshop-app\api\src
$env:JWT_SECRET = "tu-secret-real"
python -c "
from motoshop_api.auth.jwt import create_access_token
print(create_access_token('admin', 'admin'))
"
```

Guardar el token como variable de entorno `MOTO_API_TOKEN` en el Scheduled Task.

#### 3. Crear Scheduled Task (02:00 COL diario)

```powershell
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File C:\Users\MotoShop\Documents\javidevmoto\infra\refresh_v15.ps1"

$trigger = New-ScheduledTaskTrigger -Daily -At "02:00"

$principal = New-ScheduledTaskPrincipal `
    -UserId "MotoShop" `
    -LogonType S4U `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName "MotoShop_V15_Refresh" `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Description "V1.5 DuckDB refresh from R2 diario a las 02:00 COL"
```

#### 4. Probar manual

```powershell
$env:MOTO_API_TOKEN = "tu-token-jwt"
powershell -ExecutionPolicy Bypass -File infra\refresh_v15.ps1 -Verbose

# Ver log
Get-Content infra\logs\refresh_v15.log -Tail 20
```

### Cómo funciona el refresh sin restart

El endpoint `POST /api/admin/data/refresh`:
1. Borra el archivo DuckDB local
2. Lo descarga fresco desde R2 via boto3
3. Llama a `_clear_metrics_cache()` que vacía el TTL cache de todos los endpoints
4. La próxima request a cualquier `/api/metrics/*` instancia un `DuckDBMetricsRepo` nuevo que abre el archivo actualizado

No hay mutación de singletons ni restart de uvicorn. La arquitectura `Depends(get_repo)` de FastAPI crea una conexión fresh por request.

### Monitoreo

```powershell
# Ver último refresh
curl http://localhost:8000/health/data-freshness

# Ver log de refreshes
Get-Content infra\logs\refresh_v15.log -Tail 20
```

---

## Roadmap V2

Esto entra como mitigación parcial de **R-V2-27 (Sin CI/CD pipeline real)** del `docs/roadmap-v2-produccion.md`. En V2 producción, esto se reemplaza por:

- GitHub Actions con self-hosted runner Windows
- Webhook-based deploy (sin polling 5 min)
- Migrations aplicadas automáticamente con backup pre/post
- Tests pre-deploy en branch protection

Por ahora (V1 académica), el Scheduled Task polling es suficiente y robusto.

---

## Troubleshooting

### Script no se ejecuta

```powershell
# Ver historial del Scheduled Task
Get-ScheduledTaskInfo -TaskName "MotoShop_AutoPull"

# Ver Event Log
Get-WinEvent -LogName "Microsoft-Windows-TaskScheduler/Operational" -MaxEvents 20
```

### git pull falla con "not fast-forward"

Significa que alguien commiteó local sin pushear, y ahora hay divergencia. El script aborta para no perder commits locales. Resolver manual:

```powershell
git status
git log HEAD..origin/main --oneline  # commits que faltan
git log origin/main..HEAD --oneline  # commits locales
# Resolver merge o rebase manualmente
```

### API no arranca tras pull

```powershell
# Ver logs uvicorn (donde sea que stdout/stderr esté redirigido)
Get-Content infra\logs\api.log -Tail 50  # si existe

# Diagnosticar manual
cd motoshop-app\api
uvicorn motoshop_api.main:app --host 0.0.0.0 --port 8000  # ver errores en consola
```

### Notebooks sync falla

```powershell
# Verificar token
python -c "
from databricks.sdk import WorkspaceClient
import os
w = WorkspaceClient(host=os.environ['DATABRICKS_HOST'], token=os.environ['DATABRICKS_TOKEN'])
print(w.current_user.me().user_name)
"
```

Si falla, token expirado. Generar nuevo PAT en Databricks UI y actualizar `motoshop-app\api\.env`.
