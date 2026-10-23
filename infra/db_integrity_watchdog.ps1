# db_integrity_watchdog.ps1 — Detecta y repara corrupcion MyISAM tras reinicios duros
#
# Contexto: la PC SERVER sufrio 12 reinicios duros (Kernel-Power 41, BugcheckCode=0,
# PowerButtonTimestamp=0) por perdida abrupta de energia. Cada reinicio abrupto puede
# dejar indices MyISAM corruptos (caso real: tabla `auxdetrep` -> "Wrong bytesec",
# marcada como crashed). Esta tabla quedo 10+ dias en estado crashed sin que nada
# la detectara.
#
# Que hace:
#   1. Corre mysqlcheck --check sobre la BD (detecta tablas crashed/corrupt).
#   2. Si detecta una tabla crashed, la repara con myisamchk -r a nivel de archivo
#      (no requiere el privilegio REPAIR de MySQL, que ningun usuario de la app tiene).
#   3. Limpia descargas .downloading huerfanas (interrumpidas por los reinicios).
#   4. Poda snapshots de DuckDB viejos conservando los N mas recientes.
#
# Log: infra\logs\db_integrity.log
# Config via env: MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD, MYSQL_HOST, MYSQL_PORT

$ErrorActionPreference = "Continue"

$RepoRoot    = "C:\Users\MotoShop\Documents\javidevmoto\motoshopData"
$MySQLBin    = "C:\Program Files (x86)\MySQL\MySQL Server 5.0\bin"
$DataDir     = "C:\Program Files (x86)\MySQL\MySQL Server 5.0\Data"
$LogDir      = "$RepoRoot\infra\logs"
$LogFile     = "$LogDir\db_integrity.log"
$OutDir      = "$RepoRoot\out"
$KeepSnapshots = 10
$MinFreeGB   = 5

function Log([string]$Level, [string]$Message) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [$Level] $Message"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

# ─── Cargar credenciales ──────────────────────────────────────────────
$envFile = "$RepoRoot\.env"
if (!(Test-Path $envFile)) { Log "ERROR" "No existe $envFile"; exit 1 }

$cfg = @{}
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#=\s]+)\s*=\s*(.*)$') {
        $cfg[$matches[1]] = $matches[2].Trim('"', "'")
    }
}

$dbUser = $cfg['MYSQL_USER']
$dbPass = $cfg['MYSQL_PASSWORD']
$dbHost = if ($cfg['MYSQL_HOST']) { $cfg['MYSQL_HOST'] } else { "localhost" }
$dbPort = if ($cfg['MYSQL_PORT']) { $cfg['MYSQL_PORT'] } else { "3306" }
$dbName = $cfg['MYSQL_DATABASE']

if (!$dbUser -or !$dbName) { Log "ERROR" "Faltan MYSQL_USER/MYSQL_DATABASE en .env"; exit 1 }

$env:MYSQL_PWD = $dbPass
$mysqlExe   = "$MySQLBin\mysql.exe"
$checkExe   = "$MySQLBin\mysqlcheck.exe"
$myisamchk  = "$MySQLBin\myisamchk.exe"

# ─── 1. Detectar tablas corruptas ────────────────────────────────────
Log "INFO" "=== db_integrity_watchdog: verificando $dbName ==="

$checkOut = & $checkExe -u $dbUser -h $dbHost -P $dbPort --check $dbName 2>&1 | Out-String
$crashed = [regex]::Matches($checkOut, "(?m)^(?<db>[^\s]+)\.(?<tbl>[^\s]+)\s+>\s+error\s+:\s+Table '.*?' is marked as crashed")
$crashedTables = @($crashed | ForEach-Object { $_.Groups['tbl'].Value } | Sort-Object -Unique)

