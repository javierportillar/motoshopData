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

if (-not $ApiToken) {
    Write-Log "MOTO_API_TOKEN not set. Export it or pass -ApiToken <token>" "ERROR"
    exit 1
}

try {
    Write-Log "Starting DuckDB data refresh from R2..."

    # 1. Trigger refresh
    $refreshUrl = "$ApiBaseUrl/api/admin/data/refresh"
    $headers = @{
        "Authorization" = "Bearer $ApiToken"
        "Content-Type"  = "application/json"
    }

    Write-Log "POST $refreshUrl"
    $response = Invoke-RestMethod -Uri $refreshUrl -Method Post -Headers $headers -SkipCertificateCheck

    Write-Log "Refresh response: $($response | ConvertTo-Json -Compress)"
    Write-Log "DuckDB refreshed — path=$($response.path) size=$($response.size_bytes) freshness=$($response.freshness_utc)"

    # 2. Verify freshness
    Start-Sleep -Seconds 2
    $healthUrl = "$ApiBaseUrl/health/data-freshness"
    Write-Log "GET $healthUrl"
    $health = Invoke-RestMethod -Uri $healthUrl -Method Get -SkipCertificateCheck

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
