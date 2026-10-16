# start_api.ps1 — Arranca uvicorn con verificación de errores
$ErrorActionPreference = "Continue"
$ProjectRoot = "C:\Users\MotoShop\Documents\javidevmoto\motoshopData"
$ApiDir = "$ProjectRoot\motoshop-app\api"
$LogDir = "$ProjectRoot\logs"
$Port = 8000

if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$LogFile = "$LogDir\api_start_$(Get-Date -Format 'yyyy-MM-dd_HHmm').log"

function Write-Log($msg) {
    $entry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Write-Host $entry
    Add-Content -Path $LogFile -Value $entry -Encoding utf8
}

Write-Log "=== INICIO VERIFICACION API ==="

# 1. Matar instancia previa si está corriendo (permite deploy sin restart manual)
$apiProcs = Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    try {
        $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
        $cmdLine -match "uvicorn|motoshop_api"
    } catch { $false }
}
if ($apiProcs) {
    $apiProcs | ForEach-Object {
        Write-Log "Deteniendo uvicorn PID $($_.Id)"
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 3
    Write-Log "Proceso anterior detenido."
}

# 2. Verificar MySQL
Write-Log "Verificando MySQL..."
try {
    $result = & "C:\Program Files (x86)\MySQL\MySQL Server 5.0\bin\mysqladmin.exe" ping -u root 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Log "MySQL: OK"
    } else {
        Write-Log "ERROR: MySQL no responde en localhost:3306"
        Write-Log "Solución: Abrir services.msc → MySQL → Iniciar"
        exit 1
    }
} catch {
    Write-Log "ERROR: No se pudo verificar MySQL - $($_.Exception.Message)"
    exit 1
}

# 3. Verificar .env
Write-Log "Verificando .env..."
if (!(Test-Path "$ApiDir\.env")) {
    Write-Log "ERROR: .env no encontrado en $ApiDir\.env"
    Write-Log "Solución: Crear archivo .env con las variables de entorno"
    exit 1
}
Write-Log ".env: OK"

# 4. Arrancar uvicorn
Write-Log "Arrancando uvicorn en puerto $Port..."

# Cargar todas las variables desde .env (ProjectRoot y ApiDir)
$envFiles = @("$ProjectRoot\.env", "$ApiDir\.env")
foreach ($ef in $envFiles) {
    if (Test-Path $ef) {
        Get-Content $ef | ForEach-Object {
            if ($_ -match "^\s*([^#=]+)=(.*)$") {
                $k = $matches[1].Trim()
                $v = $matches[2].Trim('"', "'")
                Set-Item -Path "env:$k" -Value $v -ErrorAction SilentlyContinue
            }
        }
    }
}

if (-not $env:JWT_SECRET) {
    Write-Log "ERROR: JWT_SECRET no encontrada en archivos .env"
    exit 1
}

# Defaults operativos si no vienen en .env
if (-not $env:ENV) { $env:ENV = "dev" }
if (-not $env:MYSQL_HOST) { $env:MYSQL_HOST = "localhost" }
if (-not $env:MYSQL_PORT) { $env:MYSQL_PORT = "3306" }
if (-not $env:MYSQL_DATABASE) { $env:MYSQL_DATABASE = "motoshop2024" }
if (-not $env:MYSQL_USER) { $env:MYSQL_USER = "api_read" }
if (-not $env:CORS_ORIGINS) {
    $env:CORS_ORIGINS = "http://localhost:3000,https://api.fragloesja.uk,https://motoshop-web-tau.vercel.app,https://app.fragloesja.uk,http://localhost:8000"
}
if (-not $env:DUCKDB_PATH) {
    $env:DUCKDB_PATH = "$ProjectRoot\out\motoshop_gold.duckdb"
}

$proc = Start-Process -FilePath "$ApiDir\.venv\Scripts\python.exe" `
    -ArgumentList "-m","uvicorn","motoshop_api.main:app","--port","$Port" `
    -WindowStyle Hidden -PassThru -WorkingDirectory $ApiDir

Start-Sleep -Seconds 5

# 5. Verificar que responde
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:$Port/health" -TimeoutSec 5 -UseBasicParsing
    if ($resp.StatusCode -eq 200) {
        Write-Log "API: OK (http://localhost:$Port/health → $($resp.StatusCode))"
        Write-Log "=== FIN ==="
        exit 0
    }
} catch {
    Write-Log "ERROR: API no responde en /health después de 5s"
    Write-Log "Causa: uvicorn puede haber fallado al iniciar"
    Write-Log "Solución: Revisar logs de uvicorn o ejecutar manualmente: cd $ApiDir && python -m uvicorn motoshop_api.main:app --port $Port"
    exit 1
}
