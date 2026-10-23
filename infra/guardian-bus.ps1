<#
  guardian.ps1 -- perro guardian del nodo MotoShop.
  Corre cada 5 minutos para siempre. No decide nada de negocio: mantiene el nodo vivo
  y reporta por el bus aunque el agente de desarrollo este muerto.

  Que hace en cada vuelta:
    1. git pull --rebase de la rama de trabajo (aborta y reporta si hay conflicto).
    2. Si hay cambios sin commitear: corre la suite bancaria. Verde -> commit wip + push.
       Rojo -> NO commitea, deja el arbol como esta y lo reporta.
    3. /health de la API. Si no responde, la levanta con infra\start_api.ps1.
    4. Escribe un latido en el bus (FROM: motoshop-guardian) con SHA, estado, salud y
       minutos desde el ultimo mensaje del agente de desarrollo.

  No hace: force-push, rebase de commits pusheados, apply de conciliaciones, cambios de
  cuenta/tarea/autologon, ni levanta un segundo agente (dos agentes escribiendo = desastre).
#>
param(
  [string]$Repo     = "C:\Users\MotoShop\Documents\javidevmoto\motoshopData",
  [string]$BusWt    = "C:\Users\MotoShop\Documents\javidevmoto\motoshopData\bus-wt",
  [string]$Brama    = "feat/banco-transfer-25-tenant-config",
  [string]$BramaBus = "bus/banco-handoff",
  [string]$Remoto   = "github",
  [string]$Health   = "http://127.0.0.1:8000/health",
  [int]$IntervaloSeg = 300,
  [int]$SilencioMin  = 15
)

$ErrorActionPreference = "Continue"
# Sin TTY ni UI de credenciales: si git necesita autenticarse, que falle en vez
# de colgarse esperando un prompt invisible (medido: pull de >7 min).
$env:GIT_TERMINAL_PROMPT = "0"
$env:GIT_TERMINAL_ASKPASS = "0"
$env:GIT_ASKPASS = ""
$env:GCM_INTERACTIVE = "never"
$log = Join-Path $env:TEMP "guardian-banco.log"
function Log([string]$m) {
  $linea = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
  Add-Content -Path $log -Value $linea -Encoding utf8
}

$script:GitExe = (Get-Command git.exe -ErrorAction SilentlyContinue).Source
if (-not $script:GitExe) { $script:GitExe = "git.exe" }

function _Citar-Arg([string]$a) {
  # Start-Process pasa una sola lÃ­nea de comandos: los argumentos con espacios
  # o metacaracteres tienen que ir entre comillas.
  if ($a -match '[\s"()&|<>^]') { return '"' + ($a -replace '"', '\"') + '"' }
  return $a
}

function Git([string]$dir, [string[]]$gitArgs, [int]$TimeoutSeg = 120) {
  # Timeout duro por llamada: un pull colgado no puede frenar el latido (el
  # guardiÃ¡n promete liveness). 124 = timeout, 127 = no se pudo lanzar.
  $salida = Join-Path $env:TEMP ("guardian-git-" + [guid]::NewGuid().ToString("N") + ".out")
  $errores = "$salida.err"
  $lineaArgs = ($gitArgs | ForEach-Object { _Citar-Arg $_ }) -join " "
  try {
    $p = Start-Process -FilePath $script:GitExe -ArgumentList $lineaArgs `
          -WorkingDirectory $dir -WindowStyle Hidden -PassThru `
          -RedirectStandardOutput $salida -RedirectStandardError $errores
  } catch {
    return @{ code = 127; out = "no pude lanzar git: $($_.Exception.Message)" }
  }
  $p | Wait-Process -Timeout $TimeoutSeg -ErrorAction SilentlyContinue
  if (-not $p.HasExited) {
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    Remove-Item $salida, $errores -Force -ErrorAction SilentlyContinue
    return @{ code = 124; out = "timeout ${TimeoutSeg}s: git $lineaArgs" }
  }
  $texto = ""
  if (Test-Path $salida) { $texto += (Get-Content $salida -Raw -ErrorAction SilentlyContinue) }
  if (Test-Path $errores) { $texto += (Get-Content $errores -Raw -ErrorAction SilentlyContinue) }
  Remove-Item $salida, $errores -Force -ErrorAction SilentlyContinue
  return @{ code = $p.ExitCode; out = $texto }
}

