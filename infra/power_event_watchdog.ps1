# power_event_watchdog.ps1 — Detecta y reporta reinicios duros por perdida de energia
#
# Contexto: la PC SERVER sufrio 12 reinicios duros en 5 dias (Kernel-Power 41,
# BugcheckCode=0, PowerButtonTimestamp=0, sin minidumps, sin WHEA). Cada reinicio
# abrupto = corte electrico. Sin UPS, cada corte deja el equipo dead hasta que
# vuelve la corriente (y en este equipo vuelve solo, con el escritorio vacio).
#
# Este watchdog:
#   1. Cuenta los reinicios por dia y detecta el patron (caida de energia).
#   2. Calcula el "downtime real" (6008 = hora exacta de la muerte) por evento.
#   3. Escribe un reporte legible para diagnostico y para justificar el UPS.
#   4. Registra el estado del UPS si algum dia se conecta uno.
#
# Log: infra\logs\power_events.log
# Reporte: infra\logs\power_events_report.txt

$ErrorActionPreference = "Continue"

$RepoRoot = "C:\Users\MotoShop\Documents\javidevmoto\motoshopData"
$LogDir   = "$RepoRoot\infra\logs"
$LogFile  = "$LogDir\power_events.log"
$Report   = "$LogDir\power_events_report.txt"

if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

function Log([string]$Level, [string]$Message) {
    Add-Content -Path $LogFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [$Level] $Message" -Encoding UTF8
}

# ─── Recolectar eventos de reinicio duro ─────────────────────────────
$since = (Get-Date).AddDays(-14)

$boots = @(Get-WinEvent -FilterHashtable @{LogName='System'; Id=12; StartTime=$since} -ErrorAction SilentlyContinue |
           Sort-Object TimeCreated)

$crashes = @(Get-WinEvent -FilterHashtable @{LogName='System'; Id=41; StartTime=$since} -ErrorAction SilentlyContinue |
             Sort-Object TimeCreated)

# Evento 6008: "El cierre anterior del sistema a las HH:MM:SS resulto inesperado"
# Esa hora es la de la MUERTE real de la maquina.
$deaths = New-Object System.Collections.Generic.List[object]
foreach ($e in (Get-WinEvent -FilterHashtable @{LogName='System'; Id=6008; StartTime=$since} -ErrorAction SilentlyContinue | Sort-Object TimeCreated)) {
    $m = $e.Message
    if ($m -match 'a las (\d{1,2}):(\d{2}):(\d{2})') {
        $hh = [int]$matches[1]; $mm = [int]$matches[2]; $ss = [int]$matches[3]
        $death = $e.TimeCreated.Date.AddHours($hh).AddMinutes($mm).AddSeconds($ss)
        if ($death -gt $e.TimeCreated) { $death = $death.AddDays(-1) }
        $deaths.Add([pscustomobject]@{ Died = $death; Logged = $e.TimeCreated })
    }
}

# Downtime real: de la muerte al siguiente boot
$downtimes = @()
for ($i = 0; $i -lt $deaths.Count; $i++) {
    $nextBoot = $boots | Where-Object { $_.TimeCreated -gt $deaths[$i].Died } | Select-Object -First 1
    if ($nextBoot) {
        $downtimes += [pscustomobject]@{
            Died     = $deaths[$i].Died
            Booted   = $nextBoot.TimeCreated
            Downtime = [math]::Round(($nextBoot.TimeCreated - $deaths[$i].Died).TotalMinutes, 1)
        }
    }
}

# ─── Reporte ─────────────────────────────────────────────────────────
$lines = @()
$lines += "REPORTE DE EVENTOS DE ENERGIA - MotoShop SERVER"
$lines += "Generado: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  (ventana 14 dias)"
$lines += ""
$lines += "Reinicios duros (Kernel-Power 41): $($crashes.Count)"
$lines += "Cortes de alimentacion detectados (6008): $($deaths.Count)"
$lines += ""

if ($downtimes.Count -gt 0) {
    $lines += "DETALLE DE CORTES (hora de muerte -> arranque):"
    foreach ($d in $downtimes) {
        $lines += ("  {0} -> {1}   caido {2} min" -f $d.Died.ToString('dd/MM HH:mm:ss'), $d.Booted.ToString('dd/MM HH:mm:ss'), $d.Downtime)
    }
    $avg = [math]::Round((($downtimes | Measure-Object Downtime -Average).Average), 1)
    $max = ($downtimes | Measure-Object Downtime -Maximum).Maximum
    $lines += ""
    $lines += "Caida promedio: $avg min   |   maxima: $max min"
    $lines += ""
}

# Analisis de firmas
$bugchecks = 0; $powerButtons = 0; $withDump = $false
foreach ($c in $crashes) {
    try {
        $x = [xml]$c.ToXml()
        foreach ($d in $x.Event.EventData.Data) {
            if ($d.Name -eq 'BugcheckCode' -and $d.'#text' -and $d.'#text' -ne '0') { $bugchecks++ }
            if ($d.Name -eq 'PowerButtonTimestamp' -and $d.'#text' -and $d.'#text' -ne '0') { $powerButtons++ }
        }
    } catch {}
}
$dumps = @(Get-ChildItem 'C:\Windows\Minidump' -Filter '*.dmp' -ErrorAction SilentlyContinue)
$memoryDmp = Test-Path 'C:\Windows\MEMORY.DMP'

$lines += "DIAGNOSTICO DE FIRMA:"
$lines += "  Eventos 41 con BugcheckCode != 0 (BSOD real): $bugchecks"
$lines += "  Eventos 41 con PowerButtonTimestamp != 0 (boton power): $powerButtons"
$lines += "  Minidumps presentes: $($dumps.Count)   MEMORY.DMP: $memoryDmp"
$lines += ""
if ($bugchecks -eq 0 -and $powerButtons -eq 0 -and $dumps.Count -eq 0) {
    $lines += "  => DIAGNOSTICO: sin BSOD, sin boton de power, sin dumps."
    $lines += "     FIRMA DE PERDIDA DE ENERGIA (corte electrico / fuente / cable)."
    $lines += "     El equipo se apaga de golpe y vuelve solo cuando retorna la corriente."
    $lines += "     ACCION REQUERIDA: UPS con linea de datos (650-1000 VA minimo)."
} else {
    $lines += "  => Hay indicios de fallo de software/equipo. Revisar dumps."
}
$lines += ""

# Estado del UPS (si algum dia se instala)
$ups = @(Get-CimInstance Win32_UPSDevice -ErrorAction SilentlyContinue)
if ($ups.Count -eq 0) {
    $lines += "UPS DETECTADO: NINGUNO (Win32_UPSDevice vacio)"
    $lines += "  Sin UPS, cada corte electrico deja el servidor caido hasta que vuelve la luz."
} else {
    $lines += "UPS DETECTADO:"
    foreach ($u in $ups) { $lines += "  $($u.Name) | $($u.Status) | $($u.UPSManufacturer) $($u.UPSModel)" }
}

Set-Content -Path $Report -Value ($lines -join "`r`n") -Encoding UTF8

# ─── Alerta en el log si la situacion empeora ────────────────────────
$last24 = @($crashes | Where-Object { $_.TimeCreated -gt (Get-Date).AddHours(-24) })
if ($last24.Count -ge 3) {
    Log "ALERT" "$($last24.Count) reinicios duros en las ultimas 24h. Sin UPS el servidor queda caido en cada corte. Ver $Report"
} else {
    Log "INFO" "Reinicios 24h: $($last24.Count) | total 14d: $($crashes.Count) | cortes: $($deaths.Count)"
}

exit 0
