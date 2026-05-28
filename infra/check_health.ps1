# check_health.ps1 — Health check periódico con auto-reinicio
$ErrorActionPreference = "Continue"
$ProjectRoot = "C:\Users\MotoShop\Documents\javidevmoto"
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
    $env:MYSQL_PWD = "Sashita123"
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
try {
    $resp = Invoke-WebRequest -Uri "https://api.fragloesja.uk/health" -TimeoutSec 10 -UseBasicParsing
    if ($resp.StatusCode -eq 200) {
        Write-Log "  Túnel: OK"
    } else {
        Write-Log "  Túnel: ERROR - Status $($resp.StatusCode)"
        $issues += "Túnel respondió con status $($resp.StatusCode)"
    }
} catch {
    Write-Log "  Túnel: CAIDO - Intentando reiniciar..."
    & "$ProjectRoot\infra\start_tunnel.ps1"
    Start-Sleep -Seconds 10
    try {
        $resp2 = Invoke-WebRequest -Uri "https://api.fragloesja.uk/health" -TimeoutSec 10 -UseBasicParsing
        if ($resp2.StatusCode -eq 200) {
            Write-Log "  Túnel: REINICIADO OK"
        } else {
            Write-Log "  Túnel: ERROR después de reinicio"
            $issues += "Túnel no se pudo reiniciar"
        }
    } catch {
        Write-Log "  Túnel: ERROR - No se pudo reiniciar"
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
