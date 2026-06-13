# download_gold_duckdb.ps1
# Descarga out/motoshop_gold.duckdb desde R2 si no existe localmente.
# Uso: powershell -ExecutionPolicy Bypass -File infra\download_gold_duckdb.ps1

$ErrorActionPreference = "Continue"
$ProjectRoot = "C:\Users\MotoShop\Documents\javidevmoto"
$VenvActivate = "$ProjectRoot\.venv-infra\Scripts\Activate.ps1"

$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "[$ts] Verificando DuckDB gold..."

$DbPath = "$ProjectRoot\out\motoshop_gold.duckdb"
if (Test-Path $DbPath) {
    $size = (Get-Item $DbPath).Length / 1MB
    Write-Host "[$ts] DuckDB ya existe: $DbPath (${size:F0} MB)"
    exit 0
}

Write-Host "[$ts] DuckDB no encontrado. Descargando desde R2..."

try {
    # Activar venv
    & $VenvActivate
} catch {
    Write-Host "[$ts] WARN: Fallo al activar venv: $_"
}

python "$ProjectRoot\scripts\download_duckdb_from_r2.py"
$exitCode = $LASTEXITCODE

if ($exitCode -eq 0 -and (Test-Path $DbPath)) {
    $size = (Get-Item $DbPath).Length / 1MB
    Write-Host "[$ts] DUCKDB RESTAURADO: $DbPath (${size:F0} MB)"
    exit 0
} else {
    Write-Host "[$ts] ERROR: No se pudo restaurar DuckDB desde R2 (exit=$exitCode)"
    exit 1
}
