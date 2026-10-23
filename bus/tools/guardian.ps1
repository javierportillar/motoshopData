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
  [string]$BusWt    = "C:\Users\MotoShop\Documents\javidevmoto\bus-wt",
  [string]$Brama    = "feat/banco-transfer-25-tenant-config",
  [string]$BramaBus = "bus/banco-handoff",
  [string]$Remoto   = "github",
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

function Git([string]$dir, [string[]]$args) {
  Push-Location $dir
  try { $out = & git @args 2>&1; return @{ code = $LASTEXITCODE; out = ($out -join "`n") } }
  finally { Pop-Location }
}

function Estado-Api {
  try {
    $r = Invoke-WebRequest -Uri $Health -UseBasicParsing -TimeoutSec 8
    return ($r.StatusCode -eq 200)
  } catch { return $false }
}

function Asegurar-Bus {
  if (-not (Test-Path $BusWt)) {
    Git $Repo @("fetch", $Remoto, "--quiet") | Out-Null
    & git -C $Repo worktree add $BusWt -B bus-wt "$Remoto/$BramaBus" 2>&1 | Out-Null
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
  $sha = ""; $limpio = $true; $api = $false; $suite = ""; $conflicto = $false

  $pull = Git $Repo @("pull", "--rebase", "--quiet", $Remoto, $Brama)
  if ($pull.code -ne 0) {
    Git $Repo @("rebase", "--abort") | Out-Null
    $conflicto = $true
    Log "pull con conflicto: $($pull.out)"
  }

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
      Log "cambios sin commitear: suite verde, commit wip y push (code=$($push.code))"
      $limpio = $true
    } else {
      Log "cambios sin commitear con suite en ROJO: no commiteo"
    }
  }

  $api = Estado-Api
  if (-not $api) {
    $arranque = Join-Path $Repo "infra\start_api.ps1"
    if (Test-Path $arranque) {
      Log "API caida: ejecutando infra\start_api.ps1"
      Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",$arranque -WindowStyle Hidden
      Start-Sleep -Seconds 25
      $api = Estado-Api
    } else {
      Log "API caida y no existe infra\start_api.ps1"
    }
  }

  $sha = (Git $Repo @("rev-parse", "--short", "HEAD")).out.Trim()
  $ultimo = (Git $Repo @("log", "-1", "--format=%h %s")).out.Trim()
  $silencio = Minutos-Sin-Dev

  if (Asegurar-Bus) {
    $seq = Siguiente-Seq
    $sello = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmZ")
    $cuerpo = @(
      "FROM: motoshop-guardian",
      "TO: auditor",
      "SEQ: {0:D4}" -f $seq,
      "TIPO: avance",
      "REQUIERE_RESPUESTA: no",
      "REFS: $sha · guardian",
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
    $p = Git $BusWt @("push", "-q", $Remoto, $BramaBus)
    Log "latido SEQ $seq enviado (push code=$($p.code)), silencio dev=${silencio}m"
  } else {
    Log "no pude sincronizar el worktree del bus: latido no enviado"
  }

  Start-Sleep -Seconds $IntervaloSeg
}
