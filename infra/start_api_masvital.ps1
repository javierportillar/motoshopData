<#
  start_api_masvital.ps1 -- arranca la API del nodo MasVital sin ninguna ventana visible.

  La tarea programada MasVitalBackendService lo invoca a traves de
  start_api_masvital_wrapper.vbs (wscript + Run(..., 0, True)), asi que no aparece
  ni CMD, ni PowerShell, ni consola de Python.

  - pythonw.exe, nunca python.exe: no hay consola que mostrar.
  - stdout/stderr del proceso van a logs\api_masvital_out.log y _err.log
    (logs/ esta en .gitignore): uvicorn no escribe a una consola que no existe.
  - Vigilante de arranque: si a los $EsperaSeg el puerto no responde, mata el
    proceso y reintenta. Sin esto, un boot con la red sin lista deja el proceso
    colgado para siempre y el nodo sin API.
  - Si no arranca en $Intentos intentos, sale con codigo 1 y el guardian lo reporta.

  Este archivo es la version reproducible del lanzador: antes vivia solo en
  C:\Users\ProDesk\.masvital\run_api.py, fuera del repo.
#>
param(
  [int]$Puerto = 8000,
  [int]$EsperaSeg = 150,
  [int]$Intentos = 3
)

$ErrorActionPreference = "Continue"

$Raiz = (Resolve-Path "$PSScriptRoot\..").Path
$Api = Join-Path $Raiz "motoshop-app\api"
$Logs = Join-Path $Raiz "logs"
$LogControl = Join-Path $Logs "api_masvital.log"
$LogOut = Join-Path $Logs "api_masvital_out.log"
$LogErr = Join-Path $Logs "api_masvital_err.log"

if (-not (Test-Path $Logs)) { New-Item -ItemType Directory -Path $Logs -Force | Out-Null }

function Log([string]$mensaje) {
  Add-Content -Path $LogControl -Value ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $mensaje) -Encoding utf8
}

# --- entorno: el hijo hereda las variables de este proceso -------------------
$envFile = Join-Path $Raiz ".env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    if ($_ -match "^\s*([^#=]+)=(.*)$") {
      $clave = $matches[1].Trim()
      $valor = $matches[2].Trim().Trim('"').Trim("'")
      if ($clave) { Set-Item -Path "env:$clave" -Value $valor -ErrorAction SilentlyContinue }
    }
  }
} else {
  Log "AVISO: no encontre .env en $Raiz (la API usa sus defaults)"
}
$env:PYTHONPATH = Join-Path $Api "src"

$pythonw = Join-Path $Api ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
  Log "ERROR: no existe $pythonw"
  exit 1
}

function Puerto-Arriba {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Puerto/health" -UseBasicParsing -TimeoutSec 5
    return ($r.StatusCode -eq 200)
  } catch { return $false }
}

function Matar-Instancia {
  param([int]$Id)
  if ($Id -gt 0) { Stop-Process -Id $Id -Force -ErrorAction SilentlyContinue }
  Get-NetTCPConnection -LocalPort $Puerto -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

# --- arranque con vigilante ---------------------------------------------------
for ($intento = 1; $intento -le $Intentos; $intento++) {
  Matar-Instancia -Id 0
  Start-Sleep -Seconds 3

  $inicio = Get-Date
  Log "intento $intento/$Intentos : arrancando pythonw en :$Puerto"
  $proc = Start-Process -FilePath $pythonw -PassThru -WindowStyle Hidden -WorkingDirectory $Api `
    -ArgumentList @("-m", "uvicorn", "motoshop_api.main:app", "--host", "0.0.0.0", "--port", "$Puerto") `
    -RedirectStandardOutput $LogOut -RedirectStandardError $LogErr
  Log "pid=$($proc.Id)"

  $arriba = $false
  while (((Get-Date) - $inicio).TotalSeconds -lt $EsperaSeg) {
    Start-Sleep -Seconds 5
    if (Puerto-Arriba) { $arriba = $true; break }
    if ($proc.HasExited) { break }
  }

  if ($arriba) {
    $seg = [int]((Get-Date) - $inicio).TotalSeconds
    Log "API arriba en ${seg}s (pid=$($proc.Id))"
    exit 0
  }

  if ($proc.HasExited) {
    Log "el proceso murio solo (codigo $($proc.ExitCode)); ver $LogErr"
  } else {
    Log "sin /health despues de ${EsperaSeg}s: mato el pid $($proc.Id) y reintento"
  }
  Matar-Instancia -Id $proc.Id
}

Log "ERROR: la API no arranco en $Intentos intentos"
exit 1
