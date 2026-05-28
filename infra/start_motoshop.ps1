# start_motoshop.ps1 — Script maestro: arranca API + Túnel + verifica todo
$ErrorActionPreference = "Continue"
$ProjectRoot = "C:\Users\MotoShop\Documents\javidevmoto"
$LogDir = "$ProjectRoot\logs"

if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$LogFile = "$LogDir\motoshop_start_$(Get-Date -Format 'yyyy-MM-dd_HHmm').log"

function Write-Log($msg) {
    $entry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Write-Host $entry
    Add-Content -Path $LogFile -Value $entry -Encoding utf8
}

Write-Log "========================================"
Write-Log "  MOTOSHOP - ARRANQUE COMPLETO"
Write-Log "========================================"

# 1. Verificar MySQL
Write-Log ""
Write-Log "--- Verificando MySQL ---"
try {
    $env:MYSQL_PWD = "Sashita123"
    $result = & "C:\Program Files (x86)\MySQL\MySQL Server 5.0\bin\mysqladmin.exe" ping -u root 2>&1
    if ($LASTEXITCODE -eq 0) {
        $mysqlStatus = "OK"
        Write-Log "MySQL: OK"
    } else {
        $mysqlStatus = "ERROR"
        Write-Log "MySQL: ERROR - No responde"
        Write-Log "  Causa: Servicio MySQL detenido"
        Write-Log "  Solucion: Abrir services.msc → MySQL → Iniciar"
    }
} catch {
    $mysqlStatus = "ERROR"
    Write-Log "MySQL: ERROR - $($_.Exception.Message)"
}

# 2. Arrancar API
Write-Log ""
Write-Log "--- Arrancando API ---"
& "$ProjectRoot\infra\start_api.ps1"
$apiExitCode = $LASTEXITCODE
if ($apiExitCode -eq 0) {
    $apiStatus = "OK"
} else {
    $apiStatus = "ERROR"
}

# 3. Arrancar Túnel
Write-Log ""
Write-Log "--- Arrancando Túnel ---"
& "$ProjectRoot\infra\start_tunnel.ps1"
$tunnelExitCode = $LASTEXITCODE
if ($tunnelExitCode -eq 0) {
    $tunnelStatus = "OK"
} else {
    $tunnelStatus = "ERROR"
}

# 4. Resumen final
Write-Log ""
Write-Log "========================================"
Write-Log "  ESTADO FINAL"
Write-Log "========================================"
Write-Log "  MySQL:    $mysqlStatus"
Write-Log "  API:      $apiStatus"
Write-Log "  Túnel:    $tunnelStatus"
Write-Log "========================================"

# 5. Determinar exit code general
if ($mysqlStatus -eq "OK" -and $apiStatus -eq "OK" -and $tunnelStatus -eq "OK") {
    Write-Log "Todos los componentes OK"
    exit 0
} elseif ($mysqlStatus -eq "ERROR" -or $apiStatus -eq "ERROR") {
    Write-Log "ERROR FATAL: MySQL o API no funcionan"
    exit 1
} else {
    Write-Log "WARN: Túnel no funciona pero API y MySQL OK"
    exit 0
}
