# start_tunnel.ps1 — Arranca cloudflared con verificación de errores
$ErrorActionPreference = "Continue"
$ProjectRoot = "C:\Users\MotoShop\Documents\javidevmoto"
$LogDir = "$ProjectRoot\logs"
$Cloudflared = "C:\Users\MotoShop\.cloudflared\cloudflared.exe"
$TunnelId = "38e6118f-4d8e-43cb-8990-fa7e71039c12"
$TunnelUrl = "https://api.fragloesja.uk"

if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$LogFile = "$LogDir\tunnel_start_$(Get-Date -Format 'yyyy-MM-dd_HHmm').log"

function Write-Log($msg) {
    $entry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Write-Host $entry
    Add-Content -Path $LogFile -Value $entry -Encoding utf8
}

Write-Log "=== INICIO VERIFICACION TUNNEL ==="

# 1. Verificar si ya está corriendo
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
    -NoNewWindow -PassThru

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
