# MotoShop · Auto-Pull and Apply (Windows)
#
# Reemplaza el ciclo manual del humano + Dev W para changes en backend.
# Funciona similar a Vercel/Render autodeploy pero local en PC Windows.
#
# Lógica:
#   1. git fetch origin main
#   2. Compara HEAD local vs origin/main
#   3. Si difieren, hace git pull + detecta qué cambió
#   4. Si cambió motoshop-app/api/** → restart API
#   5. Si cambió notebooks/gold/** → sync notebooks a Databricks
#   6. Si cambió infra/create_full_workflow.py → re-deploy workflow
#   7. Si hay migrations SQL nuevas (F7-* o F8-*) → log WARNING (humano debe aplicar manual)
#   8. Log resultado a infra\logs\auto_pull.log
#
# Disparado por Scheduled Task cada 5 min con catch-up.
# Configuración en infra\AUTO_PULL_SETUP.md
#
# Manual run:
#   powershell -ExecutionPolicy Bypass -File infra\auto_pull_and_apply.ps1
#
# Para deshabilitar (mantenimiento):
#   Crear archivo infra\AUTO_PULL_DISABLED — el script chequea y aborta.

param(
    [switch]$DryRun = $false
)

$candidateRoots = @(
    (Resolve-Path "$PSScriptRoot\..").Path,
    "C:\Users\MotoShop\Documents\javidevmoto\motoshopData",
    "C:\Users\MotoShop\Documents\javidevmoto"
)
$RepoRoot = $null
foreach ($cand in $candidateRoots) {
    if (Test-Path "$cand\.git") {
        $RepoRoot = $cand
        break
    }
}
if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
}
$LogFile = "$RepoRoot\infra\logs\auto_pull.log"
$DisableFlag = "$RepoRoot\infra\AUTO_PULL_DISABLED"
$LockFile = "$RepoRoot\infra\auto_pull.lock"

