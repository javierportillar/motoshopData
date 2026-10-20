# start_tunnel.ps1 — Asegura el túnel Cloudflare (motoshop-local)
# El túnel corre como scheduled task SYSTEM "MotoShopTunnelSvc"; este script
# verifica salud y, si hace falta, reinicia la task (preferido) o arranca
# cloudflared directo con config.yml (fallback).
$ErrorActionPreference = "Continue"

# Raíz del proyecto (detección dinámica y robusta)
$candidateRoots = @(
    (Resolve-Path "$PSScriptRoot\..").Path,
    "C:\Users\MotoShop\Documents\javidevmoto\motoshopData",
    "C:\Users\MotoShop\Documents\javidevmoto"
)
$ProjectRoot = $null
foreach ($cand in $candidateRoots) {
    if (Test-Path "$cand\motoshop-app\api") { $ProjectRoot = $cand; break }
}
if (-not $ProjectRoot) { $ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path }
$LogDir = "$ProjectRoot\logs"

$Cloudflared = "C:\Users\MotoShop\AppData\Local\Microsoft\WinGet\Links\cloudflared.exe"
$TunnelId    = "91f4b0e5-0a78-4789-9185-2f4d2a7c1098"
$ConfigFile  = "C:\Users\MotoShop\.cloudflared\config.yml"
$TaskName    = "MotoShopTunnelSvc"
$TunnelUrl   = if ($env:TUNNEL_URL) { $env:TUNNEL_URL } else { "https://motoshop-local.fragloesja.uk" }

if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$LogFile = "$LogDir\tunnel_start_$(Get-Date -Format 'yyyy-MM-dd_HHmm').log"

function Write-Log($msg) {
    $entry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $LogFile -Value $entry -Encoding utf8
}

function Test-Tunnel {
    try {
        $resp = Invoke-WebRequest -Uri "$TunnelUrl/health" -TimeoutSec 10 -UseBasicParsing
        return ($resp.StatusCode -eq 200)
    } catch { return $false }
}

Write-Log "=== INICIO VERIFICACION TUNNEL ==="
Write-Log "TunnelUrl: $TunnelUrl"

# 0. Si ya responde, no tocar nada
if (Test-Tunnel) {
    Write-Log "Túnel: OK ($TunnelUrl/health)"
    Write-Log "=== FIN ==="
    exit 0
}

# 1. Preferido: reiniciar la scheduled task SYSTEM que realmente corre el túnel
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    Write-Log "Task '$TaskName' detectada (Estado: $($task.State)). Reiniciando..."
    try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue } catch {}
    Start-Sleep -Seconds 2
    try { Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop } catch { Write-Log "WARN: Start-ScheduledTask fallo: $($_.Exception.Message)" }
    for ($i = 1; $i -le 12; $i++) {
        Start-Sleep -Seconds 3
        if (Test-Tunnel) { Write-Log "Túnel: OK via task (intento $i)"; Write-Log "=== FIN ==="; exit 0 }
    }
    Write-Log "WARN: task reiniciada pero el túnel no responde; probando fallback"
}

# 2. Fallback: arrancar cloudflared directo con config.yml
if (!(Test-Path $Cloudflared)) { Write-Log "ERROR: cloudflared.exe no encontrado en $Cloudflared"; exit 1 }
if (!(Test-Path $ConfigFile))  { Write-Log "ERROR: config.yml no encontrado en $ConfigFile"; exit 1 }
Write-Log "Arrancando cloudflared (config: $ConfigFile, tunnel: $TunnelId)..."
Start-Process -FilePath $Cloudflared `
    -ArgumentList "tunnel","--config","$ConfigFile","run","$TunnelId" `
    -WindowStyle Hidden
for ($i = 1; $i -le 12; $i++) {
    Start-Sleep -Seconds 3
    if (Test-Tunnel) { Write-Log "Túnel: OK (intento $i)"; Write-Log "=== FIN ==="; exit 0 }
}
Write-Log "ERROR: Túnel no conecta"
exit 1
