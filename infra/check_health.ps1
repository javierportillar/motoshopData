# check_health.ps1 — Health check periódico con auto-reinicio
$ErrorActionPreference = "Continue"
# Detección dinámica y robusta de la raíz del proyecto
$candidateRoots = @(
    (Resolve-Path "$PSScriptRoot\..").Path,
    "C:\Users\MotoShop\Documents\javidevmoto",
    "C:\Users\MotoShop\Documents\javidevmoto\motoshopData"
)
$ProjectRoot = $null
foreach ($cand in $candidateRoots) {
    if (Test-Path "$cand\motoshop-app\api") {
        $ProjectRoot = $cand
        break
    }
}
if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
}
$LogDir = "$ProjectRoot\logs"

if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$LogFile = "$LogDir\health_$(Get-Date -Format 'yyyy-MM-dd_HHmm').log"

function Write-Log($msg) {
    $entry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $LogFile -Value $entry -Encoding utf8
}

$issues = @()

# 1. Verificar MySQL
Write-Log "MySQL..."
try {
    $env:MYSQL_PWD = (Get-Content "$ProjectRoot\.env" | Where-Object {$_ -match '^MYSQL_ROOT_PASSWORD=(.+)$'} | ForEach-Object {$matches[1]})
    if (-not $env:MYSQL_PWD) {
        Write-Log "  MySQL: ERROR - MYSQL_ROOT_PASSWORD no encontrada en .env"
        $issues += "MYSQL_ROOT_PASSWORD no configurada en .env"
    }
    $result = & "C:\Program Files (x86)\MySQL\MySQL Server 5.0\bin\mysqladmin.exe" ping -u root 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Log "  MySQL: OK"
    } else {
        Write-Log "  MySQL: ERROR - No responde"
        $issues += "MySQL caído (reiniciar servicio)"
    }
} catch {
    Write-Log "  MySQL: ERROR - $($_.Exception.Message)"
    $issues += "MySQL caído"
}

# 2. Verificar API
Write-Log "API..."
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 5 -UseBasicParsing
    if ($resp.StatusCode -eq 200) {
        Write-Log "  API: OK"
    } else {
        Write-Log "  API: ERROR - Status $($resp.StatusCode)"
        $issues += "API respondió con status $($resp.StatusCode)"
    }
} catch {
    Write-Log "  API: CAIDA - Intentando reiniciar..."
    & "$ProjectRoot\infra\start_api.ps1"
    Start-Sleep -Seconds 5
    try {
        $resp2 = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 5 -UseBasicParsing
        if ($resp2.StatusCode -eq 200) {
            Write-Log "  API: REINICIADA OK"
        } else {
            Write-Log "  API: ERROR después de reinicio"
            $issues += "API no se pudo reiniciar"
        }
    } catch {
        Write-Log "  API: ERROR - No se pudo reiniciar"
        $issues += "API no se pudo reiniciar"
    }
}

# 3. Verificar Túnel
Write-Log "Túnel..."
$tunnelUrl = if ($env:TUNNEL_URL) { $env:TUNNEL_URL } else { "https://motoshop-local.fragloesja.uk/health" }
try {
    $resp = Invoke-WebRequest -Uri $tunnelUrl -TimeoutSec 10 -UseBasicParsing
    if ($resp.StatusCode -eq 200) {
        Write-Log "  Túnel: OK ($tunnelUrl)"
    } else {
        Write-Log "  Túnel: ERROR - Status $($resp.StatusCode)"
        $issues += "Túnel respondió con status $($resp.StatusCode)"
    }
} catch {
    Write-Log "  Túnel: CAIDO ($tunnelUrl) - Recuperando via task MotoShopTunnelSvc..."
    $cfTask = Get-ScheduledTask -TaskName "MotoShopTunnelSvc" -ErrorAction SilentlyContinue
    if ($cfTask) {
        try {
            Stop-ScheduledTask -TaskName "MotoShopTunnelSvc" -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
            Start-ScheduledTask -TaskName "MotoShopTunnelSvc" -ErrorAction Stop
            Write-Log "  Task MotoShopTunnelSvc reiniciada."
        } catch {
            Write-Log "  Reinicio de task fallo: $($_.Exception.Message)"
            & "$ProjectRoot\infra\start_tunnel.ps1"
        }
    } else {
        & "$ProjectRoot\infra\start_tunnel.ps1"
    }
    Start-Sleep -Seconds 10
    try {
        $resp2 = Invoke-WebRequest -Uri $tunnelUrl -TimeoutSec 10 -UseBasicParsing
        if ($resp2.StatusCode -eq 200) {
            Write-Log "  Túnel: REINICIADO OK"
        } else {
            Write-Log "  Túnel: ERROR después de reinicio (Status $($resp2.StatusCode))"
            $issues += "Túnel no se pudo reiniciar"
        }
    } catch {
        Write-Log "  Túnel: ERROR - No se pudo reiniciar ($($_.Exception.Message))"
        $issues += "Túnel no se pudo reiniciar"
    }
}

# 4. Resumen
Write-Log "----------------------------------------"
if ($issues.Count -eq 0) {
    Write-Log "ESTADO: OK (3/3 componentes activos)"
} else {
    Write-Log "ESTADO: PROBLEMAS ($($issues.Count) problema(s))"
    foreach ($issue in $issues) {
        Write-Log "  - $issue"
    }
}
Write-Log "----------------------------------------"
