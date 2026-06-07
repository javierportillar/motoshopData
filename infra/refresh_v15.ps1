# MotoShop V1.5 · DuckDB Data Refresh
#
# Programar via Windows Scheduled Task a las 02:00 COL diario.
# Llama al endpoint POST /api/admin/data/refresh con token de admin.
#
# Setup (una sola vez):
#   1. Asegurate que el .env tiene R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY
#   2. Genera un token JWT de admin y guardalo aca (variable $API_TOKEN abajo)
#      o exporta la variable de entorno MOTO_API_TOKEN
#   3. Programa el Scheduled Task:
#      $action = New-ScheduledTaskAction -Execute "powershell.exe" `
#          -Argument "-ExecutionPolicy Bypass -File C:\Users\MotoShop\Documents\javidevmoto\infra\refresh_v15.ps1"
#      $trigger = New-ScheduledTaskTrigger -Daily -At "02:00"
#      Register-ScheduledTask -TaskName "MotoShop_V15_Refresh" -Action $action -Trigger $trigger

param(
    [string]$ApiBaseUrl = "http://localhost:8000",
    [string]$ApiToken = $env:MOTO_API_TOKEN
)

$ErrorActionPreference = "Stop"
$logFile = Join-Path $PSScriptRoot "logs\refresh_v15.log"

function Write-Log {
    param($Message, $Level = "INFO")
    $ts = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    $line = "[$ts] [$Level] $Message"
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

# Ensure log dir
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

# Si el token no vino por parámetro, usar el que cargamos del .env
if (-not $ApiToken) { $ApiToken = $env:MOTO_API_TOKEN }

if (-not $ApiToken) {
    Write-Log "MOTO_API_TOKEN not set. Export it or pass -ApiToken <token>" "ERROR"
    exit 1
}

try {
    # 0. Run pipeline: MySQL → bronze → silver → gold → DuckDB
    $rootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
    $python = Join-Path $rootDir ".venv-infra\Scripts\python.exe"
    $env:PYTHONPATH = $rootDir

    Write-Log "Running pipeline (run_all.py)..."
    & $python (Join-Path $rootDir "pipeline\run_all.py") *>> $logFile
    if ($LASTEXITCODE -ne 0) { throw "Pipeline failed with exit code $LASTEXITCODE" }
    Write-Log "Pipeline completed" "OK"

    # 0b. Upload DuckDB to R2
    Write-Log "Uploading DuckDB to R2..."
    & $python (Join-Path $rootDir "scripts\upload_duckdb_to_r2.py") *>> $logFile
    if ($LASTEXITCODE -ne 0) { throw "Upload failed with exit code $LASTEXITCODE" }
    Write-Log "Upload successful" "OK"

    # 1. Trigger API refresh
    $refreshUrl = "$ApiBaseUrl/api/admin/data/refresh"
    $headers = @{
        "Authorization" = "Bearer $ApiToken"
        "Content-Type"  = "application/json"
    }

    Write-Log "POST $refreshUrl"
    $response = Invoke-RestMethod -Uri $refreshUrl -Method Post -Headers $headers

    Write-Log "Refresh response: $($response | ConvertTo-Json -Compress)"
    Write-Log "DuckDB refreshed - path=$($response.path) size=$($response.size_bytes) freshness=$($response.freshness_utc)"

    # 2. Verify freshness
    Start-Sleep -Seconds 2
    $healthUrl = "$ApiBaseUrl/api/health/data-freshness"
    Write-Log "GET $healthUrl"
    $health = Invoke-RestMethod -Uri $healthUrl -Method Get

    Write-Log "Data freshness: status=$($health.status) lag=$($health.lag_hours)h backend=$($health.backend)"

    if ($health.status -eq "OK" -or $health.status -eq "WARN") {
        Write-Log "Refresh successful" "OK"
        exit 0
    } else {
        Write-Log "Refresh completed but freshness is $($health.status)" "WARN"
        exit 0
    }
} catch {
    $err = $_.Exception.Message
    Write-Log "Refresh failed: $err" "ERROR"
    exit 1
}
