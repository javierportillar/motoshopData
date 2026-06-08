# MotoShop V1.5 · DuckDB Data Refresh
#
# Programar via Windows Scheduled Task a las 02:00 COL diario.
# Llama al endpoint POST /api/admin/data/refresh con token de admin.
# Loguea cada step a pipeline_runs.duckdb y lo sube a R2.

param(
    [string]$ApiBaseUrl = "http://localhost:8000",
    [string]$ApiToken = $env:MOTO_API_TOKEN
)

$ErrorActionPreference = "Stop"
$logFile = Join-Path $PSScriptRoot "logs\refresh_v15.log"
$rootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $rootDir ".venv-infra\Scripts\python.exe"
$dbHelper = Join-Path $rootDir "scripts\pipeline_runs_db.py"
$uploadScript = Join-Path $rootDir "scripts\upload_duckdb_to_r2.py"

# ── Helpers de logging a archivo ──────────────────────────────────────────────
function Write-Log {
    param($Message, $Level = "INFO")
    $ts = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    $line = "[$ts] [$Level] $Message"
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

# ── Helpers de logging a DuckDB (pipeline_runs.duckdb) ───────────────────────
$global:RunId = $null

function Invoke-DB {
    param([string]$Arguments)
    $argList = @($dbHelper) + ($Arguments -split ' ')
    $result = & $python $argList 2>&1
    $exitCode = $LASTEXITCODE
    $lastLine = ($result | Select-Object -Last 1) -join "`n"
    if ($exitCode -ne 0) {
        Write-Log "pipeline_runs_db.py failed: $($lastLine -replace '\s+', ' ')" "WARN"
        return $null
    }
    return $lastLine.Trim()
}

function Start-PipelineRun {
    param($PipelineName, $TriggeredBy)
    $id = Invoke-DB "start-run --pipeline $PipelineName --triggered-by $TriggeredBy"
    if ($id -match '^\d+$') {
        $global:RunId = [int]$id
        Write-Log "Pipeline run #$global:RunId creado en pipeline_runs.duckdb"
        return $global:RunId
    }
    Write-Log "No se pudo crear pipeline run en DuckDB" "WARN"
    return $null
}

function Start-PipelineStep {
    param($StepOrder, $StepName)
    if (-not $global:RunId) { return $null }
    $id = Invoke-DB "start-step --run-id $global:RunId --step-order $StepOrder --step-name $StepName"
    if ($id -match '^\d+$') { return [int]$id }
    return $null
}

function Complete-PipelineStep {
    param($StepId, $DurationSeconds, $LogExcerpt, $Status = "success", $ErrorMessage = $null)
    if (-not $StepId) { return }
    # Pasamos log_excerpt y error_message por variables de entorno (pueden contener comillas/spacios)
    $env:PIPELINE_DB_LOG_EXCERPT = if ($LogExcerpt) { ($LogExcerpt -replace '[^\x20-\x7E\r\n\t]', ' ').Substring(0, [math]::Min($LogExcerpt.Length, 8000)) } else { '' }
    $env:PIPELINE_DB_ERROR_MSG = if ($ErrorMessage) { ($ErrorMessage -replace '[^\x20-\x7E\r\n\t]', ' ') } else { '' }
    Invoke-DB "complete-step --step-id $StepId --duration $DurationSeconds --status $Status"
    Remove-Item "env:PIPELINE_DB_LOG_EXCERPT" -ErrorAction SilentlyContinue
    Remove-Item "env:PIPELINE_DB_ERROR_MSG" -ErrorAction SilentlyContinue
}

function Complete-PipelineRun {
    param($DurationSeconds, $Status = "success", $ErrorMessage = $null)
    if (-not $global:RunId) { return }
    $env:PIPELINE_DB_ERROR_MSG = if ($ErrorMessage) { ($ErrorMessage -replace '[^\x20-\x7E\r\n\t]', ' ') } else { '' }
    Invoke-DB "complete-run --run-id $global:RunId --duration $DurationSeconds --status $Status"
    Remove-Item "env:PIPELINE_DB_ERROR_MSG" -ErrorAction SilentlyContinue
}

# ── Helper: ejecutar step con medicion + captura de output ───────────────────
function Invoke-Step {
    param(
        [scriptblock]$ScriptBlock,
        [string]$StepName,
        [int]$StepOrder
    )
    $stepId = Start-PipelineStep -StepOrder $StepOrder -StepName $StepName
    $stepStart = Get-Date
    $stepLog = Join-Path $logDir "step_${StepName}.tmp"
    $savedEA = $ErrorActionPreference

    try {
        $ErrorActionPreference = "Continue"
        & $ScriptBlock *> $stepLog
        $exitCode = $LASTEXITCODE
        $ErrorActionPreference = $savedEA
        $dur = [math]::Max(0, [math]::Round(((Get-Date) - $stepStart).TotalSeconds, 1))
        $excerptLines = Get-Content $stepLog -Tail 50 -ErrorAction SilentlyContinue
        $excerpt = $excerptLines -join "`n"

        if ($exitCode -ne 0) {
            Complete-PipelineStep -StepId $stepId -DurationSeconds $dur -LogExcerpt $excerpt -Status "failed" -ErrorMessage "Exit code $exitCode"
            throw "$StepName failed with exit code $exitCode"
        }

        Complete-PipelineStep -StepId $stepId -DurationSeconds $dur -LogExcerpt $excerpt -Status "success"
        Write-Log "$StepName completed (${dur}s)" "OK"
    } catch {
        $ErrorActionPreference = $savedEA
        if ($stepId) {
            $dur = [math]::Max(0, [math]::Round(((Get-Date) - $stepStart).TotalSeconds, 1))
            $excerptLines = if (Test-Path $stepLog) { Get-Content $stepLog -Tail 50 -ErrorAction SilentlyContinue } else { @() }
            $excerpt = $excerptLines -join "`n"
            Complete-PipelineStep -StepId $stepId -DurationSeconds $dur -LogExcerpt $excerpt -Status "failed" -ErrorMessage $_.Exception.Message
        }
        throw
    } finally {
        $ErrorActionPreference = $savedEA
        if (Test-Path $stepLog) { Remove-Item $stepLog -Force -ErrorAction SilentlyContinue }
    }
}

# ── Main ─────────────────────────────────────────────────────────────────────
$logDir = Split-Path $logFile -Parent
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# Cargar vars del .env al entorno
$envFile = Join-Path $PSScriptRoot "..\.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^\s*([^#=]+)=(.*)$") {
            $key = $matches[1].Trim()
            $val = $matches[2].Trim('"', "'")
            Set-Item -Path "env:$key" -Value $val -ErrorAction SilentlyContinue
        }
    }
    Write-Log "Variables de entorno cargadas desde .env"
}

