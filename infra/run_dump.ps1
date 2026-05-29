# run_dump.ps1 — Wrapper para Windows Task Scheduler
# Ejecuta dump_to_cloud.py --tables-core --catch-up con logging.
# Programado: cada 30 min en ventana 07:00–19:30

$ErrorActionPreference = "Continue"

$ProjectRoot = "C:\Users\MotoShop\Documents\javidevmoto"
$VenvActivate = "$ProjectRoot\.venv-infra\Scripts\Activate.ps1"
$Script = "$ProjectRoot\infra\dump_to_cloud.py"
$LogDir = "$ProjectRoot\logs"

if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

$Timestamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$LogFile = "$LogDir\dump_$Timestamp.log"

$StartTime = Get-Date
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') === INICIO DUMP ===" | Out-File -FilePath $LogFile -Encoding utf8

& $VenvActivate
$process = Start-Process -FilePath "python" -ArgumentList "$Script --tables-core --catch-up" -NoNewWindow -PassThru -Wait -RedirectStandardOutput "$LogDir\dump_stdout_$Timestamp.txt" -RedirectStandardError "$LogDir\dump_stderr_$Timestamp.txt"

$ExitCode = $process.ExitCode
$Duration = (Get-Date) - $StartTime

# Combinar stdout y stderr en el log
if (Test-Path "$LogDir\dump_stdout_$Timestamp.txt") {
    Get-Content "$LogDir\dump_stdout_$Timestamp.txt" | Out-File -FilePath $LogFile -Append -Encoding utf8
}
if (Test-Path "$LogDir\dump_stderr_$Timestamp.txt") {
    Get-Content "$LogDir\dump_stderr_$Timestamp.txt" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') === DUMP FINALIZADO === ExitCode: $ExitCode Duracion: $($Duration.TotalSeconds.ToString('F1'))s" | Out-File -FilePath $LogFile -Append -Encoding utf8

# Limpiar archivos temporales
Remove-Item "$LogDir\dump_stdout_$Timestamp.txt" -Force -ErrorAction SilentlyContinue
Remove-Item "$LogDir\dump_stderr_$Timestamp.txt" -Force -ErrorAction SilentlyContinue

if ($ExitCode -ne 0) {
    Write-Host "ERROR: dump_to_cloud.py fallo con exit code $ExitCode. Ver log: $LogFile"
    exit $ExitCode
}

Write-Host "Dump OK - $($Duration.TotalSeconds.ToString('F1'))s - Log: $LogFile"
