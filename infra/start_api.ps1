# start_api.ps1 — Arranca uvicorn con verificación de errores
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
Write-Log "ProjectRoot: $ProjectRoot"
Write-Log "ApiDir: $ApiDir"

# 1. Matar instancia previa si está corriendo (por puerto y por proceso)
try {
    $portPids = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    if ($portPids) {
        foreach ($p in $portPids) {
            Write-Log "Deteniendo proceso en puerto $Port (PID $p)"
            Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        }
    }
} catch {}
try {
    netstat -ano | Select-String ":$Port\s+.*LISTENING" | ForEach-Object {
        if ($_ -match "(\d+)$") {
            $nsPid = $matches[1]
            Write-Log "Deteniendo netstat PID $nsPid"
            Stop-Process -Id $nsPid -Force -ErrorAction SilentlyContinue
        }
    }
} catch {}

$apiProcs = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "uvicorn|motoshop_api|api_launcher" })
if ($apiProcs.Count -gt 0) {
    $apiProcs | ForEach-Object {
        Write-Log "Deteniendo API PID $($_.ProcessId) ($($_.Name))"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
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
$envFiles = @(
    "$ApiDir\.env",
    "$ProjectRoot\.env",
    "$ProjectRoot\..\.env"
)
$envFound = $false
foreach ($ef in $envFiles) {
    if (Test-Path $ef) {
        $envFound = $true
        Write-Log "Cargando $ef..."
        Get-Content $ef | ForEach-Object {
            if ($_ -match "^\s*([^#=]+)=(.*)$") {
                $k = $matches[1].Trim()
                $v = $matches[2].Trim('"', "'")
                # Solo setear si el valor no es vacío o si no existe en el environment
                if ($v -ne "" -or -not (Test-Path "env:$k")) {
                    Set-Item -Path "env:$k" -Value $v -ErrorAction SilentlyContinue
                }
            }
        }
    }
}

if (-not $envFound) {
    Write-Log "ERROR: .env no encontrado en ninguna ruta candidata"
    exit 1
}
Write-Log ".env: OK"

# 4. Arrancar uvicorn
Write-Log "Arrancando uvicorn en puerto $Port..."

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
if (-not $env:OPENCODE_API_KEY -and $env:SUPABASE_URL -and $env:SUPABASE_SERVICE_KEY) {
    try {
        $headers = @{
            "apikey" = $env:SUPABASE_SERVICE_KEY
            "Authorization" = "Bearer $($env:SUPABASE_SERVICE_KEY)"
        }
        $resp = Invoke-RestMethod -Uri "$($env:SUPABASE_URL)/rest/v1/app_users?username=eq._system_config&select=allowed_modules" -Headers $headers -Method Get -TimeoutSec 5
        if ($resp -and $resp[0].allowed_modules) {
            foreach ($item in $resp[0].allowed_modules) {
                if ($item -match "^\s*([^=]+)=(.*)$") {
                    $k = $matches[1].Trim().ToUpper()
                    $v = $matches[2].Trim()
                    if ($v -and -not (Test-Path "env:$k")) {
                        Set-Item -Path "env:$k" -Value $v
                    }
                }
            }
        }
    } catch {
        # degradacion silenciosa
    }
}
if (-not $env:HF_API_TOKEN -and $env:OPENCODE_API_KEY_FALLBACK) {
    $env:HF_API_TOKEN = $env:OPENCODE_API_KEY_FALLBACK
}

# pythonw.exe: sin consola. Los logs van a logs\api_uvicorn.log via api_launcher.py
$pythonExe = "$ApiDir\.venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "$ApiDir\.venv\Scripts\python.exe"
}
$launcher = "$ProjectRoot\infra\api_launcher.py"

$proc = Start-Process -FilePath $pythonExe `
    -ArgumentList $launcher `
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
