# capture_new_sales.ps1
# Wrapper que carga .env y ejecuta capture_new_sales.py
# Usado por: MotoShop_CaptureNewSales (Scheduled Task)

$rootDir = Resolve-Path "$PSScriptRoot\.."
$logFile = Join-Path $PSScriptRoot "logs\capture_new_sales.log"
$python = Join-Path $rootDir ".venv-infra\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

# Fijar CWD al project root para que DUCKDB_PATH relativo funcione
Set-Location $rootDir

function Write-Log {
    param($Message, $Level = "INFO")
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [$Level] $Message"
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

# Cargar .env
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

# Auto-restore: si falta el DuckDB gold, descargar desde R2
$duckdbPath = Join-Path $rootDir "out\motoshop_gold.duckdb"
if (-not (Test-Path $duckdbPath)) {
    Write-Log "DuckDB gold no encontrado - intentando descargar desde R2..." "WARN"
    & $python "$rootDir\scripts\download_duckdb_from_r2.py" 2>&1 | ForEach-Object {
        $lineStr = "$_"
        Write-Host $lineStr
        Add-Content -Path $logFile -Value $lineStr
    }
    if (Test-Path $duckdbPath) {
        Write-Log "DuckDB gold restaurado desde R2" "INFO"
    } else {
        Write-Log "No se pudo restaurar DuckDB desde R2 - continuando" "WARN"
    }
}

# Ejecutar capture
$scriptPath = Join-Path $rootDir "scripts\capture_new_sales.py"
Write-Log "Ejecutando: $scriptPath"

$savedEA = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$stdout = & $python $scriptPath 2>&1
$exitCode = $LASTEXITCODE
$ErrorActionPreference = $savedEA

# Escribir TODO el output al log
foreach ($line in $stdout) {
    $lineStr = "$line"
    Write-Host $lineStr
    Add-Content -Path $logFile -Value $lineStr
}

# Si se capturaron facturas, refrescar API cloud
$capturoDatos = ($stdout | Select-String -Pattern "Capturadas" | Select-Object -First 1)
if ($capturoDatos) {
    Write-Log "Facturas capturadas - refrescando API cloud..." "INFO"
    & $python -c "
import json, urllib.request
API = r'https://api.fragloesja.uk'
try:
    r = urllib.request.Request(f'{API}/api/auth/login',
        data=json.dumps({'username':'admin','password':'FG28'}).encode(),
        headers={'Content-Type':'application/json'}, method='POST')
    with urllib.request.urlopen(r, timeout=15) as resp:
        token = json.loads(resp.read().decode())['access_token']
    for ep in ['/api/admin/data/refresh', '/api/admin/pipeline/refresh']:
        for i in range(3):
            try:
                r2 = urllib.request.Request(f'{API}{ep}',
                    data=b'{}',
                    headers={'Authorization':f'Bearer {token}','Content-Type':'application/json'},
                    method='POST')
                with urllib.request.urlopen(r2, timeout=30) as resp2:
                    print(f'Refresh {ep} att {i+1}: {json.loads(resp2.read().decode()).get(\"status\")}')
            except Exception as e:
                print(f'Refresh {ep} att {i+1}: {e}')
    print('API refresh completado')
except Exception as e:
    print(f'API refresh fallo: {e}')
" 2>&1 | ForEach-Object {
        $lineStr = "$_"
        Write-Host $lineStr
        Add-Content -Path $logFile -Value $lineStr
    }
}

if ($exitCode -eq 0) {
    Write-Log "Capture completado: sin datos nuevos"
} else {
    Write-Log "Capture completado con codigo $exitCode (puede ser archivo bloqueado, se recupera solo)"
}
