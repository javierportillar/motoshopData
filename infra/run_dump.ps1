# run_dump.ps1 — Wrapper para Windows Task Scheduler
# Ejecuta dump_to_cloud.py --tables-core con logging.
# Programado: 12:00 PM, 8:00 PM, 2:00 AM (hora COL)

$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\MotoShop\Documents\javidevmoto"
$VenvActivate = "$ProjectRoot\.venv-infra\Scripts\Activate.ps1"
$Script = "$ProjectRoot\infra\dump_to_cloud.py"
$LogDir = "$ProjectRoot\logs"

# Crear directorio de logs si no existe
if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

$Timestamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$LogFile = "$LogDir\dump_$Timestamp.log"

function Write-Log {
    param([string]$Message)
    $entry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Write-Host $entry
    Add-Content -Path $LogFile -Value $entry
}

Write-Log "=== INICIO DUMP ==="
$StartTime = Get-Date

try {
    & $VenvActivate
    python $Script --tables-core 2>&1 | ForEach-Object { Write-Log $_ }

    if ($LASTEXITCODE -ne 0) {
        Write-Log "ERROR: dump_to_cloud.py fallo con exit code $LASTEXITCODE"
        exit $LASTEXITCODE
    }

    $Duration = (Get-Date) - $StartTime
    Write-Log "=== DUMP OK === Duracion: $($Duration.TotalSeconds.ToString('F1'))s"
} catch {
    Write-Log "EXCEPTION: $_"
    exit 1
}
