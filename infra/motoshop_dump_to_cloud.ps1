<#
.SYNOPSIS
  Dump MySQL → Parquet → UC Volume Databricks.
  Alias: motoshop_dump_to_cloud (Windows Scheduled Task).
  Naming alineado con los jobs de Databricks: motoshop_bronze_silver, motoshop_gold_workflow.

.DESCRIPTION
  Ejecuta dump_to_cloud.py --tables-core --catch-up con logging.
  Programado en Windows Task Scheduler cada 30 min en ventana 07:00–19:30.
  El PC debe estar encendido para que el dump corra; los datos se persisten
  en el Volume y el job bronze los consume a las 02:30 COL del día siguiente.

.NOTES
  Windows Task Scheduler → nombre: "motoshop_dump_to_cloud"
  Trigger: cada 30 minutos, 07:00 a 19:30, todos los días (lun-vie recomendado).
  Acción: powershell.exe -File "C:\Users\MotoShop\Documents\javidevmoto\infra\motoshop_dump_to_cloud.ps1"

  Ver también: infra/dump_to_cloud.py, infra/create_gold_workflow.py
#>

$ErrorActionPreference = "Continue"

$ProjectRoot = "C:\Users\MotoShop\Documents\javidevmoto"
$VenvActivate = "$ProjectRoot\.venv-infra\Scripts\Activate.ps1"
$Script = "$ProjectRoot\infra\dump_to_cloud.py"
$LogDir = "$ProjectRoot\logs"

if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-File $null }

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
