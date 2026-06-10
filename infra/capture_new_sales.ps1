# capture_new_sales.ps1
# Wrapper que carga .env y ejecuta capture_new_sales.py
# Usado por: MotoShop_CaptureNewSales (Scheduled Task)

$ErrorActionPreference = "Stop"
$rootDir = Resolve-Path "$PSScriptRoot\.."
$logFile = Join-Path $PSScriptRoot "logs\capture_new_sales.log"
$python = Join-Path $rootDir ".venv-infra\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

function Write-Log {
    param($Message, $Level = "INFO")
    $ts = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    $line = "[$ts] [$Level] $Message"
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

# ── Cargar .env ─────────────────────────────────────────────
$envFile = Join-Path $rootDir "motoshop-app\api\.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^\s*([A-Z_][A-Z0-9_]*)=(.*)$") {
            $key = $matches[1]
            $val = $matches[2] -replace '^"|"$', ''
            Set-Item -Path "env:$key" -Value $val -ErrorAction SilentlyContinue
        }
    }
}

# ── Ejecutar capture ────────────────────────────────────────
$scriptPath = Join-Path $rootDir "scripts\capture_new_sales.py"
Write-Log "Ejecutando: $scriptPath"

$result = & $python $scriptPath 2>&1
$exitCode = $LASTEXITCODE

foreach ($line in $result) {
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

# Exit code 0 = sin datos, >0 puede ser archivos bloqueados (normal en ejecución concurrente)
if ($exitCode -eq 0) {
    Write-Log "Capture completado: sin datos nuevos"
} else {
    Write-Log "Capture completado con código $exitCode (puede ser archivo bloqueado, se recupera solo)"
}