if (-not $ApiToken) { $ApiToken = $env:MOTO_API_TOKEN }

if (-not $ApiToken) {
    Write-Log "MOTO_API_TOKEN not set. Export it or pass -ApiToken <token>" "ERROR"
    exit 1
}

$env:PYTHONPATH = $rootDir
$globalStart = Get-Date

# ── Helpers de post-publish (no loguean al DB para evitar estado stale) ───────
function Publish-PipelineRunToR2 {
    Write-Log "Subiendo pipeline_runs.duckdb a R2..." "INFO"
    $result = & $python $uploadScript 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Upload a R2 falló: $($result[-1])" "WARN"
    } else {
        Write-Log "Upload a R2 completado" "OK"
    }
}

function Refresh-PipelineApi {
    Write-Log "Refrescando API con pipeline_runs.duckdb desde R2..." "INFO"
    $refreshUrl = "$ApiBaseUrl/api/admin/pipeline/refresh"
    $headers = @{
        "Authorization" = "Bearer $ApiToken"
        "Content-Type"  = "application/json"
    }
    try {
        $response = Invoke-RestMethod -Uri $refreshUrl -Method Post -Headers $headers
        Write-Host "Pipeline refresh response: $($response | ConvertTo-Json -Compress)"
        Write-Log "Pipeline refresh completado" "OK"
    } catch {
        Write-Log "Pipeline refresh falló: $($_.Exception.Message)" "WARN"
    }
}

# Inicializar run en DuckDB
Start-PipelineRun -PipelineName "refresh_v15" -TriggeredBy "scheduled"

try {
    $stepOrder = 0

    # ── Step 1: Pipeline (run_all.py) ─────────────────────────────────────
    $stepOrder++
    Invoke-Step -StepOrder $stepOrder -StepName "run_all" -ScriptBlock {
        & $python (Join-Path $rootDir "pipeline\run_all.py")
    }

    # ── Step 2: Trigger API data refresh (solo data DuckDB) ───────────────
    $stepOrder++
    Invoke-Step -StepOrder $stepOrder -StepName "api_refresh" -ScriptBlock {
        $refreshUrl = "$ApiBaseUrl/api/admin/data/refresh"
        $headers = @{
            "Authorization" = "Bearer $ApiToken"
            "Content-Type"  = "application/json"
        }
        Write-Host "POST $refreshUrl"
        $response = Invoke-RestMethod -Uri $refreshUrl -Method Post -Headers $headers
        Write-Host "Refresh response: $($response | ConvertTo-Json -Compress)"
        Start-Sleep -Seconds 2
        $healthUrl = "$ApiBaseUrl/api/health/data-freshness"
        Write-Host "GET $healthUrl"
        $health = Invoke-RestMethod -Uri $healthUrl -Method Get
        Write-Host "Data freshness: status=$($health.status) lag=$($health.lag_hours)h backend=$($health.backend)"
        if ($health.status -eq "OK" -or $health.status -eq "WARN") {
            Write-Log "Refresh successful" "OK"
        } else {
            Write-Log "Refresh completed but freshness is $($health.status)" "WARN"
        }
    }

    # ── Finalizar run como exitoso ────────────────────────────────────────
    $totalDur = [math]::Round(((Get-Date) - $globalStart).TotalSeconds, 1)
    Complete-PipelineRun -DurationSeconds $totalDur -Status "success"
    Write-Log "Pipeline completado (${totalDur}s)" "OK"

    # ── Post-publish: upload final + refresh API (NO logueado al DB) ──────
    Publish-PipelineRunToR2
    Refresh-PipelineApi

    Write-Log "Pipeline refresh_v15 completado exitosamente" "OK"

} catch {
    $err = $_.Exception.Message
    Write-Log "Refresh failed: $err" "ERROR"
    $totalDur = [math]::Round(((Get-Date) - $globalStart).TotalSeconds, 1)
    Complete-PipelineRun -DurationSeconds $totalDur -Status "failed" -ErrorMessage $err

    # Upload final incluso en falla para que el estado sea visible en API
    Publish-PipelineRunToR2
    Refresh-PipelineApi

    exit 1
}