function Estado-Api {
  try {
    $r = Invoke-WebRequest -Uri $Health -UseBasicParsing -TimeoutSec 8
    return ($r.StatusCode -eq 200)
  } catch { return $false }
}

function Evidencia-Api {
  $tarea = "?"
  try { $tarea = (Get-ScheduledTask -TaskName "MotoShopBackendSvc" -ErrorAction Stop).State } catch { }
  $pids = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'uvicorn|motoshop_api' } |
    ForEach-Object { $_.ProcessId })
  $dueno = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
  $estado = if ($dueno.Count -gt 0) { "listener_sin_health" }
            elseif ($pids.Count -gt 0) { "COLGADA_proceso_vivo" }
            else { "caida_sin_proceso" }
  return "estado=$estado tarea=$tarea pids=$($pids -join ',') listener=$($dueno -join ',')"
}

function Asegurar-Bus {
  if (-not (Test-Path $BusWt)) {
    Git $Repo @("fetch", $Remoto, "--quiet") | Out-Null
    Git $Repo @("worktree", "add", $BusWt, "-B", "bus-wt", "$Remoto/$BramaBus") | Out-Null
  }
  Git $BusWt @("fetch", $Remoto, "--quiet") | Out-Null
  $pull = Git $BusWt @("pull", "--rebase", "--quiet", $Remoto, $BramaBus)
  return ($pull.code -eq 0)
}

function Siguiente-Seq {
  $max = 0
  foreach ($carpeta in @("inbox", "outbox")) {
    $ruta = Join-Path $BusWt "bus\motoshop\$carpeta"
    if (Test-Path $ruta) {
      Get-ChildItem $ruta -Filter "*.md" | ForEach-Object {
        $n = 0
        if ([int]::TryParse($_.Name.Substring(0, 4), [ref]$n) -and $n -gt $max) { $max = $n }
      }
    }
  }
  return ($max + 1)
}

function Minutos-Sin-Dev {
  $ultimo = Get-ChildItem (Join-Path $BusWt "bus\motoshop\outbox") -Filter "*-motoshop-*.md" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not $ultimo) { return 9999 }
  return [int]((Get-Date) - $ultimo.LastWriteTime).TotalMinutes
}

Log "guardian arriba: repo=$Repo cada ${IntervaloSeg}s"

