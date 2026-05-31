<#
.SYNOPSIS
  Shutdown hook: send last MySQL dump to Databricks before PC turns off.

.DESCRIPTION
  Triggered by MotoShop_ShutdownSend (Scheduled Task, EventID 1074 User32)
  on system shutdown/restart. Calls dump_to_cloud.py --tables-core to upload
  the latest sgHermes data to UC Volume before the PC powers off.

  If the virtualenv is missing or the dump fails, it aborts quickly (<5s)
  so the shutdown is not delayed unnecessarily.

.NOTES
  Task: MotoShop_ShutdownSend
  Log:  logs/shutdown_dump.log
  Lock: logs/shutdown_dump.lock (short-lived)
#>

$ErrorActionPreference = "Continue"

$RepoRoot    = "C:\Users\MotoShop\Documents\javidevmoto"
$LockFile    = "$RepoRoot\logs\shutdown_dump.lock"
$LogFile     = "$RepoRoot\logs\shutdown_dump.log"
$VenvActivate = "$RepoRoot\.venv-infra\Scripts\Activate.ps1"
$DumpScript  = "$RepoRoot\infra\dump_to_cloud.py"

$LogDir = Split-Path $LogFile -Parent
if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

function Log {
    param([string]$Msg)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Value "[$ts] $Msg" -Encoding UTF8
}

# Lock: prevent concurrent runs
if (Test-Path $LockFile) {
    Log "LOCKED: otro shutdown dump en progreso, abortando"
    exit 0
}
try { Set-Content -Path $LockFile -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -Encoding UTF8 } catch {}

$start = Get-Date
Log "=== SHUTDOWN DUMP START ==="

# Virtualenv guard
if (!(Test-Path $VenvActivate)) {
    Log "WARN: .venv-infra no encontrado en $VenvActivate, abortando"
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
    exit 0
}

& $VenvActivate

$tmpStdout = "$LogDir\_shutdown_stdout.txt"
$tmpStderr = "$LogDir\_shutdown_stderr.txt"
$proc = Start-Process -FilePath "python" -ArgumentList "$DumpScript --tables-core" -NoNewWindow -PassThru -Wait `
    -RedirectStandardOutput $tmpStdout -RedirectStandardError $tmpStderr
$exitCode = $proc.ExitCode
$duration = (Get-Date) - $start

if (Test-Path $tmpStdout) {
    Get-Content $tmpStdout | ForEach-Object { Log "OUT: $_" }
    Remove-Item $tmpStdout -Force -ErrorAction SilentlyContinue
}
if (Test-Path $tmpStderr) {
    Get-Content $tmpStderr | ForEach-Object { Log "ERR: $_" }
    Remove-Item $tmpStderr -Force -ErrorAction SilentlyContinue
}

if ($exitCode -eq 0) {
    Log "OK: shutdown dump completed in $($duration.TotalSeconds.ToString('F1'))s"
} else {
    Log "FAIL: exit code $exitCode after $($duration.TotalSeconds.ToString('F1'))s"
}
Log "=== SHUTDOWN DUMP END ==="

Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
