# start_tunnel.ps1 — Arranca cloudflared con verificación de errores
$ErrorActionPreference = "Continue"
$ProjectRoot = "C:\Users\MotoShop\Documents\javidevmoto"
$LogDir = "$ProjectRoot\logs"
$Cloudflared = "C:\Users\MotoShop\AppData\Local\Microsoft\WinGet\Links\cloudflared.exe"
$TunnelId = "38e6118f-4d8e-43cb-8990-fa7e71039c12"
$TunnelUrl = if ($env:TUNNEL_URL) { $env:TUNNEL_URL } else { "https://motoshop-local.fragloesja.uk" }

if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$LogFile = "$LogDir\tunnel_start_$(Get-Date -Format 'yyyy-MM-dd_HHmm').log"

function Write-Log($msg) {
    $entry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Write-Host $entry
    Add-Content -Path $LogFile -Value $entry -Encoding utf8
}

Write-Log "=== INICIO VERIFICACION TUNNEL ==="
Write-Log "TunnelUrl: $TunnelUrl"

# 0. Si el túnel está configurado como servicio de Windows, preferir gestión del servicio
$cfService = Get-Service -Name "cloudflared" -ErrorAction SilentlyContinue
if ($cfService) {
    Write-Log "Servicio Windows cloudflared detectado (Estado: $($cfService.Status))"
    if ($cfService.Status -ne "Running") {
        Write-Log "Iniciando servicio Windows cloudflared..."
        Start-Service cloudflared -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 5
    }
    try {
        $resp = Invoke-WebRequest -Uri "$TunnelUrl/health" -TimeoutSec 10 -UseBasicParsing
        if ($resp.StatusCode -eq 200) {
            Write-Log "Túnel vía servicio: OK ($TunnelUrl/health → $($resp.StatusCode))"
            Write-Log "=== FIN ==="
            exit 0
        }
    } catch {
        Write-Log "WARN: Servicio cloudflared corriendo pero túnel no responde. Reiniciando servicio..."
        Restart-Service cloudflared -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 5
        try {
            $resp2 = Invoke-WebRequest -Uri "$TunnelUrl/health" -TimeoutSec 10 -UseBasicParsing
            if ($resp2.StatusCode -eq 200) {
                Write-Log "Túnel vía servicio: REINICIADO OK ($TunnelUrl/health → $($resp2.StatusCode))"
                Write-Log "=== FIN ==="
                exit 0
            }
        } catch {}
    }
}

# 1. Verificar si ya está corriendo (proceso independiente)
$running = Get-Process cloudflared -ErrorAction SilentlyContinue
if ($running) {
    Write-Log "Túnel ya está corriendo (PID: $($running.Id))"
    # Verificar que conecta
    try {
        $resp = Invoke-WebRequest -Uri "$TunnelUrl/health" -TimeoutSec 10 -UseBasicParsing
        if ($resp.StatusCode -eq 200) {
            Write-Log "Túnel: OK ($TunnelUrl/health → $($resp.StatusCode))"
            Write-Log "=== FIN ==="
            exit 0
        }
    } catch {
        Write-Log "WARN: Túnel proceso activo pero no conecta - reiniciando..."
        Stop-Process -Name cloudflared -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
}

# 2. Verificar que el ejecutable existe
if (!(Test-Path $Cloudflared)) {
    Write-Log "ERROR: cloudflared.exe no encontrado en $Cloudflared"
    Write-Log "Solución: Instalar cloudflared con: winget install cloudflare.cloudflared"
    exit 1
}

# 3. Verificar archivo de credenciales
$credFile = "C:\Users\MotoShop\.cloudflared\$TunnelId.json"
if (!(Test-Path $credFile)) {
    Write-Log "ERROR: Archivo de credenciales no encontrado en $credFile"
    Write-Log "Solución: Ejecutar: cloudflared tunnel login"
    exit 1
}

# 4. Arrancar cloudflared
Write-Log "Arrancando túnel $TunnelId..."
$proc = Start-Process -FilePath $Cloudflared `
    -ArgumentList "tunnel","run","$TunnelId" `
    -WindowStyle Hidden -PassThru

Start-Sleep -Seconds 10

# 5. Verificar que conecta
try {
    $resp = Invoke-WebRequest -Uri "$TunnelUrl/health" -TimeoutSec 10 -UseBasicParsing
    if ($resp.StatusCode -eq 200) {
        Write-Log "Túnel: OK ($TunnelUrl/health → $($resp.StatusCode))"
        Write-Log "=== FIN ==="
        exit 0
    }
} catch {
    Write-Log "ERROR: Túnel no conecta después de 10s"
    Write-Log "Causa: cloudflared puede haber fallado al conectar"
    Write-Log "Solución: Verificar que el túnel está configurado con: cloudflared tunnel list"
    exit 1
}