while ($true) {
  Log "TRACE_A ciclo";
  $sha = ""; $limpio = $true; $api = $false; $suite = ""; $conflicto = $false

  $pull = Git $Repo @("pull", "--rebase", "--quiet", $Remoto, $Brama)
  if ($pull.code -ne 0) {
    Git $Repo @("rebase", "--abort") | Out-Null
    $conflicto = $true
    Log "pull con conflicto: $($pull.out)"
  }

  Log "TRACE_B pull code=$($pull.code)";
  $status = Git $Repo @("status", "--porcelain")
  if ($status.out.Trim().Length -gt 0) {
    $limpio = $false
    Push-Location (Join-Path $Repo "motoshop-app\api")
    $out = & uv run pytest tests/ -q -k bank 2>&1
    $codigo = $LASTEXITCODE
    Pop-Location
    $suite = ($out | Select-Object -Last 1)
    if ($codigo -eq 0) {
      Git $Repo @("add", "-A") | Out-Null
      Git $Repo @("commit", "-m", "wip(banco): rescate de cambios sin commitear (guardian)") | Out-Null
      $push = Git $Repo @("push", $Remoto, $Brama)
      if ($push.code -ne 0) {
        Git $Repo @("pull", "--rebase", "--quiet", $Remoto, $Brama) | Out-Null
        $push = Git $Repo @("push", $Remoto, $Brama)
      }
      Log "cambios sin commitear: suite verde, commit wip y push (code=$($push.code))"
      $limpio = $true
    } else {
      Log "cambios sin commitear con suite en ROJO: no commiteo"
    }
  }

  Log "TRACE_C api start";
  $api = Estado-Api;
  Log "TRACE_D api=$api"
  if (-not $api) {
    Log "API sin health: $(Evidencia-Api)"
    $arranque = Join-Path $Repo "infra\start_api.ps1"
    if (Test-Path $arranque) {
      Log "API caida: ejecutando infra\start_api.ps1"
      Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",$arranque -WindowStyle Hidden
      Start-Sleep -Seconds 25
      $api = Estado-Api
      if (-not $api) {
        # colgado que start_api no pudo matar: matar SOLO PIDs exactos y reintentar
        $colgados = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
          Where-Object { $_.CommandLine -match 'uvicorn|motoshop_api' } |
          ForEach-Object { $_.ProcessId })
        foreach ($pidColgado in $colgados) { Stop-Process -Id $pidColgado -Force -ErrorAction SilentlyContinue }
        Log "API sigue sin health: mate pids=$($colgados -join ',') y reintento start_api"
        Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",$arranque -WindowStyle Hidden
        Start-Sleep -Seconds 25
        $api = Estado-Api
        Log "API reintento resultado=$api ($(Evidencia-Api))"
      }
    } else {
      Log "API caida y no existe infra\start_api.ps1"
    }
  }

  Log "TRACE_E presha";
  $sha = (Git $Repo @("rev-parse", "--short", "HEAD")).out.Trim()
  $ultimo = (Git $Repo @("log", "-1", "--format=%h %s")).out.Trim()
  $silencio = Minutos-Sin-Dev

  Log "TRACE_F prebus";
  if (Asegurar-Bus) {
    Log "TRACE_G busok";
    $seq = Siguiente-Seq
    $sello = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmZ")
    $cuerpo = @(
      "FROM: motoshop-guardian",
      "TO: auditor",
      "SEQ: {0:D4}" -f $seq,
      "TIPO: avance",
      "REQUIERE_RESPUESTA: no",
      "REFS: $sha - guardian",
      "",
      "Latido del guardian (el agente de desarrollo puede estar muerto: este mensaje sale igual).",
      "",
      "- SHA: $sha  ($ultimo)",
      "- Arbol limpio: $limpio",
      "- Pull: $(if ($conflicto) { 'CONFLICTO, abortado' } else { 'ok' })",
      "- API /health 200: $api",
      "- Suite bancaria: $(if ($suite) { $suite } else { 'no corrida' })",
      "- Minutos sin mensaje del agente de desarrollo: $silencio"
    )
    $destino = Join-Path $BusWt ("bus\motoshop\outbox\{0:D4}-guardian-{1}.md" -f $seq, $sello)
    Set-Content -Path $destino -Value ($cuerpo -join "`n") -Encoding utf8
    Git $BusWt @("add", "bus") | Out-Null
    Git $BusWt @("commit", "-q", "-m", ("bus(guardian): {0:D4} latido" -f $seq)) | Out-Null
    # El bus es compartido con auditor y otros nodos: si el push choca, rebase
    # y reintento (nunca force-push).
    $p = $null
    foreach ($intento in 1..3) {
      $p = Git $BusWt @("push", "-q", $Remoto, "HEAD:$BramaBus")
      if ($p.code -eq 0) { break }
      Git $BusWt @("pull", "--rebase", "--quiet", $Remoto, $BramaBus) | Out-Null
      Start-Sleep -Seconds 5
    }
    Log "latido SEQ $seq enviado (push code=$($p.code)), silencio dev=${silencio}m"
  } else {
    Log "no pude sincronizar el worktree del bus: latido no enviado"
  }

  Start-Sleep -Seconds $IntervaloSeg
}
