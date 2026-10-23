<#
  guardian-bus.ps1 -- perro guardian del nodo MasVital (adaptado de bus/tools/guardian.ps1).
  Corre cada 5 minutos. No decide nada de negocio: mantiene el nodo vivo y reporta
  por el bus aunque el agente de desarrollo este muerto.

  Cada vuelta:
    1. git pull --rebase de la rama de trabajo (aborta y reporta si hay conflicto).
    2. Cambios sin commitear: corre la suite bancaria. Verde -> commit wip + push.
       Rojo -> no commitea y lo reporta.
    3. /health de la API. Si no responde, arranca la tarea MasVitalBackendService.
    4. Latido al bus (FROM: masvital-guardian) con SHA, arbol, pull, API y suite.

  No hace: force-push, rebase de commits pusheados, apply de conciliaciones, cambios de
  cuenta/tarea/autologon, ni levanta un segundo agente.

  Ojo (PowerShell 5.1): NO envolver llamadas a git en una funcion que devuelva valor.
  `& git ...` capturado dentro de una funcion cuelga el proceso sin salida (probado dos
  veces: pull y status). Por eso todo git va suelto y con `git -C`, y $LASTEXITCODE se
  lee en la linea siguiente.
#>
param(
  [string]$Nodo     = "masvital",
  [string]$Repo     = "C:\Users\ProDesk\Documents\javdevmasv\motoshopData",
  [string]$BusWt    = "C:\Users\ProDesk\Documents\javdevmasv\bus-wt",
  [string]$Brama    = "feat/banco-transfer-25-tenant-config",
  [string]$BramaBus = "bus/banco-handoff",
  [string]$Remoto   = "origin",
  [string]$TareaApi = "MasVitalBackendService",
  [string]$Health   = "http://127.0.0.1:8000/health",
  [int]$IntervaloSeg = 300,
  [int]$SilencioMin  = 15
)

$ErrorActionPreference = "Continue"
$log = Join-Path $env:TEMP "guardian-banco.log"

function Log([string]$m) {
  $linea = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
  Add-Content -Path $log -Value $linea -Encoding utf8
}

function Estado-Api {
  try {
    $r = Invoke-WebRequest -Uri $Health -UseBasicParsing -TimeoutSec 8
    return ($r.StatusCode -eq 200)
  } catch { return $false }
}

function Asegurar-Bus {
  if (-not (Test-Path $BusWt)) {
    & git -C $Repo worktree add $BusWt -B bus-wt "$Remoto/$BramaBus" | Out-Null
  }
  & git -C $BusWt fetch $Remoto --quiet | Out-Null
  & git -C $BusWt pull --rebase --quiet $Remoto $BramaBus | Out-Null
  return ($LASTEXITCODE -eq 0)
}

function Siguiente-Seq {
  $max = 0
  foreach ($carpeta in @("inbox", "outbox")) {
    $ruta = Join-Path $BusWt "bus\$Nodo\$carpeta"
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
  $ultimo = Get-ChildItem (Join-Path $BusWt "bus\$Nodo\outbox") -Filter "*-$Nodo-*.md" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not $ultimo) { return 9999 }
  return [int]((Get-Date) - $ultimo.LastWriteTime).TotalMinutes
}

Log "guardian arriba: nodo=$Nodo repo=$Repo cada ${IntervaloSeg}s"

while ($true) {
  $sha = ""; $limpio = $true; $api = $false; $suite = ""; $conflicto = $false

  $status = (& git -C $Repo status --porcelain) -join "`n"
  if ($status.Trim().Length -gt 0) {
    $limpio = $false
    Push-Location (Join-Path $Repo "motoshop-app\api")
    $out = & ".\.venv\Scripts\python.exe" -m pytest tests/ -q -k bank 2>&1
    $codigo = $LASTEXITCODE
    Pop-Location
    $suite = ($out | Select-Object -Last 1)
    if ($codigo -eq 0) {
      & git -C $Repo add -A | Out-Null
      & git -C $Repo commit -q -m "wip(banco): rescate de cambios sin commitear (guardian)" | Out-Null
      & git -C $Repo push -q $Remoto $Brama | Out-Null
      Log "cambios sin commitear: suite verde, commit wip y push (code=$LASTEXITCODE)"
      $limpio = $true
    } else {
      Log "cambios sin commitear con suite en ROJO: no commiteo"
    }
  }

  # El pull va DESPUES del rescate: con el arbol sucio `pull --rebase` se niega (128).
  & git -C $Repo pull --rebase --quiet $Remoto $Brama | Out-Null
  if ($LASTEXITCODE -ne 0) {
    $enRebase = (Test-Path (Join-Path $Repo ".git\rebase-merge")) -or (Test-Path (Join-Path $Repo ".git\rebase-apply"))
    if ($enRebase) { & git -C $Repo rebase --abort | Out-Null }
    $conflicto = $true
    Log "pull fallo (code=$LASTEXITCODE, rebase en curso=$enRebase): no toco nada"
  }

  $api = Estado-Api
  if (-not $api) {
    Log "API caida: arrancando la tarea $TareaApi"
    & schtasks /Run /TN $TareaApi | Out-Null
    Start-Sleep -Seconds 25
    $api = Estado-Api
  }

  $sha = (& git -C $Repo rev-parse --short HEAD).Trim()
  $ultimo = (& git -C $Repo log -1 --format="%h %s").Trim()
  $silencio = Minutos-Sin-Dev

  if (Asegurar-Bus) {
    $seq = Siguiente-Seq
    $sello = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmZ")
    $cuerpo = @(
      "FROM: $Nodo-guardian",
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
    $destino = Join-Path $BusWt ("bus\$Nodo\outbox\{0:D4}-guardian-{1}.md" -f $seq, $sello)
    Set-Content -Path $destino -Value ($cuerpo -join "`n") -Encoding utf8
    & git -C $BusWt add bus | Out-Null
    & git -C $BusWt commit -q -m ("bus(guardian): {0:D4} latido" -f $seq) | Out-Null
    & git -C $BusWt push -q $Remoto "HEAD:refs/heads/$BramaBus" | Out-Null
    Log "latido SEQ $seq enviado (push code=$LASTEXITCODE), silencio dev=${silencio}m"
  } else {
    Log "no pude sincronizar el worktree del bus: latido no enviado"
  }

  Start-Sleep -Seconds $IntervaloSeg
}
