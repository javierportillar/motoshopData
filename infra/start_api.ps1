# start_api.ps1 — Arranca uvicorn con verificación de errores
$ErrorActionPreference = "Continue"
$ProjectRoot = "C:\Users\MotoShop\Documents\javidevmoto"
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

# 1. Verificar si ya está corriendo
$listening = netstat -ano 2>$null | Select-String ":$Port.*LISTENING"
if ($listening) {
    Write-Log "API ya está corriendo en puerto $Port"
    Write-Log "=== FIN ==="
    exit 0
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
# Leer secretos desde .env (¡NUNCA hardcodear!)
$env:JWT_SECRET = (Get-Content "$ApiDir\.env" | Where-Object {$_ -match '^JWT_SECRET=(.+)$'} | ForEach-Object {$matches[1]})
if (-not $env:JWT_SECRET) { Write-Log "ERROR: JWT_SECRET no encontrada en $ApiDir\.env"; exit 1 }

$env:ENV = "dev"
$env:MYSQL_HOST = "localhost"
$env:MYSQL_PORT = "3306"
$env:MYSQL_DATABASE = "motoshop2024"
$env:MYSQL_USER = "api_read"

$env:MYSQL_PASSWORD = (Get-Content "$ApiDir\.env" | Where-Object {$_ -match '^MYSQL_PASSWORD=(.+)$'} | ForEach-Object {$matches[1]})
if (-not $env:MYSQL_PASSWORD) { Write-Log "ERROR: MYSQL_PASSWORD no encontrada en $ApiDir\.env"; exit 1 }

$env:MYSQL_APP_WRITER_USER = "app_writer"

$env:MYSQL_APP_WRITER_PASSWORD = (Get-Content "$ApiDir\.env" | Where-Object {$_ -match '^MYSQL_APP_WRITER_PASSWORD=(.+)$'} | ForEach-Object {$matches[1]})
if (-not $env:MYSQL_APP_WRITER_PASSWORD) { Write-Log "ERROR: MYSQL_APP_WRITER_PASSWORD no encontrada en $ApiDir\.env"; exit 1 }
$env:CORS_ORIGINS = "http://localhost:3000,https://api.fragloesja.uk,https://motoshop-web-tau.vercel.app,https://app.fragloesja.uk,http://localhost:8000"

# Databricks (Track A) — leer del .env de la API
$env:DATABRICKS_HOST = (Get-Content "$ApiDir\.env" | Where-Object {$_ -match '^DATABRICKS_HOST=(.+)$'} | ForEach-Object {$matches[1]})
$env:DATABRICKS_TOKEN = (Get-Content "$ApiDir\.env" | Where-Object {$_ -match '^DATABRICKS_TOKEN=(.+)$'} | ForEach-Object {$matches[1]})
$env:DATABRICKS_HTTP_PATH = (Get-Content "$ApiDir\.env" | Where-Object {$_ -match '^DATABRICKS_HTTP_PATH=(.+)$'} | ForEach-Object {$matches[1]})

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