if ($crashedTables.Count -eq 0) {
    Log "INFO" "OK: sin tablas crashed/corrupt en $dbName"
} else {
    foreach ($t in $crashedTables) {
        Log "WARN" "Tabla corrupta detectada: $t"

        $myi = Join-Path $DataDir "$dbName\$t.MYI"
        $myd = Join-Path $DataDir "$dbName\$t.MYD"

        # Backup a nivel de archivo antes de tocar nada
        $bkDir = "$LogDir\db_repair_backup"
        New-Item -ItemType Directory -Path $bkDir -Force | Out-Null
        $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
        foreach ($f in @($myi, $myd)) {
            if (Test-Path $f) {
                Copy-Item $f -Destination "$bkDir\$([System.IO.Path]::GetFileName($f)).$stamp.bak" -Force -ErrorAction SilentlyContinue
            }
        }
        Log "INFO" "Backup de archivos de '$t' guardado en $bkDir (stamp=$stamp)"

        # Reparacion a nivel de archivo (no requiere privilegio REPAIR de MySQL)
        if (Test-Path $myi) {
            $repairOut = & $myisamchk -r $myi 2>&1 | Out-String
            $repairOut = ($repairOut -replace '[^\x20-\x7E]', ' ').Trim()
            Log "INFO" "myisamchk -r '$t': $repairOut"

            # Limpiar flag 'crashed' del .MYI (bit 0 del header)
            try {
                $bytes = [System.IO.File]::ReadAllBytes($myi)
                if ($bytes.Length -gt 2) {
                    $flags = [System.BitConverter]::ToUInt16($bytes, 1)
                    if (($flags -band 1) -ne 0) {
                        $bytes[1] = [byte]($flags -band 0xFFFE)
                        $bytes[2] = [byte](($flags -shr 8) -band 0xFFFE)
                        [System.IO.File]::WriteAllBytes($myi, $bytes)
                        Log "INFO" "Flag 'crashed' limpiado del header de '$t'"
                    }
                }
            } catch {
                Log "WARN" "No se pudo limpiar flag crashed de '$t': $($_.Exception.Message)"
            }

            $verify = & $myisamchk -c $myi 2>&1 | Out-String
            $verify = ($verify -replace '[^\x20-\x7E]', ' ').Trim()
            Log "INFO" "Verificacion myisamchk -c '$t': $verify"
        }
    }
}

# ─── 2. Limpiar descargas .downloading huerfanas ─────────────────────
try {
    $cutoff = (Get-Date).AddHours(-6)
    $orphans = Get-ChildItem $OutDir -Filter '*.downloading*' -File -ErrorAction SilentlyContinue |
                Where-Object { $_.LastWriteTime -lt $cutoff }
    foreach ($o in $orphans) {
        Remove-Item $o.FullName -Force -ErrorAction SilentlyContinue
        Log "INFO" "Descargando huerfana eliminada: $($o.Name) ($([math]::Round($o.Length/1MB,1)) MB)"
    }
} catch {
    Log "WARN" "No se pudieron limpiar descargas huerfanas: $($_.Exception.Message)"
}

# ─── 3. Podar snapshots de DuckDB ─────────────────────────────────────
try {
    $snaps = Get-ChildItem $OutDir -Filter '*.snapshot-*.duckdb' -File -ErrorAction SilentlyContinue |
             Sort-Object LastWriteTime -Descending
    if ($snaps.Count -gt $KeepSnapshots) {
        $old = $snaps | Select-Object -Skip $KeepSnapshots
        $freed = 0
        foreach ($s in $old) {
            $freed += $s.Length
            Remove-Item $s.FullName -Force -ErrorAction SilentlyContinue
        }
        Log "INFO" "Snapshots podados: $($old.Count) eliminados, $([math]::Round($freed/1MB)) MB liberados (conservando $KeepSnapshots)"
    }
} catch {
    Log "WARN" "No se pudo podar snapshots: $($_.Exception.Message)"
}

# ─── 4. Verificar espacio en disco ────────────────────────────────────
try {
    $c = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
    $freeGB = [math]::Round($c.FreeSpace / 1GB, 1)
    if ($freeGB -lt $MinFreeGB) {
        Log "WARN" "Espacio en C: bajo = $freeGB GB (minimo recomendado $MinFreeGB GB)"
    } else {
        Log "INFO" "Espacio en C: = $freeGB GB"
    }
} catch {
    Log "WARN" "No se pudo verificar espacio en disco: $($_.Exception.Message)"
}

Log "INFO" "=== db_integrity_watchdog: fin ==="
exit 0