function Log {
    param([string]$Level, [string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [$Level] $Message"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

# ─── Pre-flight ─────────────────────────────────────────────

if (!(Test-Path $RepoRoot)) {
    Log "ERROR" "Repo root no existe: $RepoRoot"
    exit 1
}

# Crear logs dir si no existe
New-Item -ItemType Directory -Path "$RepoRoot\infra\logs" -Force | Out-Null

# Flag de deshabilitación manual
if (Test-Path $DisableFlag) {
    Log "INFO" "AUTO_PULL_DISABLED flag presente. Aborting."
    exit 0
}

# Lock para evitar runs concurrentes
if (Test-Path $LockFile) {
    $lockAge = (Get-Date) - (Get-Item $LockFile).LastWriteTime
    if ($lockAge.TotalMinutes -lt 10) {
        Log "WARN" "Lock file presente (otra instancia corriendo o stale). Aborting."
        exit 0
    } else {
        Log "WARN" "Lock file stale (>10min). Removing."
        Remove-Item $LockFile -Force
    }
}
New-Item -ItemType File -Path $LockFile | Out-Null

try {
    Set-Location $RepoRoot

    # ─── Fetch origin ────────────────────────────────────────

    Log "INFO" "Fetching origin..."
    $fetchOutput = git fetch origin main 2>&1
    if ($LASTEXITCODE -ne 0) {
        Log "ERROR" "git fetch falló: $fetchOutput"
        exit 1
    }

    $localHead = git rev-parse HEAD
    $remoteHead = git rev-parse origin/main

    if ($localHead -eq $remoteHead) {
        Log "INFO" "Up-to-date (HEAD=$($localHead.Substring(0,7))). Nothing to do."
        exit 0
    }

    Log "INFO" "Updates detected: local=$($localHead.Substring(0,7)) → remote=$($remoteHead.Substring(0,7))"

    # ─── Detectar qué cambió ─────────────────────────────────

    $changedFiles = git diff --name-only $localHead $remoteHead 2>&1
    if ($LASTEXITCODE -ne 0) {
        Log "ERROR" "git diff falló: $changedFiles"
        exit 1
    }

    $apiChanged = $changedFiles | Where-Object { $_ -match "^motoshop-app/api/" }
    $notebooksChanged = $changedFiles | Where-Object { $_ -match "^notebooks/gold/" }
    $workflowChanged = $changedFiles | Where-Object { $_ -match "^infra/create_full_workflow\.py$" }
    $migrationsNew = $changedFiles | Where-Object { $_ -match "^infra/migrations/F[7-9]-\d+.*\.sql$" }
    $scriptsChanged = $changedFiles | Where-Object { $_ -match "^infra/(start_|check_|auto_).*\.ps1$" }

    Log "INFO" "Changed files: $($changedFiles.Count). API=$($apiChanged.Count), notebooks=$($notebooksChanged.Count), workflow=$($workflowChanged.Count), migrations=$($migrationsNew.Count), scripts=$($scriptsChanged.Count)"

    if ($DryRun) {
        Log "INFO" "DryRun mode. No changes applied."
        $changedFiles | ForEach-Object { Log "INFO" "  Would pull: $_" }
        exit 0
    }

    # ─── Migrations SQL nuevas: WARN humano, no aplicar ─────

    if ($migrationsNew.Count -gt 0) {
        Log "WARN" "Migrations SQL nuevas detectadas (requieren backup manual + aplicación):"
        $migrationsNew | ForEach-Object { Log "WARN" "  $_" }
        Log "WARN" "Continuando con pull pero NO ejecuto migrations. Notificá al humano para aplicar manual."
    }

    # ─── Pull ────────────────────────────────────────────────

    Log "INFO" "Pulling..."
    $pullOutput = git pull --ff-only origin main 2>&1
    if ($LASTEXITCODE -ne 0) {
        Log "ERROR" "git pull falló (no es fast-forward?): $pullOutput"
        Log "ERROR" "Diff manual requerida. Aborting."
        exit 1
    }
    Log "INFO" "Pull OK"

    # ─── Restart API si cambió backend ───────────────────────

    if ($apiChanged.Count -gt 0 -or $scriptsChanged -contains "infra/start_api.ps1") {
        Log "INFO" "API changes detected ($($apiChanged.Count) files). Restarting..."

        # Stop API actual: buscar proceso escuchando en puerto 8000
        try {
            $portPids = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
            if ($portPids) {
                foreach ($p in $portPids) {
                    Log "INFO" "Stopping process on port 8000 PID $p"
                    Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
                }
            }
        } catch {}
        try {
            netstat -ano | Select-String ":8000\s+.*LISTENING" | ForEach-Object {
                if ($_ -match "(\d+)$") {
                    $nsPid = $matches[1]
                    Log "INFO" "Stopping netstat PID $nsPid"
                    Stop-Process -Id $nsPid -Force -ErrorAction SilentlyContinue
                }
            }
        } catch {}

        # Stop API actual (best-effort por nombre de proceso)
        $apiProcs = Get-Process python -ErrorAction SilentlyContinue | Where-Object {
            try {
                $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
                $cmdLine -match "uvicorn|motoshop_api"
            } catch { $false }
        }

        if ($apiProcs) {
            $apiProcs | ForEach-Object {
                Log "INFO" "Stopping uvicorn PID $($_.Id)"
                Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            }
            Start-Sleep -Seconds 2
        }

        # Re-instalar deps si pyproject.toml cambió
        if ($apiChanged -contains "motoshop-app/api/pyproject.toml") {
            Log "INFO" "pyproject.toml cambió. Reinstalando deps..."
            Push-Location "$RepoRoot\motoshop-app\api"
            $pipOutput = pip install -e . 2>&1
            Pop-Location
            if ($LASTEXITCODE -ne 0) {
                Log "ERROR" "pip install falló: $pipOutput"
                exit 1
            }
        }

        # Inyectar keys LLM en archivos .env locales desde Supabase si faltan
        $candRoots = @(
            $RepoRoot,
            "$RepoRoot\..",
            "C:\Users\MotoShop\Documents\javidevmoto",
            "C:\Users\MotoShop\Documents\javidevmoto\motoshopData"
        )
        if ($env:SUPABASE_URL -and $env:SUPABASE_SERVICE_KEY) {
            try {
                $headers = @{
                    "apikey" = $env:SUPABASE_SERVICE_KEY
                    "Authorization" = "Bearer $($env:SUPABASE_SERVICE_KEY)"
                }
                $resp = Invoke-RestMethod -Uri "$($env:SUPABASE_URL)/rest/v1/app_users?username=eq._system_config&select=allowed_modules" -Headers $headers -Method Get -TimeoutSec 5
                if ($resp -and $resp[0].allowed_modules) {
                    $kvPairs = @()
                    foreach ($item in $resp[0].allowed_modules) {
                        if ($item -match "^\s*([^=]+)=(.*)$") {
                            $kvPairs += @{ Key = $matches[1].Trim().ToUpper(); Val = $matches[2].Trim() }
                        }
                    }
                    foreach ($cr in $candRoots) {
                        $envCandidates = @("$cr\.env", "$cr\motoshop-app\api\.env")
                        foreach ($ef in $envCandidates) {
                            if (Test-Path $ef) {
                                $c = Get-Content $ef -Raw -ErrorAction SilentlyContinue
                                foreach ($pair in $kvPairs) {
                                    if ($c -and $c -notmatch "$($pair.Key)=") {
                                        Add-Content -Path $ef -Value "`n$($pair.Key)=$($pair.Val)"
                                        Log "INFO" "Inyectada $($pair.Key) desde Supabase en $ef"
                                    }
                                }
                            }
                        }
                    }
                }
            } catch {
                # degradacion silenciosa
            }
        }

        # Sincronizar DuckDB fresco bidireccional entre out y api/out en todas las rutas candidatas
        foreach ($tenant in @("motoshop", "masvital")) {
            $duckFiles = @()
            foreach ($cr in $candRoots) {
                $p1 = "$cr\out\${tenant}_gold.duckdb"
                $p2 = "$cr\motoshop-app\api\out\${tenant}_gold.duckdb"
                if (Test-Path $p1) { $duckFiles += (Get-Item $p1) }
                if (Test-Path $p2) { $duckFiles += (Get-Item $p2) }
            }
            if ($duckFiles.Count -gt 1) {
                $freshest = $duckFiles | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
                foreach ($target in $duckFiles) {
                    if ($target.FullName -ne $freshest.FullName -and $target.LastWriteTimeUtc -lt $freshest.LastWriteTimeUtc) {
                        Copy-Item -Path $freshest.FullName -Destination $target.FullName -Force -ErrorAction SilentlyContinue
                        Log "INFO" "Sincronizado $($freshest.FullName) -> $($target.FullName)"
                    }
                }
            }
        }

        # Start API
        Log "INFO" "Starting API via start_api.ps1..."
        Start-Process powershell -ArgumentList "-ExecutionPolicy", "Bypass", "-File", "$RepoRoot\infra\start_api.ps1" -WindowStyle Hidden

        # Smoke test (espera hasta 30s)
        $smokeOK = $false
        for ($i = 0; $i -lt 15; $i++) {
            Start-Sleep -Seconds 2
            try {
                $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -TimeoutSec 3 -ErrorAction Stop
                if ($resp.StatusCode -eq 200) {
                    $smokeOK = $true
                    Log "INFO" "API smoke test OK (200 en intento $($i+1))"
                    break
                }
            } catch { continue }
        }
        if (-not $smokeOK) {
            Log "ERROR" "API smoke test FAILED tras 30s. Revisar manualmente."
        }
    }

    # ─── Verificar Túnel Cloudflare (motoshop-local) ──────────
    try {
        $tunnelCheckUrl = if ($env:TUNNEL_URL) { $env:TUNNEL_URL } else { "https://motoshop-local.fragloesja.uk/health" }
        $cfResp = Invoke-WebRequest -Uri $tunnelCheckUrl -TimeoutSec 6 -UseBasicParsing -ErrorAction Stop
        if ($cfResp.StatusCode -eq 200) {
            Log "INFO" "Túnel Cloudflare OK ($tunnelCheckUrl)"
        } else {
            throw "Status code $($cfResp.StatusCode)"
        }
    } catch {
        Log "WARN" "Túnel Cloudflare no responde ($($_)). Recuperando via task MotoShopTunnelSvc..."
        $cfTask = Get-ScheduledTask -TaskName "MotoShopTunnelSvc" -ErrorAction SilentlyContinue
        if ($cfTask) {
            try {
                Stop-ScheduledTask -TaskName "MotoShopTunnelSvc" -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 2
                Start-ScheduledTask -TaskName "MotoShopTunnelSvc" -ErrorAction Stop
                Log "INFO" "Task MotoShopTunnelSvc reiniciada."
            } catch {
                Log "WARN" "Reinicio de task fallo: $($_.Exception.Message)"
                & "$RepoRoot\infra\start_tunnel.ps1"
            }
        } else {
            & "$RepoRoot\infra\start_tunnel.ps1"
        }
    }

    # ─── Sync notebooks si cambió gold/ ─────────────────────

    if ($notebooksChanged.Count -gt 0) {
        Log "INFO" "Notebook changes detected ($($notebooksChanged.Count) files). Syncing to Databricks..."
        $syncOutput = python "$RepoRoot\infra\upload_all_notebooks.py" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Log "ERROR" "upload_all_notebooks.py falló: $syncOutput"
        } else {
            Log "INFO" "Notebooks sync OK"
        }
    }

    # ─── Redeploy workflow si cambió ────────────────────────

    if ($workflowChanged.Count -gt 0) {
        Log "INFO" "Workflow definition changed. Redeploying..."
        $deployOutput = python "$RepoRoot\infra\create_full_workflow.py" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Log "ERROR" "create_full_workflow.py falló: $deployOutput"
        } else {
            Log "INFO" "Workflow redeploy OK"
        }
    }

    Log "INFO" "Auto-apply COMPLETE. New HEAD=$($remoteHead.Substring(0,7))"

} catch {
    Log "ERROR" "Excepción no manejada: $_"
    Log "ERROR" $_.ScriptStackTrace
    exit 1
} finally {
    if (Test-Path $LockFile) {
        Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
    }
}
