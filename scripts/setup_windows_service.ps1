# ═══════════════════════════════════════════════════════════════════════════
# Setup Background Windows Service (Zero Window / Auto-Start on Boot)
# MotoShop & MasVital Emergency Contingency Backend + Cloudflare Tunnel
# ═══════════════════════════════════════════════════════════════════════════
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, HelpMessage = "Token del túnel de Cloudflare")]
    [string]$TunnelToken,

    [string]$ServiceName = "MotoShopBackendService"
)

# 1. Verificar privilegios de Administrador
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "ERROR: Este script debe ejecutarse en una ventana de PowerShell como Administrador."
    exit 1
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$apiDir = Join-Path $repoRoot "motoshop-app\api"
$logDir = Join-Path $apiDir "out"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

Write-Host "==> Actualizando repositorio con git pull..." -ForegroundColor Cyan
Set-Location $repoRoot
try {
    git fetch origin main
    git pull origin main
} catch {
    Write-Warning "No se pudo hacer git pull. Continuando con los archivos locales..."
}

# 2. Localizar Python y pythonw (sin consola)
$pythonExe = $null
$pythonwExe = $null

$venvPython = Join-Path $apiDir ".venv\Scripts\python.exe"
$venvPythonw = Join-Path $apiDir ".venv\Scripts\pythonw.exe"

if (Test-Path $venvPython) {
    $pythonExe = $venvPython
    $pythonwExe = $venvPythonw
} else {
    $cmdPython = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmdPython) {
        $pythonExe = $cmdPython.Source
        $pythonDir = Split-Path -Parent $pythonExe
        $potentialPythonw = Join-Path $pythonDir "pythonw.exe"
        if (Test-Path $potentialPythonw) {
            $pythonwExe = $potentialPythonw
        } else {
            $pythonwExe = $pythonExe
        }
    }
}

if (-not $pythonExe) {
    Write-Error "ERROR: No se encontró Python instalado ni el .venv en $apiDir."
    exit 1
}

Write-Host "==> Python detectado: $pythonExe" -ForegroundColor Green
Write-Host "==> Pythonw (silencioso): $pythonwExe" -ForegroundColor Green

# 3. Configurar Backend como Servicio o Tarea Oculta (0 ventanas, inicio en arranque)
$nssmCmd = Get-Command nssm.exe -ErrorAction SilentlyContinue
if (-not $nssmCmd) {
    Write-Host "==> Intentando instalar NSSM para gestión de servicio..." -ForegroundColor Cyan
    winget install -e --id NSSM.NSSM --silent --accept-source-agreements --accept-package-agreements 2>$null
    $nssmCmd = Get-Command nssm.exe -ErrorAction SilentlyContinue
}

if ($nssmCmd) {
    Write-Host "==> Registrando servicio de Windows con NSSM: $ServiceName" -ForegroundColor Cyan
    & nssm stop $ServiceName 2>$null
    & nssm remove $ServiceName confirm 2>$null

    & nssm install $ServiceName "$pythonExe" "-m uvicorn motoshop_api.main:app --host 0.0.0.0 --port 8000"
    & nssm set $ServiceName AppDirectory "$apiDir"
    & nssm set $ServiceName AppStdout "$logDir\backend_service.log"
    & nssm set $ServiceName AppStderr "$logDir\backend_service.log"
    & nssm set $ServiceName AppRotateFiles 1
    & nssm set $ServiceName AppRotateBytes 5242880 # 5 MB rotación
    & nssm set $ServiceName Start SERVICE_AUTO_START
    & nssm start $ServiceName
} else {
    Write-Host "==> Configurando Tarea Oculta de Inicio de Windows (Task Scheduler)..." -ForegroundColor Cyan
    $taskName = $ServiceName
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

    $action = New-ScheduledTaskAction -Execute "$pythonwExe" -Argument "-m uvicorn motoshop_api.main:app --host 0.0.0.0 --port 8000" -WorkingDirectory "$apiDir"
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit 0

    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
    Start-ScheduledTask -TaskName $taskName
}

# 4. Configurar Cloudflare Tunnel como Servicio de Windows (Silencioso)
$cfCmd = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
if (-not $cfCmd) {
    Write-Host "==> Instalando cloudflared vía winget..." -ForegroundColor Cyan
    winget install -e --id Cloudflare.cloudflared --silent --accept-source-agreements --accept-package-agreements 2>$null
    $cfCmd = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
}

if (-not $cfCmd) {
    Write-Warning "No se encontró cloudflared.exe. Por favor descárgalo o instálalo."
} else {
    Write-Host "==> Instalando Cloudflare Tunnel como servicio de Windows..." -ForegroundColor Cyan
    Stop-Service cloudflared -ErrorAction SilentlyContinue
    & cloudflared.exe service uninstall 2>$null
    & cloudflared.exe service install $TunnelToken
    Start-Service cloudflared -ErrorAction SilentlyContinue
}

# 5. Autovalidación en local
Write-Host "==> Esperando 5 segundos para autoverificación..." -ForegroundColor Cyan
Start-Sleep -Seconds 5

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get -TimeoutSec 5
    if ($health.status -eq "ok") {
        Write-Host ""
        Write-Host "==========================================================================" -ForegroundColor Green
        Write-Host " [SUCCESS] Backend local y Túnel configurados como SERVICIOS DE WINDOWS." -ForegroundColor Green
        Write-Host " - Ejecución 100% en segundo plano (CERO ventanas, cero popups)." -ForegroundColor Green
        Write-Host " - Inicio automático con el arranque de la PC (sin necesidad de logueo)." -ForegroundColor Green
        Write-Host " - Auto-reinicio inmediato en caso de fallo." -ForegroundColor Green
        Write-Host "==========================================================================" -ForegroundColor Green
        exit 0
    }
} catch {
    Write-Error "El backend aún no responde en http://127.0.0.1:8000/health. Revisa el log en $logDir\backend_service.log."
    exit 1
}
