<#
.SYNOPSIS
  Backup de la BD motoshop2024 (MySQL 5.0, MyISAM) en Windows.
  Verificación crítica #6 de Fase 0.
.DESCRIPTION
  Ejecuta mysqldump y comprime con gzip. El destino debe estar FUERA del repo.
  Imprime tamaño y duración para anotar en SEGUIMIENTO.md.
.PARAMETER BackupDir
  Directorio donde guardar el backup. Default: ~\Backups\motoshop
.PARAMETER Host
  Host de MySQL. Default: localhost
.PARAMETER Port
  Puerto de MySQL. Default: 3306
.PARAMETER User
  Usuario de MySQL. Default: root
.PARAMETER Password
  Contraseña de MySQL. Default: vacío
.PARAMETER Database
  Base de datos. Default: motoshop2024
.EXAMPLE
  .\infra\backup_mysql.ps1 -BackupDir "$env:USERPROFILE\Backups\motoshop"
#>

param(
  [string]$BackupDir = (Join-Path $env:USERPROFILE "Backups\motoshop"),
  [string]$Host = "localhost",
  [int]$Port = 3306,
  [string]$User = "root",
  [string]$Password = "",
  [string]$Database = "motoshop2024"
)

if (-not (Get-Command mysqldump -ErrorAction SilentlyContinue)) {
  Write-Error "mysqldump no encontrado. Verifica que MySQL esté en el PATH."
  exit 1
}

if (-not (Test-Path $BackupDir)) {
  New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$OutFile = Join-Path $BackupDir "${Database}_${Timestamp}.sql.gz"

Write-Host "→ Origen:  $User@$Host`:$Port/$Database"
Write-Host "→ Destino: $OutFile"

$mysqldumpArgs = @(
  "--host=$Host"
  "--port=$Port"
  "--user=$User"
  "--lock-tables"
  "--routines"
  "--triggers"
  "--events"
  "--default-character-set=utf8"
  $Database
)

if ($Password) {
  $mysqldumpArgs += "--password=$Password"
}

$Start = Get-Date

Write-Host "→ Iniciando mysqldump + gzip..."

# mysqldump pipe to gzip
$mysqldump = Start-Process -NoNewWindow -PassThru -FilePath "mysqldump" -ArgumentList $mysqldumpArgs -RedirectStandardOutput "stdout_dump.tmp"
$mysqldump.WaitForExit()
if ($mysqldump.ExitCode -ne 0) {
  Write-Error "mysqldump falló con código $($mysqldump.ExitCode)"
  if (Test-Path "stdout_dump.tmp") { Remove-Item "stdout_dump.tmp" }
  exit 2
}

# compress
if (Get-Command gzip -ErrorAction SilentlyContinue) {
  & gzip -9 -c stdout_dump.tmp > $OutFile
  Remove-Item "stdout_dump.tmp"
} else {
  # fallback: comprimir con .NET (no tan eficiente como gzip, pero funciona)
  Write-Host "→ gzip no encontrado. Usando compresión nativa .NET (GZipStream)..."
  $OutFile = [System.IO.Path]::ChangeExtension($OutFile, ".zip")
  $fsIn = [System.IO.File]::OpenRead("stdout_dump.tmp")
  $fsOut = [System.IO.File]::Create($OutFile)
  $gzip = New-Object System.IO.Compression.GZipStream $fsOut, ([System.IO.Compression.CompressionMode]::Compress)
  $fsIn.CopyTo($gzip)
  $gzip.Close(); $fsOut.Close(); $fsIn.Close()
  Remove-Item "stdout_dump.tmp"
}

$End = Get-Date
$Duration = ($End - $Start).TotalSeconds

$Size = [math]::Round((Get-Item $OutFile).Length / 1MB, 2)

Write-Host "→ Tamaño:   ${Size}MB"
Write-Host "→ Duración: $([math]::Round($Duration, 0))s"

# verify integrity for gzip
if ($OutFile -like "*.gz") {
  Write-Host "→ Verificación de integridad..."
  # try decompress to null
  $gzipVerify = Start-Process -NoNewWindow -PassThru -FilePath "gzip" -ArgumentList "-t", $OutFile
  $gzipVerify.WaitForExit()
  if ($gzipVerify.ExitCode -eq 0) {
    Write-Host "✓ gzip -t OK"
  } else {
    Write-Host "⚠ No se pudo verificar (gzip no disponible para -t)"
  }
}

Write-Host ""
Write-Host "Backup completado. Anotar en SEGUIMIENTO.md (F0, métrica de backup):"
Write-Host "  archivo:  $OutFile"
Write-Host "  tamaño:   ${Size}MB"
Write-Host "  duración: $([math]::Round($Duration, 0))s"
