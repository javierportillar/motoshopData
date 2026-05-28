# run_dump.ps1 — Wrapper para Windows Task Scheduler
# Ejecuta dump_to_cloud.py --tables-core con el entorno correcto.
# Programar para ejecutarse diariamente a las 02:00 hora COL.

$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\MotoShop\Documents\javidevmoto"
$VenvActivate = "$ProjectRoot\.venv-infra\Scripts\Activate.ps1"
$Script = "$ProjectRoot\infra\dump_to_cloud.py"

# Activar entorno virtual
& $VenvActivate

# Ejecutar dump de las 12 tablas core
python $Script --tables-core

if ($LASTEXITCODE -ne 0) {
    Write-Error "dump_to_cloud.py fallo con exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host "Dump completado exitosamente - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
